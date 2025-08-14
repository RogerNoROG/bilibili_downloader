# 🐧 Ubuntu 系统使用说明

## 问题说明

在 Ubuntu 22.04+ 系统上，Python 默认启用了 PEP 668 的 `externally-managed-environment` 保护机制，防止在系统 Python 环境中直接安装包。这会导致以下错误：

```
error: externally-managed-environment
× This environment is externally managed
```

## 解决方案

### 方法一：使用自动安装脚本（推荐）

1. **下载项目文件**
   ```bash
   git clone <项目地址>
   cd bilibili_downloader
   ```

2. **运行安装脚本**
   ```bash
   chmod +x install_ubuntu.sh
   ./install_ubuntu.sh
   ```

3. **运行主程序**
   ```bash
   python3 main.py
   ```

### 方法二：手动安装依赖

1. **安装系统依赖**
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv python3-pip ffmpeg
   ```

2. **运行主程序**
   ```bash
   python3 main.py
   ```

   程序会自动：
   - 创建虚拟环境 `.venv`
   - 安装 Python 依赖包
   - 配置国内镜像源
   - 重启到虚拟环境中运行

## 工作原理

程序在 Linux 系统上会自动：

1. **检测系统依赖**：检查 `python3`、`python3-venv`、`ffmpeg` 是否已安装
2. **创建虚拟环境**：在项目目录下创建 `.venv` 虚拟环境
3. **配置镜像源**：使用清华大学镜像源加速下载
4. **安装 Python 包**：在虚拟环境中安装所需依赖
5. **重启程序**：切换到虚拟环境解释器重新运行

## 常见问题

### Q: 安装脚本提示权限错误
A: 确保当前用户有 sudo 权限，不要使用 root 用户运行脚本

### Q: 网络连接慢
A: 程序已配置使用清华大学镜像源，如果仍然慢，可以尝试：
```bash
# 手动配置 pip 镜像源
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple/
```

### Q: 虚拟环境创建失败
A: 确保已安装 `python3-venv`：
```bash
sudo apt install -y python3-venv
```

### Q: FFmpeg 不可用
A: 安装 FFmpeg：
```bash
sudo apt install -y ffmpeg
```

## 目录结构

安装完成后，项目目录结构如下：

```
bilibili_downloader/
├── main.py              # 主程序
├── download.py          # 下载模块
├── merge.py             # 合并模块
├── utils.py             # 工具模块
├── requirements.txt     # Python 依赖
├── install_ubuntu.sh    # Ubuntu 安装脚本
├── .venv/               # 虚拟环境（自动创建）
│   ├── bin/
│   ├── lib/
│   └── pip.conf
└── download/            # 下载目录（自动创建）
```

## 验证安装

运行以下命令验证环境是否正确：

```bash
# 检查 Python 版本
python3 --version

# 检查 FFmpeg
ffmpeg -version

# 检查虚拟环境
ls -la .venv/

# 运行程序
python3 main.py
```

## 注意事项

1. **不要删除 `.venv` 目录**：这是项目的虚拟环境
2. **使用 `python3 main.py` 运行**：不要直接运行 `python main.py`
3. **保持网络连接**：首次运行需要下载依赖包
4. **定期更新**：建议定期运行 `sudo apt update` 更新系统包

## 技术支持

如果遇到问题，请检查：

1. Ubuntu 版本是否为 20.04 或更高
2. 是否有足够的磁盘空间（至少 1GB）
3. 网络连接是否正常
4. 用户是否有 sudo 权限

---

**🎉 现在您可以在 Ubuntu 系统上正常使用 Bilibili 视频处理工具了！**
