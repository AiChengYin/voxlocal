"""
VoxLocal 统一主题系统（方案 E：macOS × Notion 极简原生风 · 浅色默认 + 无缝深色切换）
"""
import sys
from typing import Dict

from PySide6.QtWidgets import QApplication, QWidget

VALID_THEMES = ("light", "dark")
DEFAULT_THEME = "light"

THEME_TOKENS: Dict[str, Dict[str, str]] = {
    "light": {
        "name": "light",
        "bg_desktop": "#f3f4f6",
        "bg_window": "#f5f5f7",
        "bg_card": "#ffffff",
        "bg_subtle": "#f7f7f8",
        "bg_hover": "#eceef1",
        "bg_pressed": "#e2e5ea",
        "bg_input": "#ffffff",
        "border_hairline": "#e5e7eb",
        "border_strong": "#d1d5db",
        "text_1": "#111827",
        "text_2": "#4b5563",
        "text_3": "#9ca3af",
        "blue": "#007aff",
        "blue_hover": "#0066d6",
        "blue_pressed": "#0055b3",
        "blue_soft": "rgba(0, 122, 255, 0.10)",
        "blue_border": "rgba(0, 122, 255, 0.28)",
        "red": "#ff3b30",
        "red_hover": "#e0352b",
        "red_soft": "rgba(255, 59, 48, 0.08)",
        "red_border": "rgba(255, 59, 48, 0.26)",
        "purple": "#8944ab",
        "purple_hover": "#733593",
        "purple_soft": "rgba(137, 68, 171, 0.09)",
        "purple_border": "rgba(137, 68, 171, 0.28)",
        "green": "#248a3d",
        "green_hover": "#1e7533",
        "green_soft": "rgba(36, 138, 61, 0.10)",
        "green_border": "rgba(36, 138, 61, 0.26)",
        "amber": "#b45309",
        "amber_soft": "#fff8e6",
        "cyan": "#0284c7",
        "slider_groove": "#e5e7eb",
        "slider_handle_bg": "#ffffff",
        "scrollbar": "#d1d5db",
        "scrollbar_hover": "#9ca3af",
        "diff_ok": "#1a7f37",
        "diff_orig": "#111827",
        "diff_err_fg": "#cf222e",
        "diff_err_bg": "#ffebe9",
        "diff_fix_fg": "#9a6700",
        "diff_fix_bg": "#fff3cd",
        "wave_1": "#007aff",
        "wave_2": "#38bdf8",
    },
    "dark": {
        "name": "dark",
        "bg_desktop": "#111215",
        "bg_window": "#121316",
        "bg_card": "#1b1d22",
        "bg_subtle": "#22252b",
        "bg_hover": "#2b2f37",
        "bg_pressed": "#343942",
        "bg_input": "#15171b",
        "border_hairline": "#2b2f38",
        "border_strong": "#3b404c",
        "text_1": "#f3f4f6",
        "text_2": "#a1a7b3",
        "text_3": "#6b7280",
        "blue": "#0a84ff",
        "blue_hover": "#3399ff",
        "blue_pressed": "#006ee6",
        "blue_soft": "rgba(10, 132, 255, 0.16)",
        "blue_border": "rgba(10, 132, 255, 0.40)",
        "red": "#ff453a",
        "red_hover": "#ff6961",
        "red_soft": "rgba(255, 69, 58, 0.15)",
        "red_border": "rgba(255, 69, 58, 0.42)",
        "purple": "#bf5af2",
        "purple_hover": "#d07ef8",
        "purple_soft": "rgba(191, 90, 242, 0.16)",
        "purple_border": "rgba(191, 90, 242, 0.40)",
        "green": "#30d158",
        "green_hover": "#4cd96e",
        "green_soft": "rgba(48, 209, 88, 0.16)",
        "green_border": "rgba(48, 209, 88, 0.36)",
        "amber": "#ffd60a",
        "amber_soft": "rgba(255, 214, 10, 0.14)",
        "cyan": "#5ac8fa",
        "slider_groove": "#2b2f38",
        "slider_handle_bg": "#f3f4f6",
        "scrollbar": "#3b404c",
        "scrollbar_hover": "#525866",
        "diff_ok": "#30d158",
        "diff_orig": "#f3f4f6",
        "diff_err_fg": "#ff6961",
        "diff_err_bg": "#472326",
        "diff_fix_fg": "#ffd60a",
        "diff_fix_bg": "#3d3316",
        "wave_1": "#0a84ff",
        "wave_2": "#5ac8fa",
    },
}


def normalize_theme(mode: str) -> str:
    return mode if mode in VALID_THEMES else DEFAULT_THEME


def get_tokens(mode: str) -> Dict[str, str]:
    return THEME_TOKENS[normalize_theme(mode)]


def build_stylesheet(mode: str = DEFAULT_THEME) -> str:
    t = get_tokens(mode)
    return f"""
/* VoxLocal — 方案 E：macOS × Notion 极简原生风 ({t['name']}) */

QWidget {{
    background-color: {t['bg_window']};
    color: {t['text_1']};
    font-family: "SF Pro Text", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
    font-size: 13px;
    selection-background-color: {t['blue_soft']};
    selection-color: {t['text_1']};
}}

QMainWindow {{
    background-color: {t['bg_window']};
}}

/* ===== 顶部 Header ===== */
QWidget#header {{
    background-color: {t['bg_card']};
    border-bottom: 1px solid {t['border_hairline']};
}}

QLabel#header_title {{
    font-size: 17px;
    font-weight: 700;
    color: {t['text_1']};
    background: transparent;
}}

QLabel#header_subtitle {{
    font-size: 12px;
    color: {t['text_3']};
    background: transparent;
}}

QLabel#header_version {{
    font-size: 11px;
    color: {t['text_3']};
    background: {t['bg_subtle']};
    border: 1px solid {t['border_hairline']};
    border-radius: 6px;
    padding: 2px 8px;
}}

/* 主题切换分段器 */
QFrame#theme_switch_box {{
    background-color: {t['bg_subtle']};
    border: 1px solid {t['border_hairline']};
    border-radius: 8px;
}}

QPushButton#theme_btn_active {{
    background-color: {t['bg_card']};
    color: {t['text_1']};
    border: 1px solid {t['border_hairline']};
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11.5px;
    font-weight: 600;
}}

QPushButton#theme_btn_inactive {{
    background-color: transparent;
    color: {t['text_3']};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11.5px;
    font-weight: 500;
}}

QPushButton#theme_btn_inactive:hover {{
    color: {t['text_1']};
    background-color: {t['bg_hover']};
}}

/* ===== 通用卡片 ===== */
QFrame#card, QFrame#notion_panel {{
    background-color: {t['bg_card']};
    border: 1px solid {t['border_hairline']};
    border-radius: 14px;
}}

QFrame#subtle_inner_card {{
    background-color: {t['bg_subtle']};
    border: 1px solid {t['border_hairline']};
    border-radius: 10px;
}}

QLabel {{
    color: {t['text_1']};
    background: transparent;
}}

QLabel#section_title {{
    color: {t['text_3']};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.6px;
    background: transparent;
}}

QLabel#panel_title {{
    color: {t['text_1']};
    font-size: 13.5px;
    font-weight: 700;
    background: transparent;
}}

QLabel#cloud_pill {{
    background-color: {t['blue_soft']};
    border: 1px solid {t['blue_border']};
    color: {t['blue']};
    font-size: 10px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 9px;
}}

QLabel#voice_quick_tag {{
    background-color: {t['bg_subtle']};
    color: {t['text_2']};
    border: 1px solid {t['border_hairline']};
    font-size: 10.5px;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 6px;
}}

QLabel#speed_badge {{
    background-color: {t['blue_soft']};
    border: 1px solid {t['blue_border']};
    color: {t['blue']};
    font-size: 11.5px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 6px;
}}

QLabel#char_count, QLabel#time_label {{
    color: {t['text_3']};
    font-size: 11.5px;
    background: transparent;
}}

QFrame#neural_spec_card {{
    background-color: {t['bg_subtle']};
    border: 1px solid {t['border_hairline']};
    border-radius: 10px;
}}

QLabel#neural_spec_title {{
    color: {t['text_1']};
    font-size: 11.5px;
    font-weight: 600;
    background: transparent;
}}

QLabel#neural_spec_body {{
    color: {t['text_2']};
    font-size: 11px;
    background: transparent;
}}

/* ===== 分段按钮 & 芯片按钮 ===== */
QFrame#segment_box {{
    background-color: {t['bg_subtle']};
    border: 1px solid {t['border_hairline']};
    border-radius: 9px;
}}

QPushButton#seg_btn_active {{
    background-color: {t['bg_card']};
    color: {t['blue']};
    border: 1px solid {t['border_hairline']};
    border-radius: 7px;
    font-size: 12px;
    font-weight: 600;
    padding: 6px 10px;
}}

QPushButton#seg_btn_inactive {{
    background-color: transparent;
    color: {t['text_2']};
    border: 1px solid transparent;
    border-radius: 7px;
    font-size: 12px;
    font-weight: 500;
    padding: 6px 10px;
}}

QPushButton#seg_btn_inactive:hover {{
    color: {t['text_1']};
    background-color: {t['bg_hover']};
}}

QPushButton#chip_btn {{
    background-color: {t['bg_card']};
    border: 1px solid {t['border_hairline']};
    border-radius: 6px;
    color: {t['text_2']};
    padding: 5px 0;
    font-size: 11px;
    font-weight: 500;
}}

QPushButton#chip_btn:hover {{
    background-color: {t['bg_hover']};
    color: {t['text_1']};
    border-color: {t['border_strong']};
}}

QPushButton#chip_btn_active {{
    background-color: {t['blue_soft']};
    border: 1px solid {t['blue_border']};
    color: {t['blue']};
    border-radius: 6px;
    padding: 5px 0;
    font-size: 11px;
    font-weight: 600;
}}

/* ===== 文本输入框 ===== */
QPlainTextEdit {{
    background-color: {t['bg_input']};
    color: {t['text_1']};
    border: 1px solid {t['border_strong']};
    border-radius: 10px;
    padding: 12px 14px;
    font-size: 14px;
    selection-background-color: {t['blue_soft']};
}}

QPlainTextEdit:focus {{
    border: 1.5px solid {t['blue']};
}}

/* ===== 通用按钮 ===== */
QPushButton {{
    background-color: {t['bg_card']};
    color: {t['text_1']};
    border: 1px solid {t['border_strong']};
    border-radius: 8px;
    padding: 7px 15px;
    font-size: 12.5px;
    font-weight: 500;
}}

QPushButton:hover:enabled {{
    background-color: {t['bg_subtle']};
}}

QPushButton:pressed:enabled {{
    background-color: {t['bg_pressed']};
}}

QPushButton:disabled {{
    background-color: {t['bg_subtle']};
    color: {t['text_3']};
    border-color: {t['border_hairline']};
}}

QPushButton#btn_ghost {{
    background-color: transparent;
    color: {t['text_2']};
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 5px 10px;
    font-size: 12.5px;
    font-weight: 500;
}}

QPushButton#btn_ghost:hover:enabled {{
    background-color: {t['bg_subtle']};
    color: {t['text_1']};
}}

QPushButton#btn_generate {{
    background-color: {t['blue']};
    color: #ffffff;
    border: none;
    border-radius: 9px;
    padding: 10px 28px;
    font-size: 14px;
    font-weight: 600;
    min-height: 42px;
}}

QPushButton#btn_generate:hover:enabled {{
    background-color: {t['blue_hover']};
}}

QPushButton#btn_generate:pressed:enabled {{
    background-color: {t['blue_pressed']};
}}

QPushButton#btn_generate:disabled {{
    background-color: {t['bg_subtle']};
    color: {t['text_3']};
    border: 1px solid {t['border_hairline']};
}}

/* ===== 下拉框 ===== */
QComboBox {{
    background-color: {t['bg_card']};
    color: {t['text_1']};
    border: 1px solid {t['border_strong']};
    border-radius: 8px;
    padding: 5px 10px;
    font-size: 12.5px;
    font-weight: 500;
    min-height: 30px;
}}

QComboBox:hover {{
    border-color: {t['blue']};
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {t['text_2']};
    margin-right: 6px;
}}

QComboBox QAbstractItemView {{
    background-color: {t['bg_card']};
    color: {t['text_1']};
    border: 1px solid {t['border_strong']};
    border-radius: 8px;
    selection-background-color: {t['blue_soft']};
    selection-color: {t['blue']};
    outline: none;
    padding: 4px;
}}

/* ===== 滑块 ===== */
QSlider::groove:horizontal {{
    background-color: {t['slider_groove']};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background-color: {t['slider_handle_bg']};
    border: 1.5px solid {t['blue']};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {t['blue']};
}}

QSlider::sub-page:horizontal {{
    background-color: {t['blue']};
    border-radius: 2px;
}}

/* ===== 进度条 ===== */
QProgressBar {{
    background-color: {t['slider_groove']};
    border: none;
    border-radius: 3px;
    height: 5px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background-color: {t['blue']};
    border-radius: 3px;
}}

/* ===== 滚动条 ===== */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background-color: {t['scrollbar']};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {t['scrollbar_hover']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}

QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal {{
    background-color: {t['scrollbar']};
    border-radius: 3px;
    min-width: 20px;
}}

/* ===== 标签页 QTabWidget ===== */
QTabWidget::pane {{
    border: none;
    border-top: 1px solid {t['border_hairline']};
    background-color: transparent;
    top: -1px;
    padding-top: 10px;
}}

QTabBar::tab {{
    background-color: {t['bg_subtle']};
    color: {t['text_2']};
    border: 1px solid {t['border_hairline']};
    border-bottom: none;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    padding: 7px 18px;
    margin-right: 4px;
    font-size: 13px;
    font-weight: 500;
    min-width: 112px;
}}

QTabBar::tab:hover {{
    background-color: {t['bg_hover']};
    color: {t['text_1']};
}}

QTabBar::tab:selected {{
    background-color: {t['bg_card']};
    color: {t['blue']};
    border: 1px solid {t['border_hairline']};
    border-bottom: 2px solid {t['bg_card']};
    font-weight: 600;
}}

/* 透明容器（绝不用无选择器 inline background:transparent 污染子控件） */
QWidget#transparent_box, QScrollArea#transparent_scroll {{
    background-color: transparent;
    border: none;
}}

/* ===== 状态栏 ===== */
QWidget#status_bar {{
    background-color: {t['bg_card']};
    border-top: 1px solid {t['border_hairline']};
}}

/* ===== 沉浸跟读台（方案 E：macOS × Notion） ===== */
QFrame#focus_window_card {{
    background-color: {t['bg_card']};
    border: 1px solid {t['border_hairline']};
    border-radius: 14px;
}}

QWidget#focus_toolbar {{
    background-color: {t['bg_subtle']};
    border-bottom: 1px solid {t['border_hairline']};
    border-top-left-radius: 14px;
    border-top-right-radius: 14px;
}}

QFrame#notion_steps_box {{
    background-color: {t['bg_card']};
    border: 1px solid {t['border_hairline']};
    border-radius: 8px;
}}

QLabel#step_active {{
    background-color: {t['blue_soft']};
    color: {t['blue']};
    border-radius: 6px;
    padding: 3px 9px;
    font-size: 11.5px;
    font-weight: 600;
}}

QLabel#step_done {{
    background-color: transparent;
    color: {t['green']};
    border-radius: 6px;
    padding: 3px 9px;
    font-size: 11.5px;
    font-weight: 600;
}}

QLabel#step_idle {{
    background-color: transparent;
    color: {t['text_3']};
    border-radius: 6px;
    padding: 3px 9px;
    font-size: 11.5px;
    font-weight: 500;
}}

QLabel#prop_chip {{
    background-color: {t['bg_subtle']};
    border: 1px solid {t['border_hairline']};
    color: {t['text_2']};
    border-radius: 6px;
    padding: 3px 9px;
    font-size: 11.5px;
    font-weight: 500;
}}

QLabel#prop_chip_rec {{
    background-color: {t['red_soft']};
    border: 1px solid {t['red_border']};
    color: {t['red']};
    border-radius: 6px;
    padding: 3px 9px;
    font-size: 11.5px;
    font-weight: 600;
}}

QFrame#blind_callout {{
    background-color: {t['bg_subtle']};
    border: 1px solid {t['border_hairline']};
    border-radius: 12px;
}}

QFrame#blind_callout_rec {{
    background-color: {t['red_soft']};
    border: 1px solid {t['red_border']};
    border-radius: 12px;
}}

QLabel#lock_pill {{
    background-color: {t['purple_soft']};
    border: 1px solid {t['purple_border']};
    color: {t['purple']};
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 11.5px;
    font-weight: 600;
}}

QPlainTextEdit#focus_write_input {{
    background-color: {t['bg_input']};
    color: {t['text_1']};
    border: 1px solid {t['border_strong']};
    border-radius: 10px;
    padding: 13px 15px;
    font-size: 17px;
}}

QPlainTextEdit#focus_write_input:focus {{
    border: 2px solid {t['purple']};
}}

QFrame#diff_card_user {{
    background-color: {t['bg_subtle']};
    border: 1px solid {t['border_hairline']};
    border-radius: 10px;
}}

QFrame#diff_card_orig {{
    background-color: {t['blue_soft']};
    border: 1px solid {t['blue_border']};
    border-radius: 10px;
}}

QWidget#focus_footer {{
    background-color: {t['bg_subtle']};
    border-top: 1px solid {t['border_hairline']};
    border-bottom-left-radius: 14px;
    border-bottom-right-radius: 14px;
}}

QFrame#native_param_pill {{
    background-color: {t['bg_card']};
    border: 1px solid {t['border_hairline']};
    border-radius: 8px;
}}

QFrame#stepper_box {{
    background-color: {t['bg_subtle']};
    border: 1px solid {t['border_hairline']};
    border-radius: 6px;
}}

QPushButton#stepper_btn {{
    background-color: transparent;
    color: {t['text_1']};
    border: none;
    border-radius: 4px;
    padding: 0px;
    font-size: 14px;
    font-weight: 600;
}}

QPushButton#stepper_btn:hover:enabled {{
    background-color: {t['bg_hover']};
}}

QPushButton#stepper_btn:disabled {{
    color: {t['text_3']};
}}

QSpinBox#stepper_spin {{
    background-color: transparent;
    color: {t['text_1']};
    border: none;
    padding: 0px 2px;
    font-size: 12px;
    font-weight: 600;
}}

QSpinBox#stepper_spin:disabled {{
    color: {t['text_3']};
}}

/* 核心主按钮态 */
QPushButton#btn_record_idle {{
    background-color: {t['blue']};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 0 18px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#btn_record_idle:hover:enabled {{
    background-color: {t['blue_hover']};
}}

QPushButton#btn_record_active {{
    background-color: {t['red']};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 0 18px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#btn_record_active:hover:enabled {{
    background-color: {t['red_hover']};
}}

QPushButton#btn_write, QPushButton#btn_submit_write {{
    background-color: {t['purple']};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 0 20px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#btn_write:hover:enabled, QPushButton#btn_submit_write:hover:enabled {{
    background-color: {t['purple_hover']};
}}
QPushButton#btn_submit_write:disabled {{
    background-color: {t['bg_hover']};
    color: {t['text_3']};
}}

QPushButton#btn_confirm_ok {{
    background-color: {t['green']};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 0 20px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#btn_confirm_ok:hover:enabled {{
    background-color: {t['green_hover']};
}}

QPushButton#btn_replay_rec {{
    background-color: {t['blue_soft']};
    color: {t['blue']};
    border: 1px solid {t['blue_border']};
    border-radius: 8px;
    padding: 0 13px;
    font-size: 12.5px;
    font-weight: 600;
}}
QPushButton#btn_replay_rec:hover:enabled {{
    background-color: {t['blue_border']};
}}
QPushButton#btn_replay_rec:disabled {{
    background-color: {t['bg_subtle']};
    color: {t['text_3']};
    border-color: {t['border_hairline']};
}}

QToolTip {{
    background-color: {t['bg_card']};
    color: {t['text_1']};
    border: 1px solid {t['border_strong']};
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
}}

QMessageBox {{
    background-color: {t['bg_card']};
}}
QMessageBox QLabel {{
    color: {t['text_1']};
}}
"""


def apply_windows_titlebar_theme(window: QWidget, mode: str) -> None:
    """同步 Windows 10/11 原生窗口标题栏深浅色属性（离屏/非 Win 环境安全跳过）"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(window.winId())
        if not hwnd:
            return
        use_dark = 1 if normalize_theme(mode) == "dark" else 0
        val = ctypes.c_int(use_dark)
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Win11 / Win10 20H1+), fallback 19
        dwmapi = ctypes.windll.dwmapi
        res = dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
        if res != 0:
            dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


def apply_theme(app: QApplication, mode: str = DEFAULT_THEME, window: QWidget = None) -> str:
    """将指定主题 QSS 应用到全局 QApplication，并同步原生窗口边框"""
    normalized = normalize_theme(mode)
    if app is not None:
        app.setStyleSheet(build_stylesheet(normalized))
    if window is not None:
        apply_windows_titlebar_theme(window, normalized)
    return normalized
