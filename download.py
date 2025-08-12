import os
import sys
import time
import re
import subprocess
from typing import List, Tuple


def get_save_path() -> str:
    default = os.path.abspath("download")
    print(f"\n📁 默认保存目录为：{default}")
    use_default = input("是否使用默认保存目录？(Y/n): ").strip().lower() != 'n'
    if use_default:
        os.makedirs(default, exist_ok=True)
        return default

    while True:
        path = input("请输入自定义保存目录路径: ").strip()
        if not path:
            print("❌ 路径不能为空，请重新输入。")
            continue
        path = os.path.abspath(path)
        try:
            os.makedirs(path, exist_ok=True)
            print(f"📂 保存路径：{path}")
            return path
        except Exception as e:
            print(f"❌ 创建目录失败: {e}")


def get_sessdata() -> str:
    print("🔐 获取账号凭据（登录 Bilibili）")
    cache = "SESSDATA.txt"
    if os.path.exists(cache):
        sess = open(cache, 'r', encoding='utf-8').read().strip()
        if len(sess) > 10 and input("使用缓存凭据？(Y/n): ").lower() in ("", "y"):
            return sess

    # 延迟导入，确保依赖已安装且当前解释器已切换到虚拟环境
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.bilibili.com", wait_until="networkidle")
        sessdata = None
        for _ in range(60):
            for c in context.cookies():
                if c['name'] == 'SESSDATA':
                    sessdata = c['value']
                    break
            if sessdata:
                break
            time.sleep(2)
        browser.close()
        if not sessdata:
            sys.exit("❌ 未能获取登录凭据")
        with open(cache, 'w', encoding='utf-8') as f:
            f.write(sessdata)
        print("✅ 成功获取登录凭据")
        return sessdata


def extract_bv(text: str) -> List[str]:
    return list(dict.fromkeys(re.findall(r'BV[0-9a-zA-Z]{10}', text)))


def generate_download_bat(bv_list: List[str], save_path: str, sessdata: str) -> str:
    bat = 'download_videos.bat'
    print(f"📝 生成下载脚本（共 {len(bv_list)} 个 BV）...")
    with open(bat, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write('@echo off\nchcp 65001 >nul\n')
        for bv in bv_list:
            exe = sys.executable.replace('\\\\', '/')
            f.write(f'"{exe}" -m yutto -c "{sessdata}" -d "{save_path}" {bv}\n')
    return bat


def run_download() -> Tuple[str, float, float]:
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
    bat = generate_download_bat(bv_list, save_path, sessdata)
    print("⚠  接下来的过程可能出错，如果出错了请手动执行一次文件夹下的download_videos.bat！")
    print("▶️ 正在启动下载脚本（新窗口），请等待其完成...")

    # 记录下载前的文件状态
    before_files = set(os.listdir(save_path)) if os.path.exists(save_path) else set()

    start_time = time.time()
    subprocess.run(f'start "" /wait cmd /c "{bat}"', shell=True)
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

    for bv in bv_list:
        print(f"⏬ 开始下载 {bv} ...")
        cmd = [sys.executable, '-m', 'yutto']
        if sessdata:
            cmd += ['-c', sessdata]
        cmd += ['-d', save_path, bv]
        subprocess.run(cmd, shell=False)

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
