import time
from typing import Optional

import os
import sys
import subprocess

# 注意：此文件在安装第三方依赖前不导入任何第三方模块或依赖这些模块的本地文件
from utils import check_ffmpeg_installed


def ask_execute(task_name: str, task_function, *args, **kwargs):
    resp = input(f"是否执行 {task_name}？(Y/n): ").strip().lower()
    if resp == "n":
        print(f"🚫 已跳过 {task_name}。")
        return False
    print(f"🚀 开始执行 {task_name}...")
    try:
        result = task_function(*args, **kwargs)
        print(f"✅ {task_name} 执行完成。")
        return result
    except Exception as e:
        print(f"❌ {task_name} 执行失败: {e}")
        return None


def _ensure_dependencies():
    """在导入任何依赖这些库的模块前，确保第三方依赖已安装。"""
    print("📦 检查并安装依赖...")
    for pkg in ['playwright', 'yutto']:
        try:
            __import__(pkg)
        except ImportError:
            print(f"🔧 正在安装：{pkg}")
            subprocess.run([
                sys.executable, '-m', 'pip', 'install', pkg,
                '--index-url', 'https://mirror.nju.edu.cn/pypi/simple',
                '--trusted-host', 'mirror.nju.edu.cn',
                '--user'
            ], check=True)
    # 安装 Playwright 浏览器内核
    os.environ["PLAYWRIGHT_DOWNLOAD_HOST"] = "https://npmmirror.com/mirrors/playwright"
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)


def main():
    print("=" * 60)
    print("🎬 Bilibili 视频处理自动化流程")
    print("=" * 60)

    check_ffmpeg_installed()
    # 在导入使用第三方库的模块之前确保依赖已安装
    _ensure_dependencies()

    # 依赖已就绪后再导入会使用它们的模块
    from download import run_download
    from merge import merge_videos_with_best_hevc

    download_result = ask_execute("【📥 视频下载】", run_download)

    download_dir = "./download"
    start_time = time.time()
    end_time = time.time()

    if download_result:
        download_dir, start_time, end_time = download_result
        print("✅ 下载流程已完成，继续执行后续操作...")
    else:
        print("⚠️ 下载流程被跳过或失败，继续执行后续操作...")

    merge_done = ask_execute(
        "【🎥 视频合并】",
        merge_videos_with_best_hevc,
        download_dir, None, start_time, end_time
    )

    print("\n" + "=" * 60)
    print("📋 执行摘要")
    print("=" * 60)
    # 取消开头的编码器检测统计项
    print(f"• 视频下载: {'✅ 已执行' if download_result else '⚠️ 跳过'}")
    print(f"• 视频合并: {'✅ 已执行' if merge_done else '⚠️ 跳过'}")
    print("\n🎉 处理完成！")
    input("\n👉 请按任意键退出...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 程序被用户中断。")
    except Exception as e:
        print(f"\n❌ 程序错误: {e}")
        input("按任意键退出...")
