import os
import sys
import time
import re
import subprocess
import shlex
import traceback
from typing import List, Tuple


def _project_root() -> str:
    root = os.path.dirname(os.path.abspath(__file__))
    print(f"[DEBUG] 项目根目录: {root}")
    return root


def _resolve_venv_python() -> str:
    """解析虚拟环境中 Python 解释器的路径，提供健壮的路径验证和回退机制"""
    root = _project_root()
    print(f"[DEBUG] 开始解析虚拟环境Python路径")
    
    # 构建候选路径
    if sys.platform.startswith('win'):
        candidate = os.path.join(root, '.venv', 'Scripts', 'python.exe')
    else:
        candidate = os.path.join(root, '.venv', 'bin', 'python')
    
    print(f"[DEBUG] 候选虚拟环境Python路径: {candidate}")
    
    # 验证候选路径的有效性
    if os.path.exists(candidate) and os.path.isfile(candidate):
        try:
            # 检查文件可执行性
            if os.access(candidate, os.X_OK):
                print(f"[DEBUG] 找到可执行的虚拟环境Python: {candidate}")
                return candidate
            else:
                print(f"⚠️ 警告：发现 Python 路径但不可执行 - {candidate}")
        except Exception as e:
            print(f"⚠️ 警告：验证 Python 路径时发生错误 - {e}")
            traceback.print_exc()
    
    # 回退到当前解释器，并提供路径信息用于调试
    print(f"⚠️ 未找到虚拟环境 Python，回退到主环境解释器：{sys.executable}")
    print(f"    项目根目录：{root}")
    print(f"    尝试的虚拟环境路径：{candidate}")
    
    return sys.executable


def get_sessdata() -> str:
    print("🔐 获取账号凭据（登录 Bilibili）")
    cache = "SESSDATA.txt"
    print(f"[DEBUG] 检查缓存文件: {cache}")
    if os.path.exists(cache):
        print("[DEBUG] 发现缓存文件，尝试读取")
        try:
            sess = open(cache, 'r', encoding='utf-8').read().strip()
            print(f"[DEBUG] 缓存文件内容长度: {len(sess)}")
            if len(sess) > 10 and input("使用缓存凭据？(Y/n): ").lower() in ("", "y"):
                print("[DEBUG] 使用缓存凭据")
                return sess
        except Exception as e:
            print(f"[DEBUG] 读取缓存文件失败: {e}")
            traceback.print_exc()

    # 检查是否有图形界面环境
    has_display = os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')
    print(f"[DEBUG] 图形界面环境检测结果: DISPLAY={os.environ.get('DISPLAY')}, WAYLAND_DISPLAY={os.environ.get('WAYLAND_DISPLAY')}, has_display={has_display}")
    
    # 只在有图形界面的非Windows系统上尝试使用Playwright
    if has_display and not sys.platform.startswith('win'):
        print("[DEBUG] 检测到有图形界面的非Windows环境，尝试使用Playwright")
        # 有图形界面，使用 Playwright 自动获取
        try:
            # 延迟导入，确保依赖已安装且当前解释器已切换到虚拟环境
            print("[DEBUG] 尝试导入Playwright")
            from playwright.sync_api import sync_playwright
            print("[DEBUG] Playwright导入成功")

            with sync_playwright() as p:
                print("[DEBUG] 启动Chromium浏览器")
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()
                print("[DEBUG] 访问Bilibili主页")
                page.goto("https://www.bilibili.com", wait_until="networkidle")
                sessdata = None
                print("[DEBUG] 开始监听SESSDATA Cookie")
                for _ in range(60):
                    for c in context.cookies():
                        if c['name'] == 'SESSDATA':
                            sessdata = c['value']
                            print(f"[DEBUG] 获取到SESSDATA: {sessdata[:10]}...")
                            break
                    if sessdata:
                        break
                    time.sleep(2)
                browser.close()
                if not sessdata:
                    print("❌ 未能获取登录凭据，切换到手动输入模式")
                else:
                    print("[DEBUG] 保存SESSDATA到缓存文件")
                    with open(cache, 'w', encoding='utf-8') as f:
                        f.write(sessdata)
                    print("✅ 成功获取登录凭据")
                    return sessdata
        except ImportError as e:
            print(f"⚠️ Playwright 未安装，切换到手动输入模式: {e}")
            traceback.print_exc()
        except Exception as e:
            print(f"⚠️ Playwright 获取凭据失败: {e}")
            traceback.print_exc()
            print("切换到手动输入模式")
    else:
        if sys.platform.startswith('win'):
            print("📝 Windows 系统默认使用手动输入 SESSDATA（从浏览器开发者工具中获取）")
        else:
            print("📝 检测到无图形界面环境，使用手动输入 SESSDATA")
    
    # 无图形界面或 Playwright 失败，使用手动输入
    print("📝 请手动输入 SESSDATA（从浏览器开发者工具中获取）")
    print("💡 获取方法：")
    print("   1. 在浏览器中登录 Bilibili")
    print("   2. 按 F12 打开开发者工具")
    print("   3. 切换到 Application/Storage 标签")
    print("   4. 在 Cookies 中找到 SESSDATA 的值")
    print("   5. 复制该值并粘贴到下方")
    print()
    
    while True:
        sessdata = input("请输入 SESSDATA: ").strip()
        print(f"[DEBUG] 用户输入的SESSDATA长度: {len(sessdata)}")
        if len(sessdata) > 10:
            # 保存到缓存文件
            print("[DEBUG] 保存用户输入的SESSDATA到缓存文件")
            with open(cache, 'w', encoding='utf-8') as f:
                f.write(sessdata)
            print("✅ SESSDATA 已保存")
            return sessdata
        else:
            print("❌ SESSDATA 格式不正确，请重新输入")


def generate_download_bat(bv_list: List[str], save_path: str, sessdata: str) -> str:
    bat = 'download_videos.bat'
    print(f"📝 生成下载脚本（共 {len(bv_list)} 个 BV）...")
    print(f"[DEBUG] 下载脚本路径: {bat}")
    print(f"[DEBUG] 保存路径: {save_path}")
    print(f"[DEBUG] SESSDATA: {sessdata[:10]}...")
    with open(bat, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write('@echo off\nchcp 65001 >nul\n')
        for bv in bv_list:
            exe = _resolve_venv_python().replace('\\', '/')  # 标准化路径分隔符
            print(f"[DEBUG] 为BV号生成命令: {bv}")
            f.write(f'"{exe}" -m yutto -c "{sessdata}" -d "{save_path}" {bv}\n')
    return bat


def get_save_path() -> str:
    """获取视频保存路径"""
    print("[DEBUG] 获取视频保存路径")
    save_path = os.path.abspath("download")
    print(f"[DEBUG] 创建保存目录: {save_path}")
    os.makedirs(save_path, exist_ok=True)
    return save_path


def extract_bv(text: str) -> List[str]:
    """从文本中提取所有BV号"""
    print(f"[DEBUG] 从文本中提取BV号: {text[:50]}...")
    # BV号的正则表达式
    bv_pattern = r'BV[0-9A-Za-z]{10}'
    bv_list = re.findall(bv_pattern, text)
    print(f"[DEBUG] 提取到 {len(bv_list)} 个BV号: {bv_list}")
    # 去重但保持顺序
    seen = set()
    unique_bv_list = []
    for bv in bv_list:
        if bv not in seen:
            seen.add(bv)
            unique_bv_list.append(bv)
    print(f"[DEBUG] 去重后 {len(unique_bv_list)} 个BV号: {unique_bv_list}")
    return unique_bv_list


def generate_download_sh(bv_list: List[str], save_path: str, sessdata: str) -> str:
    project_root = _project_root()
    sh = os.path.join(project_root, 'download_videos.sh')
    print(f"📝 生成下载脚本（共 {len(bv_list)} 个 BV）...")
    lines = [
        '#!/usr/bin/env bash',
        'set -euo pipefail'
    ]
    py = shlex.quote(_resolve_venv_python())
    save_q = shlex.quote(save_path)
    sess_q = shlex.quote(sessdata)
    for bv in bv_list:
        bv_q = shlex.quote(bv)
        lines.append(f"{py} -m yutto -c {sess_q} -d {save_q} {bv_q}")
    with open(sh, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    try:
        os.chmod(sh, os.stat(sh).st_mode | 0o111)
    except Exception:
        pass
    return sh


def _run_yutto_batch(bv_list: List[str], save_path: str, sessdata: str) -> None:
    """使用项目虚拟环境中的 Python 逐个调用 yutto 下载。"""
    py = _resolve_venv_python()
    for bv in bv_list:
        print(f"⏬ 开始下载 {bv} ...")
        cmd = [py, '-m', 'yutto']
        if sessdata:
            cmd += ['-c', sessdata]
        cmd += ['-d', save_path, bv]
        subprocess.run(cmd, shell=False, check=False)


def run_download() -> Tuple[str, float, float]:
    print("[DEBUG] 开始执行下载任务")
    save_path = get_save_path()
    sessdata = get_sessdata()
    print("📋 请输入包含 BV 号的文本，使用 Ctrl+Z 与回车结束输入：")
    input_lines: List[str] = []
    while True:
        try:
            input_lines.append(input())
        except EOFError:
            break
    bv_list = extract_bv('\n'.join(input_lines))
    if not bv_list:
        sys.exit("❌ 未识别任何 BV")
    # 生成并执行下载脚本
    if sys.platform.startswith('win'):
        script = generate_download_bat(bv_list, save_path, sessdata)
        print("⚠  接下来的过程可能出错，如果出错了请手动执行一次文件夹下的 download_videos.bat！")
        print("▶️ 正在启动下载脚本（新窗口），请等待其完成...")
    else:
        script = generate_download_sh(bv_list, save_path, sessdata)
        print("⚠  接下来的过程可能出错，如果出错了请手动执行一次文件夹下的 download_videos.sh！")
        print(f"▶️ 正在执行下载脚本：{script}，请等待其完成...")

    # 记录下载前的文件状态
    before_files = set(os.listdir(save_path)) if os.path.exists(save_path) else set()

    start_time = time.time()
    if sys.platform.startswith('win'):
        subprocess.run(f'start "" /wait cmd /c "{script}"', shell=True)
    else:
        subprocess.run(['bash', script], shell=False, cwd=os.path.dirname(script))
    end_time = time.time()
    print("✅ 下载完成，继续后续操作...")

    after_files = set(os.listdir(save_path)) if os.path.exists(save_path) else set()
    new_files = after_files - before_files
    new_video_files = [
        os.path.join(save_path, f) for f in new_files
        if f.lower().endswith(('.mp4', '.mkv', '.avi'))
    ]
    # 保持加入顺序（目录枚举差异可能导致顺序不稳定，优先用输入顺序）

    # 保存新增文件列表供后续使用
    # 记录顺序给合并模块使用
    try:
        from utils import set_last_download_files
        set_last_download_files(new_video_files)
    except Exception:
        pass
    return save_path, start_time, end_time


def run_download_videos_only() -> None:
    save_path = os.path.abspath("download")
    os.makedirs(save_path, exist_ok=True)
    print("请粘贴所有 BV 号（每行一个），输入完后按 Ctrl+Z（Win）或 Ctrl+D（Mac/Linux）结束：")
    before_files = set(os.listdir(save_path))
    start_time = time.time()

    # 读取或获取 SESSDATA
    sessdata = None
    cache = "SESSDATA.txt"
    if os.path.exists(cache):
        try:
            sessdata = open(cache, 'r', encoding='utf-8').read().strip()
        except Exception:
            sessdata = None
    if not sessdata:
        try:
            sessdata = get_sessdata()
        except Exception:
            sessdata = None

    try:
        bv_list: List[str] = []
        while True:
            line = input()
            if not line:
                continue
            bv = line.strip()
            if bv.startswith("BV") and len(bv) == 12:
                bv_list.append(bv)
    except EOFError:
        pass

    if not bv_list:
        print("❌ 未识别任何 BV")
        return

    _run_yutto_batch(bv_list, save_path, sessdata)

    end_time = time.time()
    print("✅ 下载流程结束。")

    after_files = set(os.listdir(save_path))
    new_files = [
        os.path.join(save_path, f) for f in (after_files - before_files)
        if f.lower().endswith(('.mp4', '.mkv', '.avi'))
    ]
    new_files = [
        f for f in new_files
        if os.path.getmtime(f) >= start_time - 2
    ]
    if not new_files:
        print("⚠️ 未检测到新增视频文件。")
    else:
        print("📝 本次下载新增视频文件：")
        for f in new_files:
            print("   •", os.path.basename(f))

    try:
        from utils import set_last_download_files
        set_last_download_files(new_files)
    except Exception:
        pass
