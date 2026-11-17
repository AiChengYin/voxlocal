"""
底部状态栏组件（支持浅色/深色主题无缝切换）
"""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QProgressBar, QFrame
)

from src.ui.theme import DEFAULT_THEME, get_tokens, normalize_theme


class StatusBarWidget(QWidget):

    def __init__(self):
        super().__init__()
        self.setObjectName("status_bar")
        self.setFixedHeight(32)
        self._theme: str = DEFAULT_THEME
        self._engine_available: bool = True
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 18, 0)
        layout.setSpacing(10)

        self.dot = QLabel("●")
        layout.addWidget(self.dot)

        self.engine_lbl = QLabel("就绪")
        layout.addWidget(self.engine_lbl)

        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.Shape.VLine)
        self._sep.setFixedHeight(14)
        layout.addWidget(self._sep)

        self.msg_lbl = QLabel("准备就绪")
        layout.addWidget(self.msg_lbl, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(100)
        self.progress.setFixedHeight(4)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.set_theme(self._theme)

    def set_theme(self, mode: str):
        self._theme = normalize_theme(mode)
        t = get_tokens(self._theme)
        dot_color = t["green"] if self._engine_available else t["red"]
        self.dot.setStyleSheet(f"color: {dot_color}; font-size: 9px; background: transparent;")
        self.engine_lbl.setStyleSheet(f"color: {t['text_2']}; font-size: 11.5px; background: transparent;")
        self.msg_lbl.setStyleSheet(f"color: {t['text_2']}; font-size: 11.5px; background: transparent;")
        self._sep.setStyleSheet(f"background: {t['border_hairline']}; max-width: 1px; border: none;")

    def set_engine_status(self, engine_name: str, available: bool, reason: str = ""):
        self._engine_available = available
        t = get_tokens(self._theme)
        color = t["green"] if available else t["red"]
        self.dot.setStyleSheet(f"color: {color}; font-size: 9px; background: transparent;")
        status = reason if reason else ("就绪" if available else "不可用")
        self.engine_lbl.setText(f"{engine_name} · {status}")

    def set_message(self, msg: str):
        self.msg_lbl.setText(msg)

    def set_busy(self, busy: bool):
        self.progress.setVisible(busy)
