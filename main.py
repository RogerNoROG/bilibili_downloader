import time
from typing import Optional

import os
import sys
import subprocess
import shutil
import platform

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
    # Linux: 用 apt 安装系统依赖，并使用本地虚拟环境安装 Python 包，避免 PEP 668 限制
    if sys.platform.startswith('linux'):
        def _has_cmd(cmd: str) -> bool:
            return shutil.which(cmd) is not None

        if _has_cmd('apt') or _has_cmd('apt-get'):
            apt_cmd = 'apt' if _has_cmd('apt') else 'apt-get'
            env = os.environ.copy()
            env['DEBIAN_FRONTEND'] = 'noninteractive'
            try:
                print("🧰 通过 apt 安装系统依赖（需要 sudo）：ffmpeg、python3-venv")
                subprocess.run(['sudo', apt_cmd, 'update', '-y'], check=False, env=env)
                subprocess.run(['sudo', apt_cmd, 'install', '-y', 'ffmpeg', 'python3-venv'], check=True, env=env)
            except Exception as e:
                print(f"⚠️ apt 安装系统依赖失败：{e}，继续尝试后续步骤。")

        # 使用项目本地虚拟环境安装 Python 包
        project_root = os.path.dirname(os.path.abspath(__file__))
        venv_dir = os.path.join(project_root, '.venv')
        venv_python = os.path.join(venv_dir, 'bin', 'python')
        if not os.path.exists(venv_python):
            print("🐍 正在创建虚拟环境 .venv ...")
            subprocess.run(['python3', '-m', 'venv', venv_dir], check=True)
        # 升级 pip 并安装包
        print("📦 在虚拟环境中安装 Python 依赖（playwright、yutto）...")
        subprocess.run([venv_python, '-m', 'pip', 'install', '--upgrade', 'pip'], check=True)
        subprocess.run([venv_python, '-m', 'pip', 'install', 'playwright', 'yutto'], check=True)
        # 安装 Playwright 浏览器内核
        os.environ["PLAYWRIGHT_DOWNLOAD_HOST"] = "https://npmmirror.com/mirrors/playwright"
        subprocess.run([venv_python, '-m', 'playwright', 'install', 'chromium'], check=False)

        # 若当前不是 venv 解释器，则切换到 venv 并重启自身
        if os.path.realpath(sys.executable) != os.path.realpath(venv_python) and os.environ.get('BILI_VENV_ACTIVATED') != '1':
            print("🔁 切换到虚拟环境解释器重新启动程序...")
            env2 = os.environ.copy()
            env2['BILI_VENV_ACTIVATED'] = '1'
            os.execvpe(venv_python, [venv_python] + sys.argv, env2)

    else:
        # Windows/macOS: 沿用当前 Python 安装依赖
        for pkg in ['playwright', 'yutto']:
            try:
                __import__(pkg)
            except ImportError:
                print(f"🔧 正在安装：{pkg}")
                subprocess.run([
                    sys.executable, '-m', 'pip', 'install', pkg,
                ], check=True)
        os.environ["PLAYWRIGHT_DOWNLOAD_HOST"] = "https://npmmirror.com/mirrors/playwright"
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)


def main():
    print("=" * 60)
    print("🎬 Bilibili 视频处理自动化流程")
    print("=" * 60)

    _ensure_dependencies()
    # 依赖补全后再检查 ffmpeg 是否可用
    check_ffmpeg_installed()

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
