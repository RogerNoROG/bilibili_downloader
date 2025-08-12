#!/usr/bin/env python3
"""
Linux环境下依赖检测测试脚本
用于验证ffmpeg和pip的检测逻辑
"""

import os
import sys
import shutil
import subprocess
import platform

def _has_cmd(cmd: str) -> bool:
    """检测命令是否存在"""
    return shutil.which(cmd) is not None

def test_dependency_detection():
    """测试依赖检测功能"""
    print("🔍 Linux环境依赖检测测试")
    print("=" * 50)
    
    # 检测操作系统
    print(f"操作系统: {platform.system()} {platform.release()}")
    print(f"Python版本: {sys.version}")
    
    # 检测ffmpeg
    ffmpeg_path = shutil.which('ffmpeg')
    print(f"ffmpeg检测: {'✅ 已安装' if ffmpeg_path else '❌ 未安装'}")
    if ffmpeg_path:
        print(f"  ffmpeg路径: {ffmpeg_path}")
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                print(f"  ffmpeg版本: {version_line}")
            else:
                print("  ⚠️ ffmpeg无法执行")
        except Exception as e:
            print(f"  ⚠️ ffmpeg执行异常: {e}")
    
    # 检测pip
    pip_path = shutil.which('pip') or shutil.which('pip3')
    print(f"pip检测: {'✅ 已安装' if pip_path else '❌ 未安装'}")
    if pip_path:
        print(f"  pip路径: {pip_path}")
        try:
            result = subprocess.run([pip_path, '--version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"  pip版本: {result.stdout.strip()}")
            else:
                print("  ⚠️ pip无法执行")
        except Exception as e:
            print(f"  ⚠️ pip执行异常: {e}")
    
    # 检测包管理器
    apt_cmd = 'apt' if _has_cmd('apt') else ('apt-get' if _has_cmd('apt-get') else None)
    print(f"包管理器: {'✅ ' + apt_cmd if apt_cmd else '❌ 未检测到apt/apt-get'}")
    
    # 检测Python虚拟环境支持
    venv_support = _has_cmd('python3') and _has_cmd('python3-venv')
    print(f"虚拟环境支持: {'✅ 已支持' if venv_support else '❌ 不支持'}")
    
    print("\n📋 检测结果摘要:")
    missing_deps = []
    if not ffmpeg_path:
        missing_deps.append('ffmpeg')
    if not pip_path:
        missing_deps.append('python3-pip')
    if not apt_cmd:
        missing_deps.append('apt包管理器')
    
    if missing_deps:
        print(f"❌ 缺少依赖: {', '.join(missing_deps)}")
        print("建议手动安装或使用main.py自动安装")
    else:
        print("✅ 所有依赖检测通过")
    
    return len(missing_deps) == 0

if __name__ == "__main__":
    try:
        success = test_dependency_detection()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        sys.exit(1)
