import os
from typing import List, Dict
import subprocess
import traceback

from utils import (
    get_video_resolution,
    get_video_files,
    move_file,
    get_media_duration_seconds,
    ass_time_add,
    get_last_download_files,
)

# moviepy 将在需要时延迟导入
MOVIEPY_AVAILABLE = False


def choose_encoder() -> str:
    print("[DEBUG] 开始选择编码器")
    # 检测可用的硬件编码器
    import subprocess
    import platform
    
    system = platform.system().lower()
    print(f"[DEBUG] 系统类型: {system}")
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
    print(f"[DEBUG] 候选编码器: {list(candidates.keys())}")
    
    # 检测可用的编码器
    available = []
    try:
        result = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, timeout=10)
        print(f"[DEBUG] FFmpeg返回码: {result.returncode}")
        if result.returncode == 0:
            ffmpeg_encoders = result.stdout.lower()
            print(f"[DEBUG] FFmpeg编码器列表长度: {len(ffmpeg_encoders)}")
            for enc, desc in candidates.items():
                if enc in ffmpeg_encoders:
                    print(f"[DEBUG] 发现可用编码器: {enc}")
                    available.append((enc, desc))
    except Exception as e:
        print(f"[DEBUG] 检测编码器时出错: {e}")
        traceback.print_exc()
        pass
    
    if not available:
        print("[DEBUG] 未找到可用编码器，使用默认CPU编码器")
        available = [('libx264', 'CPU H.264'), ('libx265', 'CPU H.265')]
    
    print("\n可用的编码器列表：")
    for idx, (enc, desc) in enumerate(available):
        print(f"  {idx+1}. {enc} - {desc}")
    print("按回车直接使用推荐编码器（自动优先硬件）：")
    choice = input("请选择编码器编号（如 1），或直接回车：").strip()
    print(f"[DEBUG] 用户选择: {choice}")
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(available):
            print(f"你选择了编码器：{available[idx][0]} - {available[idx][1]}")
            return available[idx][0]
        else:
            print("无效编号，使用默认推荐编码器。")
    
    # 自动选择最佳编码器（优先硬件）
    priority = ['hevc_nvenc', 'hevc_amf', 'hevc_qsv', 'hevc_vaapi', 'hevc_videotoolbox', 'libx265', 'h264_nvenc', 'h264_amf', 'h264_qsv', 'h264_vaapi', 'h264_videotoolbox', 'libx264']
    print(f"[DEBUG] 编码器优先级: {priority}")
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
    print(f"[DEBUG] 查找字幕文件: {video_path}")
    dirname = os.path.dirname(video_path)
    basename = os.path.splitext(os.path.basename(video_path))[0]
    subtitle_path = os.path.join(dirname, basename + ".ass")
    print(f"[DEBUG] 检查ASS字幕: {subtitle_path}")
    if os.path.isfile(subtitle_path):
        print(f"[DEBUG] 找到ASS字幕")
        return subtitle_path
    subtitle_extensions = ['.ass', '.srt', '.vtt', '.sub']
    for ext in subtitle_extensions:
        alt_subtitle_path = os.path.join(dirname, basename + ext)
        print(f"[DEBUG] 检查字幕: {alt_subtitle_path}")
        if os.path.isfile(alt_subtitle_path):
            print(f"[DEBUG] 找到字幕: {ext}")
            return alt_subtitle_path
    print("[DEBUG] 未找到字幕文件")
    return None


def merge_ass_with_offsets(subtitle_entries: List[tuple], clip_durations: List[float], gap_seconds: float, merged_subtitle_path: str) -> None:
    print(f"[DEBUG] 合并ASS字幕，条目数: {len(subtitle_entries)}, 间隔秒数: {gap_seconds}")
    print(f"[DEBUG] 合并后字幕路径: {merged_subtitle_path}")
    def cumulative_offset_for_index(index: int) -> float:
        if index <= 0:
            return 0.0
        total = sum(clip_durations[:index])
        total += gap_seconds * index
        print(f"[DEBUG] 索引 {index} 的累计偏移: {total} 秒")
        return total

    with open(merged_subtitle_path, "w", encoding="utf-8") as fout:
        wrote_header = False
        for entry_idx, (sub_path, clip_index) in enumerate(subtitle_entries):
            print(f"[DEBUG] 处理字幕条目 {entry_idx}: {sub_path}, 剪辑索引: {clip_index}")
            with open(sub_path, "r", encoding="utf-8") as fin:
                lines = fin.readlines()
            in_events = False
            offset = cumulative_offset_for_index(clip_index)
            for line in lines:
                # 首段：写入头部直到 [Events]，并从此开始处理事件
                if not wrote_header:
                    if line.strip().lower() == "[events]":
                        print(f"[DEBUG] 写入Events头部")
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
                        print(f"[DEBUG] 检测到Events部分")
                        in_events = True
                    continue

                # 进入事件段：去重 Format 行，仅写入对齐后的 Dialogue 与其它事件行
                lower = line.strip().lower()
                if lower.startswith('format:'):
                    continue
                if line.startswith("Dialogue:"):
                    parts = line.split(",", 9)
                    if len(parts) >= 3:
                        old_start = parts[1]
                        old_end = parts[2]
                        parts[1] = ass_time_add(parts[1], offset)
                        parts[2] = ass_time_add(parts[2], offset)
                        print(f"[DEBUG] 时间偏移 {offset} 秒: {old_start} -> {parts[1]}, {old_end} -> {parts[2]}")
                        fout.write(",".join(parts))
                    else:
                        fout.write(line)
                else:
                    fout.write(line)
    print("[DEBUG] 字幕合并完成")


from PIL import Image, ImageDraw, ImageFont
import subprocess

# Check if moviepy is available
MOVIEPY_AVAILABLE = False


def generate_gap_segment(tmpdir, index, video_name, fontfile=None):
    """
    使用 Pillow 生成 2 秒的间隔视频，显示居中的视频名称（淡入淡出效果）
    """
    print(f"[DEBUG] 生成间隔片段，索引: {index}, 名称: {video_name}")
    # 检查 moviepy 是否可用
    try:
        print("[DEBUG] 尝试导入moviepy")
        from moviepy import ImageClip, AudioFileClip, VideoFileClip, concatenate_videoclips, ImageSequenceClip
        global MOVIEPY_AVAILABLE
        MOVIEPY_AVAILABLE = True
        print("[DEBUG] Moviepy导入成功")
    except ImportError:
        global MOVIEPY_AVAILABLE
        MOVIEPY_AVAILABLE = False
        print("[DEBUG] Moviepy导入失败")
        raise ImportError("moviepy 库未安装，无法生成间隔片段。请运行 'pip install -r requirements.txt'")
    
    gap_seg = os.path.join(tmpdir, f'gap_{index:03d}.mp4')  # 改为 MP4 格式
    print(f"[DEBUG] 间隔片段路径: {gap_seg}")
    
    # 确定字体文件路径（跨平台）
    if fontfile is None:
        import platform
        system = platform.system().lower()
        print(f"[DEBUG] 系统类型: {system}")
        if 'windows' in system:
            fontfile = "C:/Windows/Fonts/msyh.ttc"
            if not os.path.exists(fontfile):
                fontfile = "C:/Windows/Fonts/arial.ttf"
        elif 'darwin' in system:  # macOS
            fontfile = "/System/Library/Fonts/PingFang.ttc"
            if not os.path.exists(fontfile):
                fontfile = "/System/Library/Fonts/Arial.ttf"
        else:  # Linux
            # 尝试几种常见的字体路径
            possible_fonts = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/TTF/arial.ttf",
                "/usr/share/fonts/truetype/arial.ttf"
            ]
            for font_path in possible_fonts:
                if os.path.exists(font_path):
                    fontfile = font_path
                    print(f"[DEBUG] 找到字体文件: {font_path}")
                    break
    
    # 如果仍然没有找到字体文件，使用默认字体
    if fontfile and not os.path.exists(fontfile):
        print(f"[DEBUG] 字体文件不存在: {fontfile}")
        fontfile = None  # 使用默认字体
    
    # 创建空白帧图像
    width, height = 1920, 1080
    duration = 2.0
    fps = TRANSCODE_PARAMS['fps']
    print(f"[DEBUG] 视频参数: {width}x{height}, 时长: {duration}秒, FPS: {fps}")
    
    # 创建临时图像文件夹
    temp_frames_dir = os.path.join(tmpdir, f'frames_gap_{index:03d}')
    print(f"[DEBUG] 临时帧目录: {temp_frames_dir}")
    os.makedirs(temp_frames_dir, exist_ok=True)
    
    # 生成帧图像
    total_frames = int(duration * fps)
    print(f"[DEBUG] 需要生成帧数: {total_frames}")
    for frame in range(total_frames):
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
        print(f"[DEBUG] 帧 {frame}, 时间: {t}, 透明度: {alpha}")
            
        # 添加文字（白色）
        try:
            if fontfile:
                print(f"[DEBUG] 使用字体文件: {fontfile}")
                font = ImageFont.truetype(fontfile, 48)
            else:
                print("[DEBUG] 使用默认字体")
                font = ImageFont.load_default()
        except Exception as e:
            print(f"[DEBUG] 字体加载失败，使用默认字体: {e}")
            font = ImageFont.load_default()
        
        # 使用新的方法获取文本尺寸（兼容新版本PIL）
        try:
            # 新版本PIL使用textlength和getbbox
            bbox = draw.textbbox((0, 0), video_name, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except:
            # 如果失败，默认一个尺寸
            text_width, text_height = 100, 20
        print(f"[DEBUG] 文本尺寸: {text_width}x{text_height}")
        
        position = ((width - text_width) // 2, (height - text_height) // 2)
        print(f"[DEBUG] 文本位置: {position}")
        
        # 绘制文本，应用透明度
        draw.text(position, video_name, fill=(alpha, alpha, alpha), font=font)
        
        # 保存帧
        frame_path = os.path.join(temp_frames_dir, f"frame_{frame:04d}.png")
        print(f"[DEBUG] 保存帧: {frame_path}")
        image.save(frame_path)
    
    # 创建视频片段
    image_files = [os.path.join(temp_frames_dir, f"frame_{i:04d}.png") for i in range(int(duration * fps))]
    print(f"[DEBUG] 图像文件列表生成完成，共 {len(image_files)} 个文件")
    
    # 创建静音音频（直接用moviepy生成）
    duration = 2.0
    fps = TRANSCODE_PARAMS['fps']
    def make_silence(t):
        return 0.0
    try:
        from moviepy import AudioClip
        print("[DEBUG] 创建静音音频")
        audio = AudioClip(make_silence, duration=duration, fps=44100)
    except ImportError:
        print("[DEBUG] 无法创建音频")
        audio = None
    
    # 从图像序列创建视频片段
    print("[DEBUG] 从图像序列创建视频剪辑")
    clip = ImageSequenceClip(image_files, fps=fps)
    
    # 写入文件（直接包含音频）
    print(f"[DEBUG] 写入视频文件: {gap_seg}")
    if audio:
        clip.write_videofile(gap_seg, fps=fps, codec='libx264', audio_codec='aac', bitrate="1000k", audio=audio)
    else:
        clip.write_videofile(gap_seg, fps=fps, codec='libx264', audio_codec='aac', bitrate="1000k")
    
    # 清理临时文件
    try:
        print("[DEBUG] 清理临时文件")
        for f in os.listdir(temp_frames_dir):
            os.remove(os.path.join(temp_frames_dir, f))
        os.rmdir(temp_frames_dir)
    except Exception as e:
        print(f"[DEBUG] 清理临时文件时出错: {e}")
        pass
    
    print(f"[DEBUG] 间隔片段生成完成: {gap_seg}")
    return gap_seg

def merge_videos_with_best_hevc(download_dir: str | None = None, encoder: str | None = None) -> bool:
    print(f"[DEBUG] 开始合并视频，下载目录: {download_dir}, 编码器: {encoder}")
    # 检查 moviepy 是否可用
    global MOVIEPY_AVAILABLE
    try:
        print("[DEBUG] 检查moviepy是否可用")
        from moviepy import ImageClip, AudioFileClip, VideoFileClip, concatenate_videoclips, ImageSequenceClip
        MOVIEPY_AVAILABLE = True
        print("[DEBUG] Moviepy可用")
    except ImportError as e:
        MOVIEPY_AVAILABLE = False
        print("❌ moviepy 库未安装，无法执行视频合并功能。")
        print("请运行 'pip install -r requirements.txt' 安装所有依赖。")
        print(f"[DEBUG] ImportError: {e}")
        return False
        
    def work_dir_path(base_dir: str) -> str:
        # 在源目录下创建工作目录，避免跨盘复制，提升性能
        path = os.path.join(base_dir, '.merge_work')
        print(f"[DEBUG] 工作目录路径: {path}")
        return path
        
    def parse_selection(selection: str, upper_bound: int) -> List[int]:
        # 解析类似 "1,3,5-7" 的输入，返回去重且按出现顺序的索引（0-based）
        print(f"[DEBUG] 解析用户选择: {selection}, 上限: {upper_bound}")
        tokens = [t.strip() for t in selection.split(',') if t.strip()]
        result: List[int] = []
        seen = set()
        for tok in tokens:
            if '-' in tok:
                a, b = tok.split('-', 1)
                print(f"[DEBUG] 解析范围: {a}-{b}")
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
                print(f"[DEBUG] 解析单个数字: {tok} -> 索引 {idx0}")
                if 0 <= idx0 < upper_bound and idx0 not in seen:
                    seen.add(idx0)
                    result.append(idx0)
        print(f"[DEBUG] 解析结果: {result}")
        return result

    try:
        print("[DEBUG] 获取最后下载的文件")
        files = get_last_download_files()
        if not files:
            download_dir = download_dir or "./download"
            print(f"[DEBUG] 未找到最后下载的文件，从目录获取: {download_dir}")
            files = get_video_files(download_dir)

        print(f"\n🔎 找到以下视频文件：")
        all_files = get_video_files(download_dir) if download_dir else []
        print(f"[DEBUG] 所有文件数量: {len(all_files)}")
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
            print(f"[DEBUG] 用户选择是否只合并新增文件: {choice}")
            if choice != 'n':
                default_files = files
                just_new_only = True
            else:
                default_files = all_files
        else:
            default_files = files if files else all_files

        # 若已选择"只合并新增文件"，则不再进行手动选择
        if not just_new_only:
            manual_choice = input("是否手动选择要合并的文件？(y/N): ").strip().lower()
            print(f"[DEBUG] 用户选择是否手动选择: {manual_choice}")
            if manual_choice == 'y':
                print("请输入要合并的序号（用逗号分隔，支持范围，如 1,3,5-7）。")
                print("直接回车确认当前选择；继续输入可追加选择：")
                selected_indices: List[int] = []
                while True:
                    selection = input("序号（回车确认）：").strip()
                    print(f"[DEBUG] 用户输入选择: {selection}")
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
            print("[DEBUG] 编码器未指定，开始选择")
            encoder = choose_encoder()
        else:
            print(f"🧠 合并流程全程将使用指定编码器：{encoder}")

        # 在源目录内直接工作，避免复制源文件
        if download_dir is None:
            # 若调用端未提供目录，则用所有文件的共同父目录
            common_dir = os.path.dirname(files[0]) if files else os.path.dirname(os.path.abspath(__file__))
        else:
            common_dir = os.path.abspath(download_dir)
        print(f"[DEBUG] 共同目录: {common_dir}")
        tmpdir = work_dir_path(common_dir)
        print(f"[DEBUG] 创建工作目录: {tmpdir}")
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
                traceback.print_exc()
                raise
        clip_durations: List[float] = []
        ts_paths: Dict[int, str] = {}
        for i, f in enumerate(tmp_files):
            print(f"\n🎞️  [{i+1}/{len(tmp_files)}] 转码视频：{os.path.basename(f)}")
            ts = os.path.join(tmpdir, f"clip_{i:03d}.ts")
            print(f"[DEBUG] TS文件路径: {ts}")
            subtitle = find_subtitle(files[i])
            if subtitle:
                print(f"[DEBUG] 找到字幕文件: {subtitle}")
                subtitle_entries.append((subtitle, i))
            res = get_video_resolution(f)
            width, height = res if res else (1920, 1080)
            print(f"[DEBUG] 视频分辨率: {width}x{height}")
            vf_filters: List[str] = []
            if width != 1920 or height != 1080:
                vf_filters.append("scale=1920:1080:force_original_aspect_ratio=decrease")
                vf_filters.append("pad=1920:1080:(ow-iw)/2:(oh-ih)/2")
            vf_filters.append(f"fps={TRANSCODE_PARAMS['fps']}")
            print(f"[DEBUG] 视频滤镜: {vf_filters}")
            cmd: List[str] = ['ffmpeg', '-y']
            if encoder.endswith('_vaapi'):
                from utils import get_vaapi_device_path
                vaapi_dev = get_vaapi_device_path()
                if vaapi_dev:
                    cmd += ['-vaapi_device', vaapi_dev]
                    print(f"[DEBUG] VAAPI设备: {vaapi_dev}")
            elif encoder.endswith('_qsv'):
                cmd += ['-hwaccel', 'qsv']
                print("[DEBUG] QSV硬件加速")
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
            print(f"[DEBUG] FFmpeg命令: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            duration = get_media_duration_seconds(ts)
            print(f"[DEBUG] 剪辑时长: {duration} 秒")
            clip_durations.append(duration)
            ts_paths[i] = ts

        # 创建最终的视频剪辑
        print("[DEBUG] 创建最终视频剪辑")
        final_clips = []
        for i, f in enumerate(tmp_files):
            # 添加间隔片段（在每个视频前）
            if i < len(gap_segments):
                try:
                    print(f"[DEBUG] 加载间隔片段: {gap_segments[i]}")
                    final_clips.append(VideoFileClip(gap_segments[i]))
                except Exception as e:
                    print(f"⚠️ 加载间隔片段失败：{e}")
                    traceback.print_exc()
            # 添加转码后的视频片段
            try:
                print(f"[DEBUG] 加载视频片段: {ts_paths[i]}")
                final_clips.append(VideoFileClip(ts_paths[i]))
            except Exception as e:
                print(f"⚠️ 加载视频片段失败：{e}")
                traceback.print_exc()

        if not final_clips:
            print("❌ 没有可用的视频片段")
            return False

        print("\n🎬 正在拼接视频...")
        final_video = concatenate_videoclips(final_clips, method="compose")
        
        # 输出文件路径
        output = os.path.join(tmpdir, "merged.mp4")
        print(f"[DEBUG] 输出文件路径: {output}")
        
        # 写入最终视频文件
        if encoder.startswith(('h264_', 'hevc_')) and encoder != 'libx264' and encoder != 'libx265':
            # 使用硬件编码器，先用 moviepy 生成临时文件，再用 ffmpeg 转码
            temp_output = os.path.join(tmpdir, "temp_merged.mp4")
            print(f"[DEBUG] 使用硬件编码器，先生成临时文件: {temp_output}")
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
            import subprocess as sp
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
                print(f"[DEBUG] 硬件编码命令: {' '.join(cmd)}")
                sp.run(cmd, check=True)
                # 删除临时文件
                if os.path.exists(temp_output):
                    print(f"[DEBUG] 删除临时文件: {temp_output}")
                    os.remove(temp_output)
            except sp.CalledProcessError as e:
                print(f"⚠️ 硬件编码失败，回退到 CPU 编码: {e}")
                traceback.print_exc()
                # 如果硬件编码失败，直接使用临时文件
                if os.path.exists(temp_output):
                    os.rename(temp_output, output)
        else:
            # 使用 CPU 编码器
            print(f"[DEBUG] 使用CPU编码器: {encoder}")
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
        print(f"[DEBUG] 音频路径: {audio_path}")
        # 创建音频文件（使用MoviePy）
        if final_video.audio is not None:
            final_video.audio.write_audiofile(audio_path, codec='libmp3lame', bitrate="320k")
            print(f"✅ 音轨分离完成：{audio_path}")
        else:
            print("ℹ️ 视频没有音频轨道，跳过音轨分离")

        print("\n📢 合并已完成，请输入合并后视频的新文件名（不含路径和扩展名，自动保存在脚本同一目录下）：")
        while True:
            new_name = input("请输入文件名（如 myvideo）：").strip()
            print(f"[DEBUG] 用户输入文件名: {new_name}")
            if new_name and all(c not in new_name for c in r'\/:*?"<>|'):
                break
            print("❌ 文件名无效，请重新输入（不能包含特殊字符）")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"[DEBUG] 基础目录: {base_dir}")

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
        traceback.print_exc()
        return False