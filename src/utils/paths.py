"""
路径管理工具 (遵循 python_exe_build_skill.md 规范)
兼容开发模式与 PyInstaller --onedir 打包模式
"""
import sys
import os
from pathlib import Path


def get_app_root() -> Path:
    """获取应用运行根目录（打包后为 exe 所在目录，开发模式下为项目根目录）"""
    if getattr(sys, 'frozen', False):
        # --onedir：exe 和所有资源在同一目录
        return Path(os.path.dirname(sys.executable))
    # 开发模式：本文件在 src/utils/paths.py，上溯两级到项目根
    try:
        return Path(os.path.abspath(__file__)).parent.parent.parent
    except NameError:
        return Path(os.getcwd())


def get_resource_path(relative_path: str) -> str:
    """获取打入包内的只读静态资源路径（兼容 --onefile / --onedir）"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(str(get_app_root() / 'src'), relative_path)


def get_user_data_dir(app_name: str = "VoxLocal") -> Path:
    """获取用户持久化数据目录（AppData/Roaming）"""
    d = Path.home() / "AppData" / "Roaming" / app_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_output_dir() -> Path:
    """获取音频输出默认目录（Documents/VoxLocal/output）"""
    d = Path.home() / "Documents" / "VoxLocal" / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_bin_dir() -> Path:
    """获取外置可执行文件目录（bin/）"""
    return get_app_root() / "bin"
