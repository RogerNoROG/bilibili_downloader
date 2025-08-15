from typing import Optional
import os
import sys
import subprocess
import shutil

# 注意：此文件在安装第三方依赖前不导入任何第三方模块或依赖这些模块的本地文件


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

    # Linux: 检测并安装系统依赖，使用虚拟环境安装Python包
    if sys.platform.startswith('linux'):
        def _has_cmd(cmd: str) -> bool:
            return shutil.which(cmd) is not None

        # 检测系统依赖
        missing_system_deps = []
        if not _has_cmd('python3'):
            missing_system_deps.append('python3')
        if not _has_cmd('python3-venv'):
            missing_system_deps.append('python3-venv')
        if not _has_cmd('ffmpeg'):
            missing_system_deps.append('ffmpeg')

        # 如果缺少系统依赖，尝试通过apt安装
        if missing_system_deps:
            if _has_cmd('apt') or _has_cmd('apt-get'):
                apt_cmd = 'apt' if _has_cmd('apt') else 'apt-get'
                env = os.environ.copy()
                env['DEBIAN_FRONTEND'] = 'noninteractive'
                try:
                    print(f"🧰 检测到缺少系统依赖: {', '.join(missing_system_deps)}")
                    print("🧰 通过 apt 安装系统依赖（需要 sudo）...")
                    subprocess.run(['sudo', apt_cmd, 'update', '-y'], check=False, env=env)
                    subprocess.run(['sudo', apt_cmd, 'install', '-y'] + missing_system_deps, check=True, env=env)
                    print("✅ 系统依赖安装完成")
                except Exception as e:
                    print(f"⚠️ apt 安装系统依赖失败：{e}")
                    print("请手动安装以下依赖：")
                    for dep in missing_system_deps:
                        print(f"  - {dep}")
                    print("\n或者运行以下命令：")
                    print(f"sudo {apt_cmd} update && sudo {apt_cmd} install -y {' '.join(missing_system_deps)}")
                    sys.exit(1)
            else:
                print("❌ 未检测到 apt 包管理器，请手动安装以下依赖：")
                for dep in missing_system_deps:
                    print(f"  - {dep}")
                sys.exit(1)
        else:
            print("✅ 系统依赖检查通过")

        # 使用项目本地虚拟环境安装 Python 包
        project_root = os.path.dirname(os.path.abspath(__file__))
        venv_dir = os.path.join(project_root, '.venv')
        venv_python = os.path.join(venv_dir, 'bin', 'python')
        venv_pip = os.path.join(venv_dir, 'bin', 'pip')

        if not os.path.exists(venv_python):
            print("🐍 正在创建虚拟环境 .venv ...")
            try:
                subprocess.run(['python3', '-m', 'venv', venv_dir], check=True)
                print("✅ 虚拟环境创建成功")
            except subprocess.CalledProcessError as e:
                print(f"❌ 虚拟环境创建失败: {e}")
                print("请确保已安装 python3-venv:")
                print("sudo apt update && sudo apt install -y python3-venv")
                sys.exit(1)

        # 配置pip使用国内镜像源
        print("📦 配置pip使用国内镜像源...")
        pip_config_dir = os.path.join(venv_dir, 'pip.conf')
        pip_config_content = """[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple/
trusted-host = pypi.tuna.tsinghua.edu.cn
"""
        with open(pip_config_dir, 'w', encoding='utf-8') as f:
            f.write(pip_config_content)

        # 升级 pip 并安装包
        print("📦 在虚拟环境中安装 Python 依赖...")
        try:
            # 静默升级 pip，减少无关输出
            subprocess.run([venv_python, '-m', 'pip', 'install', '--upgrade', 'pip', '-q'], check=True)

            # 检查是否有图形界面环境
            has_display = os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')
            
            # 不使用 requirements.txt，手动安装依赖
            print("📦 安装默认依赖...")
            # 确保安装所有必需的依赖，包括pillow (PIL)
            core_packages = ['moviepy', 'pillow', 'yutto']
            if has_display:
                # 有图形界面，安装完整依赖
                subprocess.run([venv_pip, 'install'] + core_packages + ['playwright', '-q'], check=True)
            else:
                # 无图形界面，不安装 playwright，但需要安装所有核心依赖
                print("🖥️ 无图形界面环境，跳过 playwright 安装")
                subprocess.run([venv_pip, 'install'] + core_packages + ['-q'], check=True)

            # 检查是否有图形界面环境
            has_display = os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')
            if has_display:
                # 有图形界面，安装 Playwright 浏览器内核
                print("🌐 检测到图形界面，安装 Playwright 浏览器内核...")
                os.environ["PLAYWRIGHT_DOWNLOAD_HOST"] = "https://npmmirror.com/mirrors/playwright"
                
                # 先安装 Playwright 系统依赖
                try:
                    print("🔧 安装 Playwright 系统依赖...")
                    subprocess.run([venv_python, '-m', 'playwright', 'install-deps'], check=False)
                except Exception as e:
                    print(f"⚠️ Playwright 系统依赖安装失败: {e}")
                    print("请手动安装系统依赖:")
                    print("sudo apt install -y libnspr4 libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2")
                
                # 安装 Chromium 浏览器
                subprocess.run([venv_python, '-m', 'playwright', 'install', 'chromium'], check=False)
            else:
                # 无图形界面，跳过 Playwright 安装
                print("🖥️ 未检测到图形界面，跳过 Playwright 安装")
                print("💡 在无图形界面的服务器环境中，将使用手动输入 SESSDATA 的方式")
            
        except subprocess.CalledProcessError as e:
            print(f"❌ 依赖安装失败: {e}")
            print("请检查网络连接或手动安装依赖:")
            print(f"cd {project_root}")
            print(f"source .venv/bin/activate")
            print("pip install -r requirements.txt")
            sys.exit(1)

        # 若当前不是 venv 解释器，则切换到 venv 并重启自身
        if os.path.realpath(sys.executable) != os.path.realpath(venv_python) and os.environ.get('BILI_VENV_ACTIVATED') != '1':
            print("🔁 切换到虚拟环境解释器重新启动程序...")
            env2 = os.environ.copy()
            env2['BILI_VENV_ACTIVATED'] = '1'
            env2['VIRTUAL_ENV'] = venv_dir
            env2['PATH'] = os.path.join(venv_dir, 'bin') + os.pathsep + env2.get('PATH', '')
            os.execvpe(venv_python, [venv_python] + sys.argv, env2)

    else:
        # Windows/macOS: 沿用当前 Python 安装依赖
        required_packages = ['playwright', 'yutto', 'moviepy', 'pillow']
        for pkg in required_packages:
            try:
                __import__(pkg)
            except ImportError:
                print(f"🔧 正在安装：{pkg}")
                try:
                    subprocess.run([
                        sys.executable, '-m', 'pip', 'install', pkg,
                    ], check=True)
                except subprocess.CalledProcessError as e:
                    print(f"❌ 安装 {pkg} 失败: {e}")
                    print("请手动安装依赖:")
                    print(f"pip install {pkg}")
                    sys.exit(1)
        os.environ["PLAYWRIGHT_DOWNLOAD_HOST"] = "https://npmmirror.com/mirrors/playwright"
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)

def main():
    print("=" * 60)
    print("🎬 Bilibili 视频处理自动化流程")
    print("=" * 60)

    _ensure_dependencies()
    
    # 依赖补全后再导入会使用它们的模块
    try:
        from utils import check_ffmpeg_installed
        check_ffmpeg_installed()
    except ImportError as e:
        print(f"❌ 导入 utils 模块失败: {e}")
        print("请检查依赖是否正确安装")
        sys.exit(1)

    # 依赖已就绪后再导入会使用它们的模块
    try:
        from download import run_download
        from merge import merge_videos_with_best_hevc
    except ImportError as e:
        print(f"❌ 导入模块失败: {e}")
        print("请检查依赖是否正确安装")
        sys.exit(1)

    download_result = ask_execute("【📥 视频下载】", run_download)

    download_dir = "./download"

    if download_result:
        download_dir, _, _ = download_result
        print("✅ 下载流程已完成，继续执行后续操作...")
    else:
        print("⚠️ 下载流程被跳过或失败，继续执行后续操作...")

    merge_done = ask_execute(
        "【🎥 视频合并】",
        merge_videos_with_best_hevc,
        download_dir, None
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
