import os
import shutil
from tempfile import TemporaryDirectory
from typing import List, Tuple

from utils import (
    get_video_resolution,
    detect_available_encoders,
    select_best_hevc_encoder,
    get_video_files,
    run_ffmpeg,
    insert_gap,
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
                if not wrote_header:
                    fout.write(line)
                    if line.strip().lower() == "[events]":
                        in_events = True
                    continue
                if not in_events:
                    if line.strip().lower() == "[events]":
                        fout.write(line)
                        in_events = True
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
            if not wrote_header:
                wrote_header = True


def merge_videos_with_best_hevc(download_dir: str | None = None, encoder: str | None = None, start_time: float | None = None, end_time: float | None = None) -> bool:
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

        manual_selection_allowed = True
        if files and len(files) != len(all_files):
            print(f"\n detected {len(files)} new file(s).")
            choice = input("是否只合并新增文件？(Y/n，输入'n'将合并所有文件): ").strip().lower()
            if choice != 'n':
                # 用户选择只合并新增文件：直接使用新增文件列表，并且不再询问手动选择
                manual_selection_allowed = False
                print(f"📝 将合并 {len(files)} 个新增文件")
            else:
                files = all_files
                print("📝 将合并所有视频文件")
        elif files:
            print(f"📝 默认合并 {len(files)} 个文件")
        else:
            print("📝 将合并所有找到的视频文件")

        # 允许用户手动选择要合并的文件（仅当未选择“只合并新增”时）
        if manual_selection_allowed:
            manual_choice = input("是否手动选择要合并的文件？(y/N): ").strip().lower()
            if manual_choice == 'y':
                print("请输入要合并的序号（用逗号分隔，支持范围，如 1,3,5-7）。直接回车将使用上一步选择：")
                selection = input("序号：").strip()
                if selection:
                    idxs = parse_selection(selection, upper_bound=len(display_files))
                    if idxs:
                        files = [display_files[i] for i in idxs]
                        print("📝 将按以下顺序合并（手动选择）：")
                        for f in files:
                            print("   •", os.path.basename(f))
                    else:
                        print("⚠️ 未解析到有效序号，继续使用上一步选择。")

        print(f"\n🔎 本次将要合并的文件：")
        for f in files:
            print("   •", os.path.basename(f))

        if not files:
            print("❌ 未找到可合并的视频文件")
            return False

        if encoder is None:
            encoder = choose_encoder()
        else:
            print(f"🧠 合并流程全程将使用指定编码器：{encoder}")

        with TemporaryDirectory() as tmpdir:
            print(f"📁 正在复制待合并文件到临时目录：{tmpdir}")
            tmp_files: List[str] = []
            for f in files:
                dst = os.path.join(tmpdir, os.path.basename(f))
                shutil.copy2(f, dst)
                tmp_files.append(dst)

            concat_list: List[str] = []
            subtitle_entries: List[tuple] = []
            gap = os.path.join(tmpdir, 'gap.ts')
            print("🎨 生成2秒无声黑屏（TS 容器）...")
            run_ffmpeg([
                'ffmpeg', '-y',
                '-f', 'lavfi', '-i', f"color=c=black:s=1920x1080:d=2:r={TRANSCODE_PARAMS['fps']}",
                '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
                '-c:v', encoder,
                '-pix_fmt', TRANSCODE_PARAMS['pix_fmt'],
                '-c:a', 'aac',
                '-b:a', TRANSCODE_PARAMS['audio_bitrate'],
                '-t', '2',
                '-f', 'mpegts',
                gap
            ])

            clip_durations: List[float] = []
            for i, f in enumerate(tmp_files):
                print(f"\n🎞️  [{i+1}/{len(tmp_files)}] 转码视频：{os.path.basename(f)}")
                print(f"    ➡️ 本视频实际使用编码器：{encoder}")
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

                cmd = [
                    'ffmpeg', '-y',
                    '-i', f,
                    '-vf', ','.join(vf_filters),
                    '-r', str(TRANSCODE_PARAMS['fps']),
                    '-vsync', 'cfr',
                    '-pix_fmt', TRANSCODE_PARAMS['pix_fmt'],
                    '-c:v', encoder,
                    '-b:v', TRANSCODE_PARAMS['bitrate'],
                    '-c:a', 'aac',
                    '-b:a', TRANSCODE_PARAMS['audio_bitrate'],
                    '-f', 'mpegts',
                    ts
                ]
                run_ffmpeg(cmd)
                concat_list.append(ts)
                duration = get_media_duration_seconds(ts)
                clip_durations.append(duration)

                if i < len(tmp_files) - 1:
                    insert_gap(concat_list, tmpdir, gap, i)

            output = os.path.abspath("output_final_merged.mp4")
            concat_file = os.path.join(tmpdir, "concat_list.txt")
            print("📄 生成合并列表文件...")
            with open(concat_file, "w", encoding="utf-8") as f:
                for ts in concat_list:
                    f.write(f"file '{os.path.abspath(ts)}'\n")

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
                run_ffmpeg([
                    'ffmpeg', '-y',
                    '-fflags', '+genpts',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', concat_file,
                    '-c:v', encoder,
                    '-r', str(TRANSCODE_PARAMS['fps']),
                    '-pix_fmt', TRANSCODE_PARAMS['pix_fmt'],
                    '-c:a', 'aac',
                    '-b:a', TRANSCODE_PARAMS['audio_bitrate'],
                    '-movflags', '+faststart',
                    output
                ])
            print(f"\n✅ 合并完成：{output}")

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
