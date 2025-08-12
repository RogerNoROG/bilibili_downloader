import os
import sys
import json
import platform
import shutil
import subprocess
from typing import List, Tuple


def _local_tool_candidates(tool: str) -> list[str]:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    names = [tool]
    if sys.platform.startswith('win'):
        names = [f"{tool}.exe", tool]
    return [os.path.join(base_dir, n) for n in names]


def _resolve_tool(tool: str) -> str | None:
    # 1) PATH 查找
    path = shutil.which(tool)
    if path:
        return path
    # 2) 脚本所在目录查找（与程序同目录）
    for cand in _local_tool_candidates(tool):
        if os.path.isfile(cand):
            return cand
    return None


def get_ffmpeg_path() -> str | None:
    return _resolve_tool('ffmpeg')


def get_ffprobe_path() -> str | None:
    return _resolve_tool('ffprobe')


def get_ffplay_path() -> str | None:
    return _resolve_tool('ffplay')


def get_vaapi_device_path() -> str | None:
    """返回可用的 VAAPI render 节点，如 /dev/dri/renderD128。若不可用返回 None。"""
    if not sys.platform.startswith('linux'):
        return None
    dri_dir = '/dev/dri'
    try:
        if not os.path.isdir(dri_dir):
            return None
        candidates: List[str] = []
        for name in os.listdir(dri_dir):
            if name.startswith('renderD'):
                candidates.append(os.path.join(dri_dir, name))
        candidates.sort()
        return candidates[0] if candidates else None
    except Exception:
        return None


def check_ffmpeg_installed() -> None:
    """检查 ffmpeg/ffprobe 是否可用；优先使用 PATH，其次程序同目录。"""
    tools = [
        (get_ffmpeg_path(), 'ffmpeg'),
        (get_ffprobe_path(), 'ffprobe')
    ]
    for resolved, name in tools:
        if not resolved:
            print(f"❌ 未检测到 {name}，请安装或将其与程序放在同一目录后再运行。")
            print("参考: https://ffmpeg.org/download.html 或各平台包管理器。")
            sys.exit(1)
        try:
            subprocess.run([resolved, '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception:
            print(f"❌ {name} 无法执行：{resolved}")
            sys.exit(1)


def get_media_duration_seconds(path: str) -> float:
    """使用 ffprobe 获取媒体时长（秒）。失败返回 0.0。"""
    try:
        ffprobe = get_ffprobe_path() or 'ffprobe'
        probe = subprocess.run(
            [ffprobe, '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='ignore', check=True
        )
        return float(probe.stdout.strip())
    except Exception:
        return 0.0


def get_video_resolution(video_path: str):
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_streams', '-select_streams', 'v:0', video_path
    ]
    try:
        ffprobe = get_ffprobe_path() or 'ffprobe'
        cmd = [ffprobe if (len(cmd) > 0 and cmd[0] == 'ffprobe') else cmd[0]] + cmd[1:]
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='ignore', timeout=10
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        for stream in data.get('streams', []):
            if stream['codec_type'] == 'video':
                width = stream.get('width')
                height = stream.get('height')
                if width and height:
                    return (width, height)
    except Exception:
        pass
    return None


def detect_available_encoders() -> List[Tuple[str, str]]:
    print("🔍 正在检测可用的硬件编码器...")
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
        }
    elif 'darwin' in system:
        candidates = {
            'h264_videotoolbox': 'Apple H.264 (VideoToolbox)',
            'hevc_videotoolbox': 'Apple H.265 (VideoToolbox)',
        }
    else:
        candidates = {}
    candidates.update({'libx264': 'CPU H.264', 'libx265': 'CPU H.265'})

    try:
        ffmpeg = get_ffmpeg_path() or 'ffmpeg'
        result = subprocess.run(
            [ffmpeg, '-encoders'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', errors='ignore'
        )
        ffmpeg_encoders = result.stdout.lower()
    except Exception:
        print("⚠️ 无法获取 ffmpeg 编码器列表，仅保留 CPU 编码器。")
        return [('libx264', 'CPU H.264'), ('libx265', 'CPU H.265')]

    available: List[Tuple[str, str]] = []
    print("🛠️  正在测试编码器可用性...")
    vaapi_dev = get_vaapi_device_path() if platform.system().lower().startswith('linux') else None
    if vaapi_dev:
        print(f"   🔧 检测到 VAAPI 设备: {vaapi_dev}")
    elif platform.system().lower().startswith('linux'):
        print("   ⚠️ 未检测到 VAAPI 设备节点（/dev/dri/renderD*）")
    for enc, desc in candidates.items():
        if enc not in ffmpeg_encoders:
            print(f"   ⏩ 跳过: {enc}（ffmpeg 不支持）")
            continue
        try:
            ffmpeg = get_ffmpeg_path() or 'ffmpeg'
            if enc.endswith('_vaapi'):
                test_cmd = [ffmpeg, '-y']
                if vaapi_dev:
                    test_cmd += ['-vaapi_device', vaapi_dev]
                test_cmd += [
                    '-f', 'lavfi', '-i', 'testsrc=duration=1:size=1280x720:rate=30',
                    '-vf', 'format=nv12,hwupload',
                    '-c:v', enc, '-t', '1', '-f', 'null', '-'
                ]
            else:
                test_cmd = [
                    ffmpeg, '-y', '-f', 'lavfi', '-i', 'testsrc=duration=1:size=1280x720:rate=30',
                    '-c:v', enc, '-t', '1', '-f', 'null', '-'
                ]
            print(f"   🧪 测试 {enc}: {' '.join(test_cmd)}")
            result = subprocess.run(
                test_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='ignore', timeout=8
            )
            if result.returncode == 0:
                print(f"   ✅ 可用: {enc} - {desc}")
                available.append((enc, desc))
            else:
                err = (result.stderr or "").strip()
                if err:
                    err_summary = err[-500:]
                    print(f"   ❌ 不可用: {enc} - {desc}（错误摘要）:\n      {err_summary}")
                else:
                    print(f"   ❌ 不可用: {enc} - {desc}")
        except Exception as e:
            print(f"   ❌ 不可用: {enc} - {desc}（异常: {e}）")

    if not available:
        print("⚠️ 未检测到可用硬件编码器，仅可用 CPU 编码器。")
        available = [('libx264', 'CPU H.264'), ('libx265', 'CPU H.265')]

    print("📝 编码器检测结果：")
    for enc, desc in available:
        print(f"   • {enc} - {desc}")
    return available


def select_best_hevc_encoder(available_encoders=None) -> str:
    if available_encoders is None:
        available_encoders = [enc for enc, _ in detect_available_encoders()]
    else:
        available_encoders = [enc for enc, _ in available_encoders]

    priority = [
        'hevc_nvenc', 'hevc_amf', 'hevc_qsv', 'hevc_vaapi', 'hevc_videotoolbox', 'libx265'
    ]
    for enc in priority:
        if enc in available_encoders:
            print(f"🎯 自动选择 HEVC 编码器: {enc}")
            return enc
    print("⚠️ 未检测到 HEVC 硬件编码器，使用 libx265")
    return 'libx265'


def get_video_files(directory: str) -> List[str]:
    """获取指定目录下的所有视频文件（按目录枚举顺序，不排序）"""
    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv')
    return [
        os.path.join(directory, f) for f in os.listdir(directory)
        if f.lower().endswith(video_extensions)
    ]


def run_ffmpeg(cmd: list, timeout_seconds: int | None = None):
    """运行 ffmpeg 命令并检查返回码。使用二进制管道避免编码问题。"""
    try:
        # 自动解析 ffmpeg 路径（Windows 未在 PATH 且在当前目录的情况）
        if cmd and isinstance(cmd[0], str) and os.path.basename(cmd[0]).lower() in ('ffmpeg', 'ffmpeg.exe'):
            ffmpeg = get_ffmpeg_path() or cmd[0]
            cmd = [ffmpeg] + cmd[1:]

        # 在 Linux 下，为了确保硬件编解码权限，若非 root 且存在 sudo，则使用 sudo 执行
        if sys.platform.startswith('linux'):
            try:
                is_root = (os.geteuid() == 0)
            except Exception:
                is_root = False
            if not is_root and shutil.which('sudo'):
                cmd = ['sudo', '-E'] + cmd
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            timeout=timeout_seconds,
        )
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
                        if os.path.exists(output_path):
                            uid = os.getuid()
                            gid = os.getgid()
                            subprocess.run(['sudo', 'chown', f'{uid}:{gid}', output_path],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
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
        raise


def insert_gap(concat_list: list, tmpdir: str, gap: str, index: int) -> None:
    """在视频片段之间插入黑屏间隔"""
    import shutil
    # 直接引用 TS 容器，避免 mp4/aac 头解析问题
    gap_copy = os.path.join(tmpdir, f'gap_{index}.ts')
    shutil.copy2(gap, gap_copy)
    concat_list.append(gap_copy)


def move_file(source_path: str, target_dir: str, new_name: str) -> str | None:
    """移动文件到目标目录并重命名"""
    import shutil
    if not os.path.exists(source_path):
        print(f"❌ 源文件不存在: {source_path}")
        return None

    _, ext = os.path.splitext(source_path)
    target_path = os.path.join(target_dir, new_name + ext)

    counter = 1
    original_target_path = target_path
    while os.path.exists(target_path):
        name_part = f"{new_name}_{counter}"
        target_path = os.path.join(target_dir, name_part + ext)
        counter += 1
        if counter > 100:
            print(f"❌ 无法生成唯一文件名: {original_target_path}")
            return None

    try:
        shutil.move(source_path, target_path)
        return target_path
    except Exception as e:
        print(f"❌ 文件移动失败 {source_path} -> {target_path}: {e}")
        return None


def ass_time_add(time_str: str, delta_sec: float) -> str:
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
    return f"{h2}:{m2:02d}:{s2:02d}.{centiseconds:02d}"

# ---- shared state for passing ordered new files between modules ----
_LAST_DOWNLOAD_FILES: List[str] = []

def set_last_download_files(files: List[str]) -> None:
    global _LAST_DOWNLOAD_FILES
    _LAST_DOWNLOAD_FILES = list(files)

def get_last_download_files() -> List[str]:
    return list(_LAST_DOWNLOAD_FILES)
