import os
import sys
import json
import platform
import shutil
import subprocess
import traceback
from typing import List, Tuple


def _local_tool_candidates(tool: str) -> list[str]:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"[DEBUG] 查找工具 '{tool}' 的候选路径，基目录: {base_dir}")
    names = [tool]
    if sys.platform.startswith('win'):
        names = [f"{tool}.exe", tool]
    candidates = [os.path.join(base_dir, n) for n in names]
    print(f"[DEBUG] 工具 '{tool}' 的候选路径: {candidates}")
    return candidates


def _resolve_tool(tool: str) -> str | None:
    print(f"[DEBUG] 解析工具: {tool}")
    # 1) PATH 查找
    path = shutil.which(tool)
    print(f"[DEBUG] PATH中查找结果: {path}")
    if path:
        return path
    # 2) 脚本所在目录查找（与程序同目录）
    for cand in _local_tool_candidates(tool):
        print(f"[DEBUG] 检查候选路径: {cand}")
        if os.path.isfile(cand):
            print(f"[DEBUG] 找到工具: {cand}")
            return cand
    print(f"[DEBUG] 未找到工具: {tool}")
    return None


def get_ffmpeg_path() -> str | None:
    path = _resolve_tool('ffmpeg')
    print(f"[DEBUG] FFmpeg路径: {path}")
    return path


def get_ffprobe_path() -> str | None:
    path = _resolve_tool('ffprobe')
    print(f"[DEBUG] FFprobe路径: {path}")
    return path


def get_ffplay_path() -> str | None:
    path = _resolve_tool('ffplay')
    print(f"[DEBUG] FFplay路径: {path}")
    return path


def get_vaapi_device_path() -> str | None:
    """返回可用的 VAAPI render 节点，如 /dev/dri/renderD128。若不可用返回 None。"""
    print(f"[DEBUG] 检查VAAPI设备路径，系统平台: {sys.platform}")
    if not sys.platform.startswith('linux'):
        print("[DEBUG] 非Linux系统，跳过VAAPI设备检查")
        return None
    dri_dir = '/dev/dri'
    try:
        print(f"[DEBUG] 检查DRI目录: {dri_dir}")
        if not os.path.isdir(dri_dir):
            print(f"[DEBUG] DRI目录不存在: {dri_dir}")
            return None
        candidates: List[str] = []
        print(f"[DEBUG] 列出DRI目录内容")
        for name in os.listdir(dri_dir):
            if name.startswith('renderD'):
                candidate_path = os.path.join(dri_dir, name)
                print(f"[DEBUG] 发现renderD设备: {candidate_path}")
                candidates.append(candidate_path)
        candidates.sort()
        result = candidates[0] if candidates else None
        print(f"[DEBUG] 选择的VAAPI设备: {result}")
        return result
    except Exception as e:
        print(f"[DEBUG] 检查VAAPI设备时出错: {e}")
        traceback.print_exc()
        return None


def check_ffmpeg_installed() -> None:
    """检查 ffmpeg/ffprobe 是否可用；优先使用 PATH，其次程序同目录。"""
    print("[DEBUG] 检查FFmpeg安装情况")
    tools = [
        (get_ffmpeg_path(), 'ffmpeg'),
        (get_ffprobe_path(), 'ffprobe')
    ]
    for resolved, name in tools:
        print(f"[DEBUG] 检查工具 {name}，解析路径: {resolved}")
        if not resolved:
            print(f"❌ 未检测到 {name}，请安装或将其与程序放在同一目录后再运行。")
            print("参考: https://ffmpeg.org/download.html 或各平台包管理器。")
            sys.exit(1)
        try:
            print(f"[DEBUG] 测试工具 {name} 是否可执行")
            subprocess.run([resolved, '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            print(f"[DEBUG] 工具 {name} 可执行")
        except Exception as e:
            print(f"❌ {name} 无法执行：{resolved}, 错误: {e}")
            traceback.print_exc()
            sys.exit(1)


def get_media_duration_seconds(path: str) -> float:
    """使用 moviepy 获取媒体时长（秒）。失败返回 0.0。"""
    print(f"[DEBUG] 获取媒体时长: {path}")
    try:
        print("[DEBUG] 尝试导入moviepy.VideoFileClip")
        from moviepy import VideoFileClip
        print("[DEBUG] 成功导入VideoFileClip")
        print("[DEBUG] 打开视频文件")
        clip = VideoFileClip(path)
        duration = clip.duration
        print(f"[DEBUG] 视频时长: {duration} 秒")
        clip.close()
        return duration
    except Exception as e:
        print(f"[DEBUG] 获取媒体时长失败: {e}")
        traceback.print_exc()
        return 0.0


def get_video_resolution(video_path: str):
    """使用 moviepy 获取视频分辨率 (width, height)。失败返回 None。"""
    print(f"[DEBUG] 获取视频分辨率: {video_path}")
    try:
        print("[DEBUG] 尝试导入moviepy.VideoFileClip")
        from moviepy import VideoFileClip
        print("[DEBUG] 成功导入VideoFileClip")
        print("[DEBUG] 打开视频文件")
        clip = VideoFileClip(video_path)
        res = (clip.w, clip.h)
        print(f"[DEBUG] 视频分辨率: {res}")
        clip.close()
        return res
    except Exception as e:
        print(f"[DEBUG] 获取视频分辨率失败: {e}")
        traceback.print_exc()
        return None


def detect_available_encoders() -> List[Tuple[str, str]]:
    print("🔍 正在检测可用的硬件编码器...")
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
        ffmpeg = get_ffmpeg_path() or 'ffmpeg'
        print(f"[DEBUG] 使用FFmpeg路径: {ffmpeg}")
        print("[DEBUG] 获取FFmpeg编码器列表")
        result = subprocess.run(
            [ffmpeg, '-encoders'], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        print(f"[DEBUG] FFmpeg返回码: {result.returncode}")
        if result.returncode == 0:
            ffmpeg_encoders = result.stdout.lower()
            print(f"[DEBUG] FFmpeg编码器列表长度: {len(ffmpeg_encoders)}")
            for enc, desc in candidates.items():
                if enc in ffmpeg_encoders:
                    print(f"[DEBUG] 发现可用编码器: {enc}")
                    available.append((enc, desc))
                else:
                    print(f"[DEBUG] 编码器不可用: {enc}")
        else:
            print(f"[DEBUG] FFmpeg执行失败，错误输出: {result.stderr}")
    except Exception as e:
        print(f"[DEBUG] 获取编码器列表时出错: {e}")
        traceback.print_exc()
        pass
    
    if not available:
        print("[DEBUG] 未找到可用编码器，使用默认CPU编码器")
        available = [('libx264', 'CPU H.264'), ('libx265', 'CPU H.265')]
    
    print("\n可用的编码器列表：")
    for idx, (enc, desc) in enumerate(available):
        print(f"  {idx+1}. {enc} - {desc}")
    return available


def select_best_hevc_encoder(available_encoders=None) -> str:
    print("[DEBUG] 选择最佳HEVC编码器")
    if available_encoders is None:
        print("[DEBUG] 使用自动检测的编码器列表")
        available_encoders = [enc for enc, _ in detect_available_encoders()]
    else:
        print(f"[DEBUG] 使用提供的编码器列表: {available_encoders}")
        available_encoders = [enc for enc, _ in available_encoders]

    priority = [
        'hevc_nvenc', 'hevc_amf', 'hevc_qsv', 'hevc_vaapi', 'hevc_videotoolbox', 'libx265'
    ]
    print(f"[DEBUG] 编码器优先级: {priority}")
    for enc in priority:
        if enc in available_encoders:
            print(f"🎯 自动选择 HEVC 编码器: {enc}")
            return enc
    print("⚠️ 未检测到 HEVC 硬件编码器，使用 libx265")
    return 'libx265'


def get_video_files(directory: str) -> List[str]:
    """获取指定目录下的所有视频文件（按目录枚举顺序，不排序）"""
    print(f"[DEBUG] 获取目录中的视频文件: {directory}")
    if not os.path.exists(directory):
        print(f"[DEBUG] 目录不存在: {directory}")
        return []
        
    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv')
    files = []
    try:
        print(f"[DEBUG] 列出目录内容")
        dir_contents = os.listdir(directory)
        print(f"[DEBUG] 目录中文件数量: {len(dir_contents)}")
        for f in dir_contents:
            if f.lower().endswith(video_extensions):
                full_path = os.path.join(directory, f)
                print(f"[DEBUG] 发现视频文件: {full_path}")
                files.append(full_path)
    except Exception as e:
        print(f"[DEBUG] 列目录时出错: {e}")
        traceback.print_exc()
        
    print(f"[DEBUG] 找到视频文件数量: {len(files)}")
    return files


def run_ffmpeg(cmd: list, timeout_seconds: int | None = None):
    """运行 ffmpeg 命令并检查返回码。使用二进制管道避免编码问题。"""
    print(f"[DEBUG] 运行FFmpeg命令: {' '.join(cmd)}")
    try:
        # 自动解析 ffmpeg 路径（Windows 未在 PATH 且在当前目录的情况）
        if cmd and isinstance(cmd[0], str) and os.path.basename(cmd[0]).lower() in ('ffmpeg', 'ffmpeg.exe'):
            ffmpeg = get_ffmpeg_path() or cmd[0]
            print(f"[DEBUG] 使用FFmpeg路径: {ffmpeg}")
            cmd = [ffmpeg] + cmd[1:]

        # 在 Linux 下，为了确保硬件编解码权限，若非 root 且存在 sudo，则使用 sudo 执行
        if sys.platform.startswith('linux'):
            try:
                is_root = (os.geteuid() == 0)
                print(f"[DEBUG] Linux系统权限检查，是否为root: {is_root}")
            except Exception:
                is_root = False
            if not is_root and shutil.which('sudo'):
                print("[DEBUG] 非root用户且存在sudo，使用sudo执行")
                cmd = ['sudo', '-E'] + cmd

        print(f"[DEBUG] 最终执行命令: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            timeout=timeout_seconds,
        )
        print(f"[DEBUG] 命令执行完成，返回码: {result.returncode}")

        # 如以 sudo 执行，尽量将输出文件归还给当前用户，避免后续操作权限问题
        try:
            if sys.platform.startswith('linux') and shutil.which('sudo'):
                try:
                    is_root = (os.geteuid() == 0)
                except Exception:
                    is_root = False
                if not is_root and result.returncode == 0:
                    # 约定：命令最后一个参数是输出路径（本项目当前所有调用均符合）
                    if cmd and isinstance(cmd[-1], str) and cmd[-1] not in ('-', 'pipe:', '|'):
                        output_path = cmd[-1]
                        print(f"[DEBUG] 检查输出文件权限: {output_path}")
                        if os.path.exists(output_path):
                            uid = os.getuid()
                            gid = os.getgid()
                            print(f"[DEBUG] 修改文件所有者为 {uid}:{gid}")
                            subprocess.run(['sudo', 'chown', f'{uid}:{gid}', output_path],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"[DEBUG] 修改文件权限时出错: {e}")
            traceback.print_exc()
            pass

        if result.returncode != 0:
            stderr_text = (result.stderr or b'').decode('utf-8', errors='ignore')
            print(f"❌ FFmpeg命令执行失败: {' '.join(cmd)}")
            if stderr_text:
                print(f"错误输出: {stderr_text}")
            raise subprocess.CalledProcessError(result.returncode, cmd)
        return result
    except subprocess.TimeoutExpired:
        print(f"❌ FFmpeg命令执行超时: {' '.join(cmd)}")
        raise
    except Exception as e:
        print(f"❌ FFmpeg命令执行异常: {e}")
        traceback.print_exc()
        raise


def insert_gap(concat_list: list, tmpdir: str, gap: str, index: int) -> None:
    """在视频片段之间插入黑屏间隔"""
    print(f"[DEBUG] 插入间隔片段，索引: {index}")
    import shutil
    # 直接引用 TS 容器，避免 mp4/aac 头解析问题
    gap_copy = os.path.join(tmpdir, f'gap_{index}.ts')
    print(f"[DEBUG] 间隔片段复制路径: {gap_copy}")
    shutil.copy2(gap, gap_copy)
    concat_list.append(gap_copy)


def move_file(source_path: str, target_dir: str, new_name: str) -> str | None:
    """移动文件到目标目录并重命名"""
    print(f"[DEBUG] 移动文件: {source_path} -> {target_dir}/{new_name}")
    import shutil
    if not os.path.exists(source_path):
        print(f"❌ 源文件不存在: {source_path}")
        return None

    _, ext = os.path.splitext(source_path)
    target_path = os.path.join(target_dir, new_name + ext)
    print(f"[DEBUG] 目标文件路径: {target_path}")

    counter = 1
    original_target_path = target_path
    while os.path.exists(target_path):
        name_part = f"{new_name}_{counter}"
        target_path = os.path.join(target_dir, name_part + ext)
        print(f"[DEBUG] 目标文件已存在，尝试新名称: {target_path}")
        counter += 1
        if counter > 100:
            print(f"❌ 无法生成唯一文件名: {original_target_path}")
            return None

    try:
        print(f"[DEBUG] 执行文件移动操作")
        shutil.move(source_path, target_path)
        print(f"[DEBUG] 文件移动完成")
        return target_path
    except Exception as e:
        print(f"❌ 文件移动失败 {source_path} -> {target_path}: {e}")
        traceback.print_exc()
        return None


def ass_time_add(time_str: str, delta_sec: float) -> str:
    print(f"[DEBUG] ASS时间计算: {time_str} + {delta_sec}秒")
    h, m, s_ms = time_str.split(':')
    s, ms = s_ms.split('.')
    total = int(h)*3600 + int(m)*60 + int(s) + float('0.'+ms)
    total += delta_sec
    if total < 0:
        total = 0
    h2 = int(total // 3600)
    m2 = int((total % 3600) // 60)
    s2 = int(total % 60)
    centiseconds = int(round((total - int(total)) * 100))
    if centiseconds == 100:
        centiseconds = 0
        s2 += 1
        if s2 == 60:
            s2 = 0
            m2 += 1
            if m2 == 60:
                m2 = 0
                h2 += 1
    result = f"{h2}:{m2:02d}:{s2:02d}.{centiseconds:02d}"
    print(f"[DEBUG] 计算结果: {result}")
    return result

# ---- shared state for passing ordered new files between modules ----
_LAST_DOWNLOAD_FILES: List[str] = []

def set_last_download_files(files: List[str]) -> None:
    global _LAST_DOWNLOAD_FILES
    print(f"[DEBUG] 设置最后下载的文件列表，数量: {len(files)}")
    _LAST_DOWNLOAD_FILES = list(files)

def get_last_download_files() -> List[str]:
    print(f"[DEBUG] 获取最后下载的文件列表，数量: {len(_LAST_DOWNLOAD_FILES)}")
    return list(_LAST_DOWNLOAD_FILES)