"""
PyInstaller 打包脚本 (遵循 python_exe_build_skill.md 规范)
修复：
  1. frozen 模式下 src 包的 sys.path 注入
  2. kokoro / misaki / spacy 等含 C 扩展的包必须 --collect-all
  3. espeakng-loader 包含 DLL，也需全量收集
  4. transformers 需要 --collect-data 采集配置文件
"""
import os
import sys
import time
import subprocess
import PyInstaller.__main__

APP_NAME = "VoxLocal"

# 1. 终止旧进程，等待句柄释放
try:
    subprocess.run(["taskkill", "/F", "/IM", f"{APP_NAME}.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
except Exception:
    pass

# 2. 打包配置
options = [
    'src/main.py',
    f'--name={APP_NAME}',
    '--windowed',           # GUI 应用隐藏控制台
    '--onedir',             # 启动快，便于依赖收集
    '--noconfirm',

    # ── 关键：将项目根加入模块检索路径（解决 from src.xxx import）──
    '--paths=.',

    # ── 图标与资源 ──
    '--icon=src/assets/app.ico',
    '--add-data=src/assets;assets',

    # ── 核心依赖收集 ──
    '--collect-all', 'edge_tts',
    '--collect-all', 'soundfile',

    # ── PySide6 隐式导入 ──
    '--hidden-import', 'PySide6.QtCore',
    '--hidden-import', 'PySide6.QtGui',
    '--hidden-import', 'PySide6.QtWidgets',
    '--hidden-import', 'PySide6.QtMultimedia',
    '--hidden-import', 'PySide6.QtMultimediaWidgets',

    # ── 其他隐式导入 ──
    '--hidden-import', 'sqlite3',
    '--hidden-import', 'asyncio',

    # ── 剪枝：排除未使用的 Qt 子模块（大幅缩减体积）──
    '--exclude-module', 'PySide6.QtWebEngineCore',
    '--exclude-module', 'PySide6.QtWebEngineWidgets',
    '--exclude-module', 'PySide6.Qt3DCore',
    '--exclude-module', 'PySide6.Qt3DAnimation',
    '--exclude-module', 'PySide6.Qt3DExtras',
    '--exclude-module', 'PySide6.Qt3DInput',
    '--exclude-module', 'PySide6.QtQml',
    '--exclude-module', 'PySide6.QtQuick',
    '--exclude-module', 'PySide6.QtQuickWidgets',
    '--exclude-module', 'PySide6.QtDesigner',
    '--exclude-module', 'PySide6.QtSql',
    '--exclude-module', 'PySide6.QtTest',
    '--exclude-module', 'PySide6.QtSensors',
    '--exclude-module', 'PySide6.QtSerialPort',
    '--exclude-module', 'PySide6.QtPdf',
    '--exclude-module', 'PySide6.QtPdfWidgets',
    '--exclude-module', 'tkinter',
    '--exclude-module', 'matplotlib',
    '--exclude-module', 'scipy',
    '--exclude-module', 'IPython',
    '--exclude-module', 'jupyter',
    '--exclude-module', 'notebook',
]

PyInstaller.__main__.run(options)

# 3. 刷新 Windows 图标缓存
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass

# 4. 校验产物
exe_path = os.path.join("dist", APP_NAME, f"{APP_NAME}.exe")
if os.path.exists(exe_path):
    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    sys.stdout.buffer.write(f"\n[OK] Build succeeded!\n   EXE: {os.path.abspath(exe_path)}\n   Size: {size_mb:.1f} MB\n".encode('utf-8'))
else:
    sys.stdout.buffer.write(f"\n[FAIL] Build failed! Not found: {exe_path}\n".encode('utf-8'))
    sys.exit(1)
