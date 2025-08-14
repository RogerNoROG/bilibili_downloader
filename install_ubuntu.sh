#!/bin/bash

# Ubuntu 系统安装脚本
# 用于快速设置 Bilibili 视频处理项目的运行环境

set -e  # 遇到错误立即退出

echo "============================================================"
echo "🐧 Ubuntu 系统环境安装脚本"
echo "============================================================"

# 检查是否为 root 用户
if [ "$EUID" -eq 0 ]; then
    echo "❌ 请不要使用 root 用户运行此脚本"
    echo "请使用普通用户运行，脚本会自动请求 sudo 权限"
    exit 1
fi

# 检查是否为 Ubuntu 系统
if ! grep -q "Ubuntu" /etc/os-release; then
    echo "⚠️ 此脚本专为 Ubuntu 系统设计"
    echo "其他 Linux 发行版可能需要手动安装依赖"
fi

echo "📦 更新系统包列表..."
sudo apt update

echo "🔧 安装系统依赖..."
sudo apt install -y \
    python3 \
    python3-venv \
    python3-pip \
    ffmpeg \
    curl \
    wget

# 检查是否有图形界面环境
if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
    echo "🖥️ 检测到图形界面，安装 Playwright 依赖..."
    sudo apt install -y \
        libnspr4 \
        libnss3 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgbm1 \
        libpango-1.0-0 \
        libcairo2 \
        libasound2
else
    echo "🖥️ 未检测到图形界面，跳过 Playwright 依赖安装"
fi

echo "✅ 系统依赖安装完成"

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
echo "🐍 Python 版本: $PYTHON_VERSION"

# 检查 FFmpeg 版本
FFMPEG_VERSION=$(ffmpeg -version 2>/dev/null | head -n1 | cut -d' ' -f3)
echo "🎬 FFmpeg 版本: $FFMPEG_VERSION"

echo ""
echo "🎉 系统环境设置完成！"
echo ""
echo "📋 下一步操作："
echo "1. 运行主程序："
echo "   python3 main.py"
echo ""
echo "2. 如果遇到权限问题，请确保当前用户有 sudo 权限"
echo ""
echo "3. 如果遇到网络问题，程序会自动使用国内镜像源"
echo ""
echo "============================================================"
