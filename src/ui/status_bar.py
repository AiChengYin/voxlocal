"""
底部状态栏组件
"""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QProgressBar, QFrame
)
from PySide6.QtCore import Qt, QTimer


class StatusBarWidget(QWidget):

    def __init__(self):
        super().__init__()
        self.setFixedHeight(32)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            StatusBarWidget {
                background-color: #161b22;
                border-top: 1px solid #21262d;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        # 引擎状态点
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: #3fb950; font-size: 10px; background: transparent;")
        layout.addWidget(self.dot)

        self.engine_lbl = QLabel("就绪")
        self.engine_lbl.setStyleSheet("color: #8b949e; font-size: 11px; background: transparent;")
        layout.addWidget(self.engine_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #21262d; background: #21262d; max-width: 1px;")
        layout.addWidget(sep)

        self.msg_lbl = QLabel("准备就绪")
        self.msg_lbl.setStyleSheet("color: #8b949e; font-size: 11px; background: transparent;")
        layout.addWidget(self.msg_lbl, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)   # 不定进度
        self.progress.setFixedWidth(100)
        self.progress.setFixedHeight(4)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

    def set_engine_status(self, engine_name: str, available: bool, reason: str = ""):
        color = "#3fb950" if available else "#f85149"
        self.dot.setStyleSheet(f"color: {color}; font-size: 10px; background: transparent;")
        status = reason if reason else ("就绪" if available else "不可用")
        self.engine_lbl.setText(f"{engine_name} · {status}")

    def set_message(self, msg: str):
        self.msg_lbl.setText(msg)

    def set_busy(self, busy: bool):
        self.progress.setVisible(busy)
