import os
import shutil
import json
from typing import List, Dict

from utils import (
    get_video_resolution,
    detect_available_encoders,
    select_best_hevc_encoder,
    get_video_files,
    run_ffmpeg,
    move_file,
    get_media_duration_seconds,
    ass_time_add,
    get_last_download_files,
)


def choose_encoder() -> str:
    encoders = detect_available_encoders()
    print("\n可用的编码器列表：")
    for idx, (enc, desc) in enumerate(encoders):
        print(f"  {idx+1}. {enc} - {desc}")
    print("按回车直接使用推荐编码器（自动优先硬件）：")
    choice = input("请选择编码器编号（如 1），或直接回车：").strip()
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(encoders):
            print(f"你选择了编码器：{encoders[idx][0]} - {encoders[idx][1]}")
            return encoders[idx][0]
        else:
            print("无效编号，使用默认推荐编码器。")
    encoder = select_best_hevc_encoder(encoders)
    print(f"自动选择编码器：{encoder}")
    return encoder


TRANSCODE_PARAMS = {
    'fps': 60,
    'bitrate': '2M',
    'audio_bitrate': '320k',
    'pix_fmt': 'yuv420p'
}


def find_subtitle(video_path: str) -> str | None:
    print(f"🔍 查找字幕文件 - 视频路径: {video_path}")
    dirname = os.path.dirname(video_path)
    basename = os.path.splitext(os.path.basename(video_path))[0]
    subtitle_path = os.path.join(dirname, basename + ".ass")

    print(f"   📁 视频目录: {dirname}")
    print(f"   📄 视频基础名: {basename}")
    print(f"   🎯 预期字幕路径: {subtitle_path}")

    if os.path.isfile(subtitle_path):
        print(f"   ✅ 找到字幕文件: {subtitle_path}")
        return subtitle_path
    else:
        print(f"   ❌ 字幕文件不存在: {subtitle_path}")
        print(f"   📋 目录中的所有文件:")
        try:
            for file in os.listdir(dirname):
                print(f"      • {file}")
                if file.lower().endswith(('.ass', '.srt', '.vtt', '.sub')):
                    print(f"        🎬 发现字幕文件: {file}")
        except Exception as e:
            print(f"   ⚠️ 无法列出目录文件: {e}")

        subtitle_extensions = ['.ass', '.srt', '.vtt', '.sub']
        for ext in subtitle_extensions:
            alt_subtitle_path = os.path.join(dirname, basename + ext)
            if os.path.isfile(alt_subtitle_path):
                print(f"   🔄 找到替代字幕文件: {alt_subtitle_path}")
                return alt_subtitle_path

        return None


def merge_ass_with_offsets(subtitle_entries: List[tuple], clip_durations: List[float], gap_seconds: float, merged_subtitle_path: str) -> None:
    def cumulative_offset_for_index(index: int) -> float:
        if index <= 0:
            return 0.0
        total = sum(clip_durations[:index])
        total += gap_seconds * index
        return total

    with open(merged_subtitle_path, "w", encoding="utf-8") as fout:
        wrote_header = False
        for entry_idx, (sub_path, clip_index) in enumerate(subtitle_entries):
            with open(sub_path, "r", encoding="utf-8") as fin:
                lines = fin.readlines()
            in_events = False
            offset = cumulative_offset_for_index(clip_index)
            for line in lines:
                # 首段：写入头部直到 [Events]，并从此开始处理事件
                if not wrote_header:
                    if line.strip().lower() == "[events]":
                        fout.write(line)
                        wrote_header = True
                        in_events = True
                        continue
                    else:
                        fout.write(line)
                        continue

                # 后续段：跳过头部，遇到 [Events] 后开始处理事件
                if not in_events:
                    if line.strip().lower() == "[events]":
                        in_events = True
                    continue

                # 进入事件段：去重 Format 行，仅写入对齐后的 Dialogue 与其它事件行
                lower = line.strip().lower()
                if lower.startswith('format:'):
                    continue
                if line.startswith("Dialogue:"):
                    parts = line.split(",", 9)
                    if len(parts) >= 3:
                        parts[1] = ass_time_add(parts[1], offset)
                        parts[2] = ass_time_add(parts[2], offset)
                        fout.write(",".join(parts))
                    else:
                        fout.write(line)
                else:
                    fout.write(line)


def merge_videos_with_best_hevc(download_dir: str | None = None, encoder: str | None = None) -> bool:
    # --- checkpoint helpers ---
    def project_root() -> str:
        return os.path.dirname(os.path.abspath(__file__))

    def checkpoint_path() -> str:
        return os.path.join(project_root(), '.merge_checkpoint.json')

    def work_dir_path(base_dir: str) -> str:
        # 在源目录下创建工作目录，避免跨盘复制，提升性能
        return os.path.join(base_dir, '.merge_work')

    def load_checkpoint() -> Dict | None:
        try:
            path = checkpoint_path()
            if os.path.isfile(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def save_checkpoint(state: Dict) -> None:
        try:
            with open(checkpoint_path(), 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def clear_checkpoint_and_workdir(base_dir: str | None = None) -> None:
        # 先删除断点文件
        try:
            if os.path.isfile(checkpoint_path()):
                os.remove(checkpoint_path())
        except Exception:
            pass
        # 尝试定位并删除工作目录
        try:
            wd: str | None = None
            if base_dir:
                wd = work_dir_path(base_dir)
            else:
                st = load_checkpoint()
                if st:
                    wd = st.get('work_dir')
            if wd and os.path.isdir(wd):
                shutil.rmtree(wd, ignore_errors=True)
        except Exception:
            pass
    def parse_selection(selection: str, upper_bound: int) -> List[int]:
        # 解析类似 "1,3,5-7" 的输入，返回去重且按出现顺序的索引（0-based）
        tokens = [t.strip() for t in selection.split(',') if t.strip()]
        result: List[int] = []
        seen = set()
        for tok in tokens:
            if '-' in tok:
                a, b = tok.split('-', 1)
                if a.isdigit() and b.isdigit():
                    start_i = int(a)
                    end_i = int(b)
                    if start_i <= end_i:
                        for v in range(start_i, end_i + 1):
                            idx0 = v - 1
                            if 0 <= idx0 < upper_bound and idx0 not in seen:
                                seen.add(idx0)
                                result.append(idx0)
                    else:
                        for v in range(end_i, start_i + 1):
                            idx0 = v - 1
                            if 0 <= idx0 < upper_bound and idx0 not in seen:
                                seen.add(idx0)
                                result.append(idx0)
            elif tok.isdigit():
                idx0 = int(tok) - 1
                if 0 <= idx0 < upper_bound and idx0 not in seen:
                    seen.add(idx0)
                    result.append(idx0)
        return result

    try:
        files = get_last_download_files()
        if not files:
            download_dir = download_dir or "./download"
            files = get_video_files(download_dir)

        print(f"\n🔎 找到以下视频文件：")
        all_files = get_video_files(download_dir) if download_dir else []
        # 展示用列表：按创建时间倒序显示（Windows 下为创建时间）
        display_files = sorted(all_files, key=os.path.getctime, reverse=True)
        is_new_file = {f: f in files for f in all_files} if files and all_files else {}
        for idx, f in enumerate(display_files):
            marker = " [新增]" if is_new_file.get(f) else ""
            print(f"  {idx+1:2d}. {os.path.basename(f)}{marker}")

        # 先询问是否只合并新增文件
        if files and len(files) != len(all_files):
            print(f"\n detected {len(files)} new file(s).")
            choice = input("是否只合并新增文件？(Y/n，输入'n'将合并所有文件): ").strip().lower()
            default_files = files if choice != 'n' else all_files
        else:
            default_files = files if files else all_files

        # 再询问是否手动选择
        manual_choice = input("是否手动选择要合并的文件？(y/N): ").strip().lower()
        if manual_choice == 'y':
            print("请输入要合并的序号（用逗号分隔，支持范围，如 1,3,5-7）。直接回车将使用默认选择：")
            selection = input("序号：").strip()
            if selection:
                idxs = parse_selection(selection, upper_bound=len(display_files))
                if idxs:
                    files = [display_files[i] for i in idxs]
                else:
                    print("⚠️ 未解析到有效序号，继续使用默认选择。")
                    files = default_files
            else:
                files = default_files
        else:
            files = default_files

        print(f"\n🔎 本次将要合并的文件：")
        for f in files:
            print("   •", os.path.basename(f))

        if not files:
            print("❌ 未找到可合并的视频文件")
            return False

        # 断点续传：若检查到上次记录，询问是否继续
        state = load_checkpoint()
        resuming = False
        if state:
            ans = input("检测到上次未完成的合并，是否从断点继续？(Y/n): ").strip().lower()
            if ans != 'n':
                resuming = True
                files = state.get('source_files', files)
                encoder = state.get('encoder', encoder)
                print("🧷 已载入断点记录，将从上次进度继续。")
            else:
                clear_checkpoint_and_workdir()

        if encoder is None:
            encoder = choose_encoder()
        else:
            print(f"🧠 合并流程全程将使用指定编码器：{encoder}")

        # 询问断点保存间隔（按处理片段数）
        try:
            save_interval = input("断点保存间隔（每处理多少个片段保存一次，默认1）：").strip()
            save_interval_clips = int(save_interval) if save_interval else 1
            if save_interval_clips <= 0:
                save_interval_clips = 1
        except Exception:
            save_interval_clips = 1

        # 在源目录内直接工作，避免复制源文件
        if download_dir is None:
            # 若调用端未提供目录，则用所有文件的共同父目录
            common_dir = os.path.dirname(files[0]) if files else project_root()
        else:
            common_dir = os.path.abspath(download_dir)
        tmpdir = work_dir_path(common_dir)
        os.makedirs(tmpdir, exist_ok=True)
        print(f"📁 使用工作目录：{tmpdir}")
        tmp_files: List[str] = list(files)
        subtitle_entries: List[tuple] = []
        gap = os.path.join(tmpdir, 'gap.ts')
        print("🎨 生成2秒无声黑屏（TS 容器）...")
        gap_cmd = ['ffmpeg', '-y']
        if encoder.endswith('_vaapi'):
            gap_cmd += ['-vaapi_device', '/dev/dri/renderD128']
        elif encoder.endswith('_qsv'):
            gap_cmd += ['-hwaccel', 'qsv']
        gap_cmd += [
            '-f', 'lavfi', '-i', f"color=c=black:s=1920x1080:d=2:r={TRANSCODE_PARAMS['fps']}",
            '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
        ]
        if encoder.endswith('_vaapi'):
            gap_cmd += ['-vf', 'format=nv12,hwupload']
        elif encoder.endswith('_qsv'):
            gap_cmd += ['-vf', 'format=nv12,hwupload=extra_hw_frames=64']
        gap_cmd += [
            '-c:v', encoder,
        ]
        if not (encoder.endswith('_vaapi') or encoder.endswith('_qsv')):
            gap_cmd += ['-pix_fmt', TRANSCODE_PARAMS['pix_fmt']]
        gap_cmd += [
            '-c:a', 'aac',
            '-b:a', TRANSCODE_PARAMS['audio_bitrate'],
            '-t', '2',
            '-f', 'mpegts',
            gap
        ]
        if not os.path.exists(gap):
            run_ffmpeg(gap_cmd)

        clip_durations: List[float] = []
        processed_indices: List[int] = []
        ts_paths: Dict[int, str] = {}
        if resuming and state:
            processed_indices = state.get('processed_indices', [])
            ts_paths = {int(k): v for k, v in state.get('ts_paths', {}).items()}
            for i in processed_indices:
                d = get_media_duration_seconds(ts_paths.get(i, ''))
                if d > 0:
                    clip_durations.append(d)
        for i, f in enumerate(tmp_files):
            print(f"\n🎞️  [{i+1}/{len(tmp_files)}] 转码视频：{os.path.basename(f)}")
            print(f"    ➡️ 本视频实际使用编码器：{encoder}")
            # 输出片段仍放在工作目录，避免污染源目录
            ts = os.path.join(tmpdir, f"clip_{i:03d}.ts")

            subtitle = find_subtitle(files[i])
            if subtitle:
                subtitle_entries.append((subtitle, i))

            res = get_video_resolution(f)
            width, height = res if res else (1920, 1080)
            vf_filters: List[str] = []
            if width != 1920 or height != 1080:
                vf_filters.append("scale=1920:1080:force_original_aspect_ratio=decrease")
                vf_filters.append("pad=1920:1080:(ow-iw)/2:(oh-ih)/2")
            vf_filters.append(f"fps={TRANSCODE_PARAMS['fps']}")
            print(f"    ➡️ 视频滤镜: {','.join(vf_filters)}")

            cmd: List[str] = ['ffmpeg', '-y']
            if encoder.endswith('_vaapi'):
                cmd += ['-vaapi_device', '/dev/dri/renderD128']
            elif encoder.endswith('_qsv'):
                cmd += ['-hwaccel', 'qsv']
            cmd += ['-i', f]
            vf_chain = list(vf_filters)
            if encoder.endswith('_vaapi'):
                vf_chain += ['format=nv12', 'hwupload']
            elif encoder.endswith('_qsv'):
                vf_chain += ['format=nv12', 'hwupload=extra_hw_frames=64']
            cmd += ['-vf', ','.join(vf_chain)]
            cmd += [
                '-r', str(TRANSCODE_PARAMS['fps']),
                '-vsync', 'cfr',
            ]
            if not (encoder.endswith('_vaapi') or encoder.endswith('_qsv')):
                cmd += ['-pix_fmt', TRANSCODE_PARAMS['pix_fmt']]
            cmd += [
                '-c:v', encoder,
                '-b:v', TRANSCODE_PARAMS['bitrate'],
                '-c:a', 'aac',
                '-b:a', TRANSCODE_PARAMS['audio_bitrate'],
                '-f', 'mpegts',
                ts
            ]
            run_ffmpeg(cmd)
            duration = get_media_duration_seconds(ts)
            clip_durations.append(duration)
            processed_indices.append(i)
            ts_paths[i] = ts

            if len(processed_indices) % save_interval_clips == 0:
                save_checkpoint({
                    'encoder': encoder,
                    'source_files': files,
                    'work_dir': tmpdir,
                    'gap': gap,
                    'processed_indices': processed_indices,
                    'ts_paths': {str(k): v for k, v in ts_paths.items()},
                })

                # 间隔在最终合并列表阶段以 gap.ts 形式插入

            output = os.path.abspath("output_final_merged.mp4")
            concat_file = os.path.join(tmpdir, "concat_list.txt")
            print("📄 生成合并列表文件...")
            with open(concat_file, "w", encoding="utf-8") as f:
                for i in range(len(files)):
                    ts_abs = os.path.abspath(ts_paths.get(i, os.path.join(tmpdir, f"clip_{i:03d}.ts")))
                    f.write(f"file '{ts_abs}'\n")
                    if i < len(files) - 1:
                        f.write(f"file '{os.path.abspath(gap)}'\n")

            print("🔗 开始合并所有片段...")
            try:
                run_ffmpeg([
                    'ffmpeg', '-y',
                    '-fflags', '+genpts',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', concat_file,
                    '-c', 'copy',
                    '-bsf:a', 'aac_adtstoasc',
                    '-movflags', '+faststart',
                    output
                ])
            except Exception:
                print("⚠️ 直接拷贝合并失败，回退到重编码合并（保证时间戳单调）...")
                reenc_cmd: List[str] = ['ffmpeg', '-y']
                if encoder.endswith('_vaapi'):
                    reenc_cmd += ['-vaapi_device', '/dev/dri/renderD128']
                elif encoder.endswith('_qsv'):
                    reenc_cmd += ['-hwaccel', 'qsv']
                reenc_cmd += [
                    '-fflags', '+genpts',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', concat_file,
                    '-c:v', encoder,
                    '-r', str(TRANSCODE_PARAMS['fps']),
                ]
                if not (encoder.endswith('_vaapi') or encoder.endswith('_qsv')):
                    reenc_cmd += ['-pix_fmt', TRANSCODE_PARAMS['pix_fmt']]
                reenc_cmd += [
                    '-c:a', 'aac',
                    '-b:a', TRANSCODE_PARAMS['audio_bitrate'],
                    '-movflags', '+faststart',
                    output
                ]
                run_ffmpeg(reenc_cmd)
            print(f"\n✅ 合并完成：{output}")
            clear_checkpoint_and_workdir(common_dir)

            merged_subtitle = None
            if subtitle_entries:
                merged_subtitle = os.path.splitext(output)[0] + ".ass"
                print(f"📝 正在按精确累计时长合并字幕，并包含每段之间的 2 秒间隔...")
                merge_ass_with_offsets(subtitle_entries, clip_durations, gap_seconds=2.0, merged_subtitle_path=merged_subtitle)
                print(f"✅ 字幕合并完成：{merged_subtitle}")
            else:
                print("ℹ️ 未检测到可合并的字幕文件。")

            audio_path = os.path.splitext(output)[0] + ".mp3"
            print(f"🎵 正在分离音轨到 {audio_path} ...")
            run_ffmpeg([
                'ffmpeg', '-y', '-i', output, '-vn', '-acodec', 'libmp3lame', '-b:a', '320k', audio_path
            ])
            print(f"✅ 音轨分离完成：{audio_path}")

            print("\n📢 合并已完成，请输入合并后视频的新文件名（不含路径和扩展名，自动保存在脚本同一目录下）：")
            while True:
                new_name = input("请输入文件名（如 myvideo）：").strip()
                if new_name and all(c not in new_name for c in r'\/:*?"<>|'):
                    break
                print("❌ 文件名无效，请重新输入（不能包含特殊字符）")
            base_dir = os.path.dirname(os.path.abspath(__file__))

            video_target = move_file(output, base_dir, new_name)
            if video_target:
                print(f"✅ 视频已保存为：{video_target}")
                if merged_subtitle:
                    subtitle_target = move_file(merged_subtitle, base_dir, new_name)
                    if subtitle_target:
                        print(f"✅ 字幕已保存为：{subtitle_target}")
                audio_target = move_file(audio_path, base_dir, new_name)
                if audio_target:
                    print(f"✅ 音频已保存为：{audio_target}")

            print("\n🎉 合并及保存全部完成！文件均已保存在脚本同一目录下。")
            return True
    except Exception as e:
        print(f"❌ 程序运行失败：{e}")
        return False
