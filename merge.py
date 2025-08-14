import os
from typing import List, Dict
import subprocess

from utils import (
    get_video_resolution,
    get_video_files,
    move_file,
    get_media_duration_seconds,
    ass_time_add,
    get_last_download_files,
)

from moviepy import AudioClip


def choose_encoder() -> str:
    # 检测可用的硬件编码器
    import subprocess
    import platform
    
    system = platform.system().lower()
    if 'windows' in system:
        candidates = {
            'h264_nvenc': 'NVIDIA H.264 (NVENC)',
            'hevc_nvenc': 'NVIDIA H.265 (NVENC)',
            'h264_amf': 'AMD H.264 (AMF)',
            'hevc_amf': 'AMD H.265 (AMF)',
            'h264_qsv': 'Intel H.264 (QSV)',
            'hevc_qsv': 'Intel H.265 (QSV)',
        }
    elif 'linux' in system:
        candidates = {
            'h264_nvenc': 'NVIDIA H.264 (NVENC)',
            'hevc_nvenc': 'NVIDIA H.265 (NVENC)',
            'h264_amf': 'AMD H.264 (AMF)',
            'hevc_amf': 'AMD H.265 (AMF)',
            'h264_vaapi': 'VAAPI H.264',
            'hevc_vaapi': 'VAAPI H.265',
            'h264_qsv': 'Intel H.264 (QSV)',
            'hevc_qsv': 'Intel H.265 (QSV)',
        }
    elif 'darwin' in system:
        candidates = {
            'h264_videotoolbox': 'Apple H.264 (VideoToolbox)',
            'hevc_videotoolbox': 'Apple H.265 (VideoToolbox)',
        }
    else:
        candidates = {}
    
    # 添加 CPU 编码器作为备选
    candidates.update({'libx264': 'CPU H.264', 'libx265': 'CPU H.265'})
    
    # 检测可用的编码器
    available = []
    try:
        result = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            ffmpeg_encoders = result.stdout.lower()
            for enc, desc in candidates.items():
                if enc in ffmpeg_encoders:
                    available.append((enc, desc))
    except Exception:
        pass
    
    if not available:
        available = [('libx264', 'CPU H.264'), ('libx265', 'CPU H.265')]
    
    print("\n可用的编码器列表：")
    for idx, (enc, desc) in enumerate(available):
        print(f"  {idx+1}. {enc} - {desc}")
    print("按回车直接使用推荐编码器（自动优先硬件）：")
    choice = input("请选择编码器编号（如 1），或直接回车：").strip()
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(available):
            print(f"你选择了编码器：{available[idx][0]} - {available[idx][1]}")
            return available[idx][0]
        else:
            print("无效编号，使用默认推荐编码器。")
    
    # 自动选择最佳编码器（优先硬件）
    priority = ['hevc_nvenc', 'hevc_amf', 'hevc_qsv', 'hevc_vaapi', 'hevc_videotoolbox', 'libx265', 'h264_nvenc', 'h264_amf', 'h264_qsv', 'h264_vaapi', 'h264_videotoolbox', 'libx264']
    for enc in priority:
        for available_enc, _ in available:
            if enc == available_enc:
                print(f"🎯 自动选择编码器: {enc}")
                return enc
    
    # 默认使用 libx264
    encoder = 'libx264'
    print(f"自动选择编码器：{encoder}")
    return encoder


TRANSCODE_PARAMS = {
    'fps': 60,
    'bitrate': '2M',
    'audio_bitrate': '320k',
    'pix_fmt': 'yuv420p'
}


def find_subtitle(video_path: str) -> str | None:
    dirname = os.path.dirname(video_path)
    basename = os.path.splitext(os.path.basename(video_path))[0]
    subtitle_path = os.path.join(dirname, basename + ".ass")
    if os.path.isfile(subtitle_path):
        return subtitle_path
    subtitle_extensions = ['.ass', '.srt', '.vtt', '.sub']
    for ext in subtitle_extensions:
        alt_subtitle_path = os.path.join(dirname, basename + ext)
        if os.path.isfile(alt_subtitle_path):
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

import os
from PIL import Image, ImageDraw, ImageFont
import subprocess

# Check if moviepy is available
try:
    from moviepy import ImageClip, AudioFileClip, VideoFileClip, concatenate_videoclips, ImageSequenceClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    print("警告：未安装 moviepy 库，部分功能可能无法使用。")
    print("请运行 'pip install -r requirements.txt' 安装所有依赖。")


def generate_gap_segment(tmpdir, index, video_name, fontfile="C:/Windows/Fonts/msyh.ttc"):
    if not MOVIEPY_AVAILABLE:
        raise ImportError("moviepy 库未安装，无法生成间隔片段。请运行 'pip install -r requirements.txt'")
    """
    使用 Pillow 生成 2 秒的间隔视频，显示居中的视频名称（淡入淡出效果）
    """
    gap_seg = os.path.join(tmpdir, f'gap_{index:03d}.mp4')  # 改为 MP4 格式
    
    # 确保字体文件存在
    if not os.path.exists(fontfile):
        fontfile = "C:/Windows/Fonts/arial.ttf"  # 回退到默认字体
    if not os.path.exists(fontfile):
        fontfile = None  # 使用默认字体
    
    # 创建空白帧图像
    width, height = 1920, 1080
    duration = 2.0
    fps = TRANSCODE_PARAMS['fps']
    
    # 创建临时图像文件夹
    temp_frames_dir = os.path.join(tmpdir, f'frames_gap_{index:03d}')
    os.makedirs(temp_frames_dir, exist_ok=True)
    
    # 生成帧图像
    for frame in range(int(duration * fps)):
        t = frame / fps
        # 创建黑色背景图像
        image = Image.new('RGB', (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # 计算透明度（淡入淡出）
        if t < 0.5:
            alpha = int(255 * t * 2)
        elif t > 1.5:
            alpha = int(255 * (2 - t * 2))
        else:
            alpha = 255
            
        # 添加文字（白色）
        try:
            if fontfile:
                font = ImageFont.truetype(fontfile, 48)
            else:
                font = ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()
        
        # 使用新的方法获取文本尺寸（兼容新版本PIL）
        try:
            # 新版本PIL使用textlength和getbbox
            bbox = draw.textbbox((0, 0), video_name, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except AttributeError:
            # 旧版本PIL使用textsize
            text_width, text_height = draw.textsize(video_name, font=font)
        
        position = ((width - text_width) // 2, (height - text_height) // 2)
        
        # 绘制文本，应用透明度
        draw.text(position, video_name, fill=(alpha, alpha, alpha), font=font)
        
        # 保存帧
        frame_path = os.path.join(temp_frames_dir, f"frame_{frame:04d}.png")
        image.save(frame_path)
    
    # 创建视频片段
    image_files = [os.path.join(temp_frames_dir, f"frame_{i:04d}.png") for i in range(int(duration * fps))]
    
    # 创建静音音频（直接用moviepy生成）
    duration = 2.0
    fps = TRANSCODE_PARAMS['fps']
    def make_silence(t):
        return 0.0
    audio = AudioClip(make_silence, duration=duration, fps=44100)
    
    # 从图像序列创建视频片段
    clip = ImageSequenceClip(image_files, fps=fps)
    
    # 写入文件（直接包含音频）
    if audio:
        clip.write_videofile(gap_seg, fps=fps, codec='libx264', audio_codec='aac', bitrate="1000k", audio=audio)
    else:
        clip.write_videofile(gap_seg, fps=fps, codec='libx264', audio_codec='aac', bitrate="1000k")
    
    # 清理临时文件
    try:
        for f in os.listdir(temp_frames_dir):
            os.remove(os.path.join(temp_frames_dir, f))
        os.rmdir(temp_frames_dir)
    except Exception:
        pass
    
    return gap_seg

def merge_videos_with_best_hevc(download_dir: str | None = None, encoder: str | None = None) -> bool:
    if not MOVIEPY_AVAILABLE:
        print("❌ moviepy 库未安装，无法执行视频合并功能。")
        print("请运行 'pip install -r requirements.txt' 安装所有依赖。")
        return False
    def work_dir_path(base_dir: str) -> str:
        # 在源目录下创建工作目录，避免跨盘复制，提升性能
        return os.path.join(base_dir, '.merge_work')
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
        just_new_only = False
        if files and len(files) != len(all_files):
            print(f"\n detected {len(files)} new file(s).")
            choice = input("是否只合并新增文件？(Y/n，输入'n'将合并所有文件): ").strip().lower()
            if choice != 'n':
                default_files = files
                just_new_only = True
            else:
                default_files = all_files
        else:
            default_files = files if files else all_files

        # 若已选择“只合并新增文件”，则不再进行手动选择
        if not just_new_only:
            manual_choice = input("是否手动选择要合并的文件？(y/N): ").strip().lower()
            if manual_choice == 'y':
                print("请输入要合并的序号（用逗号分隔，支持范围，如 1,3,5-7）。")
                print("直接回车确认当前选择；继续输入可追加选择：")
                selected_indices: List[int] = []
                while True:
                    selection = input("序号（回车确认）：").strip()
                    if not selection:
                        break
                    idxs = parse_selection(selection, upper_bound=len(display_files))
                    if not idxs:
                        print("⚠️ 未解析到有效序号，请重新输入或直接回车确认。")
                        continue
                    for i in idxs:
                        if i not in selected_indices:
                            selected_indices.append(i)
                    # 显示当前选择摘要
                    if selected_indices:
                        print("📝 当前已选择：")
                        for i in selected_indices:
                            print(f"   • {os.path.basename(display_files[i])}")
                if selected_indices:
                    files = [display_files[i] for i in selected_indices]
                else:
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

        if encoder is None:
            encoder = choose_encoder()
        else:
            print(f"🧠 合并流程全程将使用指定编码器：{encoder}")

        # 在源目录内直接工作，避免复制源文件
        if download_dir is None:
            # 若调用端未提供目录，则用所有文件的共同父目录
            common_dir = os.path.dirname(files[0]) if files else os.path.dirname(os.path.abspath(__file__))
        else:
            common_dir = os.path.abspath(download_dir)
        tmpdir = work_dir_path(common_dir)
        os.makedirs(tmpdir, exist_ok=True)
        # 静默工作目录日志
        tmp_files: List[str] = list(files)
        subtitle_entries: List[tuple] = []
        # 为每个视频生成带文件名的间隔片段（每个视频前都加）
        gap_segments = []
        for i, file_path in enumerate(files):
            video_name = os.path.splitext(os.path.basename(file_path))[0]
            print(f"🎨 生成间隔片段 {i+1}/{len(files)}：{video_name}")
            try:
                seg_path = generate_gap_segment(tmpdir, i, video_name)
                gap_segments.append(seg_path)
            except Exception as e:
                print(f"⚠️ 生成间隔片段失败：{e}")
                raise
        clip_durations: List[float] = []
        ts_paths: Dict[int, str] = {}
        for i, f in enumerate(tmp_files):
            print(f"\n🎞️  [{i+1}/{len(tmp_files)}] 转码视频：{os.path.basename(f)}")
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
            cmd: List[str] = ['ffmpeg', '-y']
            if encoder.endswith('_vaapi'):
                from utils import get_vaapi_device_path
                vaapi_dev = get_vaapi_device_path()
                if vaapi_dev:
                    cmd += ['-vaapi_device', vaapi_dev]
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
            subprocess.run(cmd, check=True)
            duration = get_media_duration_seconds(ts)
            clip_durations.append(duration)
            ts_paths[i] = ts

        # 创建最终的视频剪辑
        final_clips = []
        for i, f in enumerate(tmp_files):
            # 添加间隔片段（在每个视频前）
            if i < len(gap_segments):
                try:
                    final_clips.append(VideoFileClip(gap_segments[i]))
                except Exception as e:
                    print(f"⚠️ 加载间隔片段失败：{e}")
            # 添加转码后的视频片段
            try:
                final_clips.append(VideoFileClip(ts_paths[i]))
            except Exception as e:
                print(f"⚠️ 加载视频片段失败：{e}")

        if not final_clips:
            print("❌ 没有可用的视频片段")
            return False

        print("\n🎬 正在拼接视频...")
        final_video = concatenate_videoclips(final_clips, method="compose")
        
        # 输出文件路径
        output = os.path.join(tmpdir, "merged.mp4")
        
        # 写入最终视频文件
        if encoder.startswith(('h264_', 'hevc_')) and encoder != 'libx264' and encoder != 'libx265':
            # 使用硬件编码器，先用 moviepy 生成临时文件，再用 ffmpeg 转码
            temp_output = os.path.join(tmpdir, "temp_merged.mp4")
            final_video.write_videofile(
                temp_output,
                fps=TRANSCODE_PARAMS['fps'],
                codec='libx264',  # 临时使用 CPU 编码
                audio_codec='aac',
                bitrate="5000k",
                preset="ultrafast",
                threads=4
            )
            
            # 使用 ffmpeg 进行硬件编码转码
            print(f"🔄 使用硬件编码器 {encoder} 进行最终转码...")
            import subprocess
            cmd = ['ffmpeg', '-y', '-i', temp_output]
            
            # 根据编码器类型添加硬件加速参数
            if encoder.endswith('_nvenc'):
                cmd += ['-c:v', encoder, '-preset', 'p7', '-tune', 'hq']
            elif encoder.endswith('_amf'):
                cmd += ['-c:v', encoder, '-quality', 'quality']
            elif encoder.endswith('_qsv'):
                cmd += ['-c:v', encoder, '-preset', 'medium']
            elif encoder.endswith('_vaapi'):
                from utils import get_vaapi_device_path
                vaapi_dev = get_vaapi_device_path()
                if vaapi_dev:
                    cmd += ['-c:v', encoder, '-vaapi_device', vaapi_dev]
                else:
                    cmd += ['-c:v', encoder]
            elif encoder.endswith('_videotoolbox'):
                cmd += ['-c:v', encoder]
            else:
                cmd += ['-c:v', encoder]
            
            cmd += ['-b:v', '5000k', '-c:a', 'aac', '-b:a', '320k', output]
            
            try:
                subprocess.run(cmd, check=True)
                # 删除临时文件
                if os.path.exists(temp_output):
                    os.remove(temp_output)
            except subprocess.CalledProcessError as e:
                print(f"⚠️ 硬件编码失败，回退到 CPU 编码: {e}")
                # 如果硬件编码失败，直接使用临时文件
                if os.path.exists(temp_output):
                    os.rename(temp_output, output)
        else:
            # 使用 CPU 编码器
            final_video.write_videofile(
                output,
                fps=TRANSCODE_PARAMS['fps'],
                codec=encoder,
                audio_codec='aac',
                bitrate="5000k",
                preset="ultrafast",
                threads=4
            )
        
        merged_subtitle = None
        if subtitle_entries:
            merged_subtitle = os.path.splitext(output)[0] + ".ass"
            print(f"⚠ 正在按精确累计时长合并字幕，并包含每段之间的 2 秒间隔...")
            merge_ass_with_offsets(subtitle_entries, clip_durations, gap_seconds=2.0, merged_subtitle_path=merged_subtitle)
            print(f"✅ 字幕合并完成：{merged_subtitle}")
        else:
            print("ℹ️ 未检测到可合并的字幕文件。")

        audio_path = os.path.splitext(output)[0] + ".mp3"
        # 创建音频文件（使用MoviePy）
        final_video.audio.write_audiofile(audio_path, codec='libmp3lame', bitrate="320k")
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
