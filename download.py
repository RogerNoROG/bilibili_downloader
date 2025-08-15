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