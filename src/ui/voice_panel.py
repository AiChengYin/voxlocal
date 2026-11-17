"""
语音调谐中心（方案 C：现代声波流光工作台）
基于 oil-ui 规范重新设计：动态声波、流光分段控制器、芯片档位与神经规格注脚
"""
import random
from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QSlider, QFrame, QPushButton, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPainter, QColor

from src.engines.models import VoiceInfo


class SoundWaveVisualizer(QWidget):
    """5 频段动态跳动声波频谱微组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(26, 16)
        self._heights = [5, 12, 8, 15, 6]
        self._targets = [12, 6, 14, 8, 13]
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._animate_step)
        self._timer.start()

    def _animate_step(self):
        for i in range(5):
            diff = self._targets[i] - self._heights[i]
            if abs(diff) <= 1:
                self._targets[i] = random.randint(4, 15)
            else:
                self._heights[i] += 1 if diff > 0 else -1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bar_w = 3
        gap = 2
        for i, h in enumerate(self._heights):
            x = i * (bar_w + gap)
            y = 16 - h
            # 错落采用电感紫与电光青
            color = QColor("#6366f1") if i % 2 == 1 else QColor("#06b6d4")
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(x, y, bar_w, h, 1, 1)


class VoiceParamPanel(QWidget):
    """现代声波流光语音控制面板 (Cyber Fluent Studio)"""

    voice_changed = Signal(str)
    speed_changed = Signal(float)
    language_changed = Signal(str)  # "en" 或 "ja"

    def __init__(self):
        super().__init__()
        self._all_voices: List[VoiceInfo] = []
        self._current_lang: str = "en"
        self._preferred_voice_en: str = "en-US-AriaNeural"
        self._preferred_voice_ja: str = "ja-JP-NanamiNeural"
        self._setup_ui()

    def _setup_ui(self):
        outer = QFrame()
        outer.setObjectName("cyber_panel")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(14, 14, 14, 14)
        outer_layout.setSpacing(14)

        # ── 1. 顶部声波频谱头 ──
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self.wave_widget = SoundWaveVisualizer(self)
        header_row.addWidget(self.wave_widget)

        panel_title = QLabel("语音调谐中心")
        panel_title.setObjectName("cyber_title")
        header_row.addWidget(panel_title)

        header_row.addStretch()

        cloud_badge = QLabel("NEURAL CLOUD")
        cloud_badge.setObjectName("cyber_cloud_badge")
        header_row.addWidget(cloud_badge)

        outer_layout.addLayout(header_row)

        # ── 2. 语种通道切换 ──
        lang_sec_row = QHBoxLayout()
        lang_lbl = QLabel("语种通道")
        lang_lbl.setObjectName("cyber_section_title")
        lang_sec_row.addWidget(lang_lbl)
        lang_sec_row.addStretch()
        lang_active_lbl = QLabel("ACTIVE")
        lang_active_lbl.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700;")
        lang_sec_row.addWidget(lang_active_lbl)
        outer_layout.addLayout(lang_sec_row)

        segment_row = QHBoxLayout()
        segment_row.setSpacing(6)

        self.btn_lang_en = QPushButton("🇬🇧 英语 (EN)")
        self.btn_lang_en.setObjectName("neon_btn_active")
        self.btn_lang_en.setCursor(Qt.PointingHandCursor)
        self.btn_lang_en.clicked.connect(lambda: self.set_language("en"))
        segment_row.addWidget(self.btn_lang_en, 1)

        self.btn_lang_ja = QPushButton("🇯🇵 日语 (JA)")
        self.btn_lang_ja.setObjectName("neon_btn_inactive")
        self.btn_lang_ja.setCursor(Qt.PointingHandCursor)
        self.btn_lang_ja.clicked.connect(lambda: self.set_language("ja"))
        segment_row.addWidget(self.btn_lang_ja, 1)

        outer_layout.addLayout(segment_row)

        # ── 3. 神经网络发音角色卡 ──
        voice_sec_row = QHBoxLayout()
        voice_title = QLabel("神经网络角色")
        voice_title.setObjectName("cyber_section_title")
        voice_sec_row.addWidget(voice_title)
        voice_sec_row.addStretch()

        self.tag_badge = QLabel("首选推荐")
        self.tag_badge.setObjectName("voice_quick_tag")
        voice_sec_row.addWidget(self.tag_badge)
        outer_layout.addLayout(voice_sec_row)

        voice_card = QFrame()
        voice_card.setObjectName("cyber_card_inner")
        card_layout = QVBoxLayout(voice_card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(8)

        self.voice_combo = QComboBox()
        self.voice_combo.setObjectName("cyber_combo")
        self.voice_combo.currentIndexChanged.connect(self._on_combo_changed)
        card_layout.addWidget(self.voice_combo)

        meta_row = QHBoxLayout()
        self.accent_lbl = QLabel("美式英语 · 女声")
        self.accent_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; background: transparent;")
        meta_row.addWidget(self.accent_lbl)
        meta_row.addStretch()

        spec_lbl = QLabel("24kHz 声学模型")
        spec_lbl.setStyleSheet("color: #06b6d4; font-size: 10px; font-weight: 600; background: transparent;")
        meta_row.addWidget(spec_lbl)

        card_layout.addLayout(meta_row)
        outer_layout.addWidget(voice_card)

        # ── 4. 跟读步频与芯片按键 ──
        speed_sec_row = QHBoxLayout()
        speed_title = QLabel("跟读步频")
        speed_title.setObjectName("cyber_section_title")
        speed_sec_row.addWidget(speed_title)
        speed_sec_row.addStretch()

        self.speed_badge = QLabel("1.0×")
        self.speed_badge.setObjectName("speed_cyber_badge")
        speed_sec_row.addWidget(self.speed_badge)
        outer_layout.addLayout(speed_sec_row)

        speed_box = QFrame()
        speed_box.setObjectName("cyber_card_inner")
        speed_box_layout = QVBoxLayout(speed_box)
        speed_box_layout.setContentsMargins(10, 10, 10, 10)
        speed_box_layout.setSpacing(10)

        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setObjectName("cyber_slider")
        self.speed_slider.setRange(50, 200)   # 0.5x ~ 2.0x (×100)
        self.speed_slider.setValue(100)
        self.speed_slider.setTickInterval(10)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_box_layout.addWidget(self.speed_slider)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)

        self.chip_08 = QPushButton("0.8× 细磨")
        self.chip_08.setObjectName("chip_btn")
        self.chip_08.setCursor(Qt.PointingHandCursor)
        self.chip_08.clicked.connect(lambda: self.set_speed(0.8))
        chips_row.addWidget(self.chip_08, 1)

        self.chip_10 = QPushButton("1.0× 标准")
        self.chip_10.setObjectName("chip_btn_active")
        self.chip_10.setCursor(Qt.PointingHandCursor)
        self.chip_10.clicked.connect(lambda: self.set_speed(1.0))
        chips_row.addWidget(self.chip_10, 1)

        self.chip_12 = QPushButton("1.2× 冲刺")
        self.chip_12.setObjectName("chip_btn")
        self.chip_12.setCursor(Qt.PointingHandCursor)
        self.chip_12.clicked.connect(lambda: self.set_speed(1.2))
        chips_row.addWidget(self.chip_12, 1)

        speed_box_layout.addLayout(chips_row)
        outer_layout.addWidget(speed_box)

        # ── 5. 底部声学规格注脚 ──
        spec_card = QFrame()
        spec_card.setObjectName("neural_spec_card")
        spec_layout = QVBoxLayout(spec_card)
        spec_layout.setContentsMargins(10, 10, 10, 10)
        spec_layout.setSpacing(4)

        spec_header = QLabel("⚡ 微软神经语流渲染")
        spec_header.setObjectName("neural_spec_title")
        spec_layout.addWidget(spec_header)

        spec_body = QLabel("端到端深度神经网络直通，提供拟真连读音变与停顿韵律，跟读延迟低至 120ms。")
        spec_body.setObjectName("neural_spec_body")
        spec_body.setWordWrap(True)
        spec_layout.addWidget(spec_body)

        outer_layout.addWidget(spec_card)

        # 外部布局包裹
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(outer)

    # ────────────────────────── 逻辑与交互 ──────────────────────────

    def _on_speed_changed(self, value: int):
        speed = value / 100.0
        self.speed_badge.setText(f"{speed:.1f}×")
        self._update_chip_styles(speed)
        self.speed_changed.emit(speed)

    def set_speed(self, speed: float):
        self.speed_slider.setValue(int(speed * 100))

    def _update_chip_styles(self, speed: float):
        for btn, target in [(self.chip_08, 0.8), (self.chip_10, 1.0), (self.chip_12, 1.2)]:
            is_active = abs(speed - target) < 0.05
            btn.setObjectName("chip_btn_active" if is_active else "chip_btn")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _on_combo_changed(self):
        voice_id = self.get_selected_voice_id()
        if voice_id:
            if self._current_lang == "ja":
                self._preferred_voice_ja = voice_id
            else:
                self._preferred_voice_en = voice_id

            # 更新角色口音与快捷标签
            self._update_voice_metadata(voice_id)
            self.voice_changed.emit(voice_id)

    def _update_voice_metadata(self, voice_id: str):
        for v in self._all_voices:
            if v.voice_id == voice_id:
                self.accent_lbl.setText(v.accent_desc or f"{v.language} · {v.gender}")
                self.tag_badge.setText(v.tag or "推荐")
                break

    def set_language(self, lang: str, emit_signal: bool = True):
        """设置当前语种 ('en' 或 'ja') 并刷新语音列表"""
        if lang not in ("en", "ja"):
            lang = "en"
        self._current_lang = lang

        # 更新霓虹分段按钮样式
        if lang == "ja":
            self.btn_lang_ja.setObjectName("neon_btn_active")
            self.btn_lang_en.setObjectName("neon_btn_inactive")
        else:
            self.btn_lang_en.setObjectName("neon_btn_active")
            self.btn_lang_ja.setObjectName("neon_btn_inactive")

        for btn in (self.btn_lang_en, self.btn_lang_ja):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self._populate_combo()

        if emit_signal:
            self.language_changed.emit(lang)

    def get_language(self) -> str:
        return self._current_lang

    def set_preferred_voice(self, lang: str, voice_id: str):
        if lang == "ja":
            self._preferred_voice_ja = voice_id
        else:
            self._preferred_voice_en = voice_id

    def update_voices(self, voices: List[VoiceInfo]):
        """接收当前引擎提供的全部语音，并根据当前语种过滤填充"""
        self._all_voices = voices
        self._populate_combo()

    def _populate_combo(self):
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()

        # 根据当前语种过滤
        filtered = [
            v for v in self._all_voices
            if v.language.lower().startswith(self._current_lang)
        ]
        if not filtered and self._all_voices:
            filtered = self._all_voices

        prev_lang = None
        target_idx = 0
        preferred_id = self._preferred_voice_ja if self._current_lang == "ja" else self._preferred_voice_en

        for v in filtered:
            lang = v.language
            # 添加分组标题
            if lang != prev_lang:
                self.voice_combo.addItem(f"── {lang} ──")
                idx = self.voice_combo.count() - 1
                item = self.voice_combo.model().item(idx)
                if item:
                    item.setEnabled(False)
                prev_lang = lang

            self.voice_combo.addItem(f"  {v.display_name}", userData=v.voice_id)
            current_idx = self.voice_combo.count() - 1
            if v.voice_id == preferred_id:
                target_idx = current_idx

        # 若未匹配到 preferred_id，寻找第一个可用的语音项
        if target_idx == 0:
            for i in range(self.voice_combo.count()):
                item = self.voice_combo.model().item(i)
                if item and item.isEnabled():
                    target_idx = i
                    break

        if self.voice_combo.count() > 0:
            self.voice_combo.setCurrentIndex(target_idx)

        self.voice_combo.blockSignals(False)

        selected_id = self.get_selected_voice_id()
        if selected_id:
            self._update_voice_metadata(selected_id)
            self.voice_changed.emit(selected_id)

    def select_voice(self, voice_id: str):
        for i in range(self.voice_combo.count()):
            if self.voice_combo.itemData(i) == voice_id:
                self.voice_combo.setCurrentIndex(i)
                break

    def get_selected_voice_id(self) -> str:
        return self.voice_combo.currentData() or ""

    def get_speed(self) -> float:
        return self.speed_slider.value() / 100.0
