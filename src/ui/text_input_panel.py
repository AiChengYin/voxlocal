"""
文本输入面板（方案 E：macOS × Notion 极简原生风）
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QFrame
)
from PySide6.QtCore import Signal


class TextInputPanel(QWidget):
    text_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        outer = QFrame()
        outer.setObjectName("card")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(16, 14, 16, 14)
        outer_layout.setSpacing(10)

        # 标题行
        title_row = QHBoxLayout()
        section_lbl = QLabel("输入文本")
        section_lbl.setObjectName("section_title")
        title_row.addWidget(section_lbl)
        title_row.addStretch()
        self.char_count = QLabel("0 行有效句子 | 0 字符")
        self.char_count.setObjectName("prop_chip")
        title_row.addWidget(self.char_count)
        outer_layout.addLayout(title_row)

        # 文本编辑区
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "在此粘贴或输入英文文本（支持以换行或标点分句）…\n\n"
            "进入跟读台后将按乱序无限循环朗读，完成开口录音与默写自检后自动切入下一句。\n\n"
            "例如：\n"
            "The quick brown fox jumps over the lazy dog.\n"
            "Practice makes perfect.\n"
            "Keep up the good work and never give up."
        )
        self.editor.setMinimumHeight(180)
        self.editor.textChanged.connect(self._on_text_changed)
        outer_layout.addWidget(self.editor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(outer)

    def set_language(self, lang: str):
        """根据当前选定语言更新占位提示文字"""
        if lang == "ja":
            self.editor.setPlaceholderText(
                "在此粘贴或输入日文文本（支持以换行或句号「。」分句）…\n\n"
                "进入跟读台后将按乱序无限循环朗读，完成开口录音与默写自检后自动切入下一句。\n\n"
                "例如：\n"
                "吾輩は猫である。名前はまだ無い。\n"
                "どこで生れたかとんと見当がつかぬ。\n"
                "何でも薄暗いじめじめした所でニャーニャー泣いていた事だけは記憶している。"
            )
        else:
            self.editor.setPlaceholderText(
                "在此粘贴或输入英文文本（支持以换行或标点分句）…\n\n"
                "进入跟读台后将按乱序无限循环朗读，完成开口录音与默写自检后自动切入下一句。\n\n"
                "例如：\n"
                "The quick brown fox jumps over the lazy dog.\n"
                "Practice makes perfect.\n"
                "Keep up the good work and never give up."
            )

    def _on_text_changed(self):
        text = self.editor.toPlainText()
        count = len(text)
        lines = self.get_lines()
        self.char_count.setText(f"{len(lines)} 行有效句子 | {count:,} 字符")
        self.text_changed.emit(text)

    def get_text(self) -> str:
        return self.editor.toPlainText()

    def get_lines(self) -> list:
        from src.core.line_reader import LineReaderManager
        return LineReaderManager.split_sentences(self.editor.toPlainText())

    def set_text(self, text: str):
        self.editor.setPlainText(text)
