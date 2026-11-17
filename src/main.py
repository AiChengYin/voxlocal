"""
VoxLocal — 本地语音合成桌面应用
主入口文件

遵循 python_exe_build_skill.md 规范：
- Win32 AppUserModelID 注入
- freeze_support() 防子进程重入
- 单例互斥守护
- 全局崩溃日志捕获（打包后闪退诊断）
"""
import sys
import os
import traceback
import multiprocessing

# ── 打包环境路径注入（frozen 模式下 sys.path 需要手动注入项目根）──
if getattr(sys, 'frozen', False):
    # --onedir 模式：exe 在 dist/VoxLocal/，项目根就是 exe 所在目录
    _app_root = os.path.dirname(sys.executable)
    # --windowed 下 sys.stdout/stderr 为 None，loguru 等库会崩溃
    # 用 devnull 替身让这些库安全降级
    import io
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()
else:
    # 开发模式：main.py 在 src/，项目根上溯一级
    _app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

if _app_root not in sys.path:
    sys.path.insert(0, _app_root)

# ── 崩溃日志路径 ──
_crash_log = os.path.join(
    os.path.expanduser("~"), "AppData", "Roaming", "VoxLocal", "crash.log"
)


def _setup_crash_logger():
    """将未捕获异常写入日志文件，方便打包后调试闪退"""
    os.makedirs(os.path.dirname(_crash_log), exist_ok=True)

    def _excepthook(exc_type, exc_value, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            with open(_crash_log, "a", encoding="utf-8") as f:
                import datetime
                f.write(f"\n{'='*60}\n{datetime.datetime.now()}\n{msg}\n")
        except Exception:
            pass
        # 若有控制台则同时输出
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook


# ── Win32 AppUserModelID（在 QApplication 之前注入）──
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "voxlocal.app.client.2026"
        )
    except Exception:
        pass


def main():
    _setup_crash_logger()

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        from PySide6.QtGui import QIcon, QFont
    except Exception as e:
        # PySide6 加载失败时写日志并退出
        with open(_crash_log, "a", encoding="utf-8") as f:
            f.write(f"\n[FATAL] PySide6 import failed: {e}\n{traceback.format_exc()}\n")
        sys.exit(1)

    try:
        from src.utils.single_instance import SingleInstanceGuard
        from src.utils.paths import get_resource_path
    except Exception as e:
        with open(_crash_log, "a", encoding="utf-8") as f:
            f.write(f"\n[FATAL] utils import failed: {e}\n{traceback.format_exc()}\n")
        sys.exit(1)

    # ── 单例守护 ──
    guard = SingleInstanceGuard("Local\\VoxLocal_SingleInstance_Mutex_2026")
    if guard.is_already_running():
        guard.restore_and_activate_existing_window("VoxLocal")
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setApplicationName("VoxLocal")
    app.setOrganizationName("VoxLocal")

    # ── 加载 QSS 主题（方案 E：macOS × Notion 默认浅色，支持后续无刷新切换）──
    try:
        from src.ui.theme import DEFAULT_THEME, build_stylesheet
        app.setStyleSheet(build_stylesheet(DEFAULT_THEME))
    except Exception:
        qss_path = get_resource_path("assets/styles/theme.qss")
        if os.path.exists(qss_path):
            try:
                with open(qss_path, "r", encoding="utf-8") as f:
                    app.setStyleSheet(f.read())
            except Exception:
                pass

    # ── 全局字体 ──
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # ── 加载图标 ──
    ico_path = get_resource_path("assets/app.ico")
    if os.path.exists(ico_path):
        app.setWindowIcon(QIcon(ico_path))

    # ── 启动主窗口 ──
    try:
        from src.ui.main_window import MainWindow
        window = MainWindow()
        window.show()
    except Exception as e:
        msg = traceback.format_exc()
        with open(_crash_log, "a", encoding="utf-8") as f:
            f.write(f"\n[FATAL] MainWindow init failed: {e}\n{msg}\n")
        try:
            QMessageBox.critical(None, "VoxLocal 启动失败",
                f"窗口初始化失败，请查看日志：\n{_crash_log}\n\n错误：{e}")
        except Exception:
            pass
        sys.exit(1)

    sys.exit(app.exec())


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
