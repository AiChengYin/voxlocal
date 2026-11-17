"""
沉浸式逐行朗读聚焦面板 (FocusReadPanel)
方案 E：macOS × Notion 极简原生风，支持浅色/深色主题无缝切换
实现“盲听输入 -> 开口录音(可配3~10次) -> 防作弊默写 -> 自检OK直通下一乱序句”全闭环
"""
import difflib
import html
import time
from enum import Enum, auto
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.ui.theme import DEFAULT_THEME, get_tokens, normalize_theme


BLIND_PLACEHOLDER = "🎧 盲听中，请专注听音输入…"
MIN_TARGET_READ_COUNT = 3
MAX_TARGET_READ_COUNT = 10
DEFAULT_TARGET_READ_COUNT = 3


class StudyStage(Enum):
    """单句听说读写四阶段状态机"""
    S1_LISTEN_SPEAK = auto()     # 听读与录音未达标
    RECORDING = auto()           # 正在麦克风录音采集中
    S2_READY_TO_WRITE = auto()   # 录音已达标，显示【写】按钮
    S3_WRITING = auto()          # 默写输入中（强制隐藏原文、禁用听音）
    S4_REVIEWING = auto()        # 默写自检对照中（确认OK / 重新输入）


def build_diff_html(user_text: str, orig_text: str, theme: str = DEFAULT_THEME) -> Tuple[str, str]:
    """
    基于 difflib.SequenceMatcher 生成“我的输入”与“正确原文”的差异高亮 HTML
    仅用于视觉自检对比，不阻断学习者确认通过
    """
    t = get_tokens(theme)
    u_clean = user_text.strip()
    o_clean = orig_text.strip()
    matcher = difflib.SequenceMatcher(None, u_clean, o_clean)

    user_parts = []
    orig_parts = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        u_seg = html.escape(u_clean[i1:i2])
        o_seg = html.escape(o_clean[j1:j2])
        if tag == "equal":
            user_parts.append(f'<span style="color:{t["diff_ok"]};">{u_seg}</span>')
            orig_parts.append(f'<span style="color:{t["diff_orig"]};">{o_seg}</span>')
        elif tag == "replace":
            if u_seg:
                user_parts.append(
                    f'<span style="color:{t["diff_err_fg"]};background:{t["diff_err_bg"]};'
                    f'text-decoration:line-through;border-radius:3px;">{u_seg}</span>'
                )
            if o_seg:
                orig_parts.append(
                    f'<span style="color:{t["diff_fix_fg"]};background:{t["diff_fix_bg"]};'
                    f'font-weight:700;border-radius:3px;">{o_seg}</span>'
                )
        elif tag == "delete":
            if u_seg:
                user_parts.append(
                    f'<span style="color:{t["diff_err_fg"]};background:{t["diff_err_bg"]};'
                    f'text-decoration:line-through;border-radius:3px;">{u_seg}</span>'
                )
        elif tag == "insert":
            if o_seg:
                orig_parts.append(
                    f'<span style="color:{t["diff_fix_fg"]};background:{t["diff_fix_bg"]};'
                    f'font-weight:700;border-radius:3px;">{o_seg}</span>'
                )

    return "".join(user_parts), "".join(orig_parts)


def _refresh_widget_style(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class FocusReadPanel(QWidget):
    """逐行跟读与听说读写闭环沉浸面板（方案 E：macOS × Notion 极简原生风）"""

    # 信号定义
    play_pause_clicked = Signal()
    replay_clicked = Signal()
    gap_changed = Signal(float)            # 停顿秒数改变
    back_to_text_clicked = Signal()        # 点击返回文本库

    record_start_requested = Signal()      # 请求开始麦克风录音
    record_stop_requested = Signal()       # 请求结束麦克风录音
    replay_recording_clicked = Signal()    # 请求回放最新一次我的录音
    target_count_changed = Signal(int)     # 目标朗读次数配置变更 (3~10)
    write_mode_entered = Signal()          # 点击【写】进入防作弊默写态
    recording_stage_resumed = Signal()     # 从写作态因调大目标次数回退到录音态
    sentence_completed_ok = Signal()       # 默写自检点击【确认 OK】直通下一句

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._theme: str = DEFAULT_THEME
        self._current_text: str = ""
        self._last_user_text: str = ""
        self._loop_count: int = 1
        self._stage: StudyStage = StudyStage.S1_LISTEN_SPEAK
        self._is_text_revealed: bool = False
        self._target_read_count: int = DEFAULT_TARGET_READ_COUNT
        self._completed_rec_count: int = 0
        self._has_latest_recording: bool = False
        self._is_replaying_recording: bool = False
        self._feedback_lock_until: float = 0.0
        self._last_feedback_tone: str = "normal"
        self._rec_start_ts: float = 0.0
        self._rec_pip_widgets: List[QFrame] = []

        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(100)
        self._rec_timer.timeout.connect(self._on_rec_tick)

        self._setup_ui()
        self.set_theme(self._theme)
        self._sync_stage_ui()

    @property
    def stage(self) -> StudyStage:
        return self._stage

    @property
    def is_text_revealed(self) -> bool:
        return self._is_text_revealed

    @property
    def completed_rec_count(self) -> int:
        return self._completed_rec_count

    @property
    def target_read_count(self) -> int:
        return self._target_read_count

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 统一 macOS 极简卡片外框
        self.sentence_card = QFrame()
        self.sentence_card.setObjectName("focus_window_card")
        window_layout = QVBoxLayout(self.sentence_card)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.setSpacing(0)

        # ── 1. 顶部 macOS Toolbar + Notion 4阶段面包屑 ──
        toolbar = QWidget()
        toolbar.setObjectName("focus_toolbar")
        toolbar.setFixedHeight(50)
        top_row = QHBoxLayout(toolbar)
        top_row.setContentsMargins(16, 0, 16, 0)
        top_row.setSpacing(12)

        self.btn_back = QPushButton("‹ 返回文本库")
        self.btn_back.setObjectName("btn_ghost")
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.clicked.connect(self.back_to_text_clicked.emit)
        top_row.addWidget(self.btn_back)

        top_row.addStretch()

        # Notion 分段路径（听 · 说 · 写 · 检）
        steps_box = QFrame()
        steps_box.setObjectName("notion_steps_box")
        steps_layout = QHBoxLayout(steps_box)
        steps_layout.setContentsMargins(3, 3, 3, 3)
        steps_layout.setSpacing(2)

        self._step_listen = QLabel("听 · 盲听")
        self._step_speak = QLabel("说 · 0/3")
        self._step_write = QLabel("写 · 默写")
        self._step_review = QLabel("检 · 对照")
        for lbl in (self._step_listen, self._step_speak, self._step_write, self._step_review):
            lbl.setObjectName("step_idle")
            steps_layout.addWidget(lbl)
        top_row.addWidget(steps_box)

        top_row.addStretch()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(56)
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setTextVisible(False)
        top_row.addWidget(self.progress_bar)

        self.progress_label = QLabel("第 0 / 0 句 · 第 0 轮 (0%)")
        self.progress_label.setObjectName("char_count")
        top_row.addWidget(self.progress_label)

        window_layout.addWidget(toolbar)

        # ── 2. 中央纯净画布 ──
        canvas = QWidget()
        canvas.setObjectName("transparent_box")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(26, 20, 26, 16)
        canvas_layout.setSpacing(14)

        # 2.1 属性徽标行 + 显隐原文按钮
        card_header_row = QHBoxLayout()
        card_header_row.setSpacing(8)

        self.loop_tag = QLabel("● 准备中…")
        self.loop_tag.setObjectName("prop_chip")
        card_header_row.addWidget(self.loop_tag)

        self.rec_prop_chip = QLabel("开口进度 0/3")
        self.rec_prop_chip.setObjectName("prop_chip")
        card_header_row.addWidget(self.rec_prop_chip)

        card_header_row.addStretch()

        self.btn_toggle_text = QPushButton("显示原文")
        self.btn_toggle_text.setObjectName("btn_toggle_text")
        self.btn_toggle_text.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_text.clicked.connect(self.toggle_text_visibility)
        card_header_row.addWidget(self.btn_toggle_text)
        canvas_layout.addLayout(card_header_row)

        # 2A. 盲听 Callout / 原文展示区
        self.sentence_scroll = QScrollArea()
        self.sentence_scroll.setObjectName("transparent_scroll")
        self.sentence_scroll.setWidgetResizable(True)
        self.sentence_scroll.setFrameShape(QFrame.NoFrame)

        listen_container = QWidget()
        listen_container.setObjectName("transparent_box")
        listen_layout = QVBoxLayout(listen_container)
        listen_layout.setContentsMargins(0, 6, 0, 6)
        listen_layout.addStretch()

        self.blind_callout = QFrame()
        self.blind_callout.setObjectName("blind_callout")
        callout_layout = QVBoxLayout(self.blind_callout)
        callout_layout.setContentsMargins(20, 18, 20, 18)
        callout_layout.setSpacing(6)

        self.sentence_label = QLabel(BLIND_PLACEHOLDER)
        self.sentence_label.setWordWrap(True)
        self.sentence_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        callout_layout.addWidget(self.sentence_label)

        self.blind_hint_lbl = QLabel(
            "先听清句子结构与连读韵律，再点击下方「开始录音」开口跟读；如需核对文字可随时点击右上角「显示原文」。"
        )
        self.blind_hint_lbl.setWordWrap(True)
        callout_layout.addWidget(self.blind_hint_lbl)

        listen_layout.addWidget(self.blind_callout)
        listen_layout.addStretch()
        self.sentence_scroll.setWidget(listen_container)
        canvas_layout.addWidget(self.sentence_scroll, 1)

        # 2B. 默写输入区 (S3_WRITING)
        self.write_panel = QWidget()
        self.write_panel.setObjectName("transparent_box")
        write_layout = QVBoxLayout(self.write_panel)
        write_layout.setContentsMargins(0, 4, 0, 4)
        write_layout.setSpacing(10)

        write_hint = QLabel("🔒 防作弊模式 · 已隐藏原文并暂停全部音频")
        write_hint.setObjectName("lock_pill")
        write_layout.addWidget(write_hint, 0, Qt.AlignLeft)

        self.write_input = QPlainTextEdit()
        self.write_input.setObjectName("focus_write_input")
        self.write_input.setPlaceholderText("请根据记忆与听音默写当前句子…")
        self.write_input.setMinimumHeight(110)
        self.write_input.textChanged.connect(self._on_write_text_changed)
        write_layout.addWidget(self.write_input, 1)

        write_btn_row = QHBoxLayout()
        write_btn_row.addStretch()
        self.btn_submit_write = QPushButton("提交默写")
        self.btn_submit_write.setObjectName("btn_submit_write")
        self.btn_submit_write.setFixedHeight(36)
        self.btn_submit_write.setEnabled(False)
        self.btn_submit_write.setCursor(Qt.PointingHandCursor)
        self.btn_submit_write.clicked.connect(self.submit_writing)
        write_btn_row.addWidget(self.btn_submit_write)
        write_layout.addLayout(write_btn_row)

        canvas_layout.addWidget(self.write_panel, 1)

        # 2C. 默写自检对照区 (S4_REVIEWING)
        self.review_panel = QWidget()
        self.review_panel.setObjectName("transparent_box")
        review_layout = QVBoxLayout(self.review_panel)
        review_layout.setContentsMargins(0, 4, 0, 4)
        review_layout.setSpacing(10)

        review_scroll = QScrollArea()
        review_scroll.setObjectName("transparent_scroll")
        review_scroll.setWidgetResizable(True)
        review_scroll.setFrameShape(QFrame.NoFrame)

        review_inner = QWidget()
        review_inner.setObjectName("transparent_box")
        review_inner_layout = QVBoxLayout(review_inner)
        review_inner_layout.setContentsMargins(0, 0, 0, 0)
        review_inner_layout.setSpacing(8)

        user_box = QFrame()
        user_box.setObjectName("diff_card_user")
        user_box_layout = QVBoxLayout(user_box)
        user_box_layout.setContentsMargins(14, 10, 14, 10)
        user_box_layout.setSpacing(4)
        self._review_user_kicker = QLabel("我的输入")
        self._review_user_kicker.setObjectName("section_title")
        user_box_layout.addWidget(self._review_user_kicker)
        self.review_user_lbl = QLabel("")
        self.review_user_lbl.setWordWrap(True)
        self.review_user_lbl.setTextFormat(Qt.RichText)
        self.review_user_lbl.setStyleSheet("font-size: 15.5px; background: transparent;")
        user_box_layout.addWidget(self.review_user_lbl)
        review_inner_layout.addWidget(user_box)

        orig_box = QFrame()
        orig_box.setObjectName("diff_card_orig")
        orig_box_layout = QVBoxLayout(orig_box)
        orig_box_layout.setContentsMargins(14, 10, 14, 10)
        orig_box_layout.setSpacing(4)
        self._review_orig_kicker = QLabel("正确原文")
        self._review_orig_kicker.setObjectName("section_title")
        orig_box_layout.addWidget(self._review_orig_kicker)
        self.review_orig_lbl = QLabel("")
        self.review_orig_lbl.setWordWrap(True)
        self.review_orig_lbl.setTextFormat(Qt.RichText)
        self.review_orig_lbl.setStyleSheet("font-size: 15.5px; background: transparent;")
        orig_box_layout.addWidget(self.review_orig_lbl)
        review_inner_layout.addWidget(orig_box)
        review_inner_layout.addStretch()

        review_scroll.setWidget(review_inner)
        review_layout.addWidget(review_scroll, 1)

        review_btn_row = QHBoxLayout()
        review_btn_row.setSpacing(10)
        review_btn_row.addStretch()

        self.btn_rewrite = QPushButton("重新输入")
        self.btn_rewrite.setObjectName("btn_rewrite")
        self.btn_rewrite.setFixedHeight(36)
        self.btn_rewrite.setCursor(Qt.PointingHandCursor)
        self.btn_rewrite.clicked.connect(self.retry_writing)
        review_btn_row.addWidget(self.btn_rewrite)

        self.btn_confirm_ok = QPushButton("确认 OK（下一句）")
        self.btn_confirm_ok.setObjectName("btn_confirm_ok")
        self.btn_confirm_ok.setFixedHeight(36)
        self.btn_confirm_ok.setCursor(Qt.PointingHandCursor)
        self.btn_confirm_ok.clicked.connect(self.confirm_writing_ok)
        review_btn_row.addWidget(self.btn_confirm_ok)
        review_layout.addLayout(review_btn_row)

        canvas_layout.addWidget(self.review_panel, 1)

        # 2.2 底部状态行 + 极简录音完成条格
        self._status_divider = QFrame()
        self._status_divider.setObjectName("separator")
        self._status_divider.setFixedHeight(1)
        canvas_layout.addWidget(self._status_divider)

        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        self.playback_status_lbl = QLabel("正在初始化…")
        status_row.addWidget(self.playback_status_lbl, 1)

        self._pips_container = QWidget()
        self._pips_container.setObjectName("transparent_box")
        self._pips_layout = QHBoxLayout(self._pips_container)
        self._pips_layout.setContentsMargins(0, 0, 0, 0)
        self._pips_layout.setSpacing(4)
        status_row.addWidget(self._pips_container)
        canvas_layout.addLayout(status_row)

        window_layout.addWidget(canvas, 1)

        # ── 3. 底部 macOS Footer（单句进度 + 主控按钮 + 参数配置）──
        footer = QWidget()
        footer.setObjectName("focus_footer")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(20, 10, 20, 14)
        footer_layout.setSpacing(10)

        # 3A. 音频进度滑块
        audio_prog_row = QHBoxLayout()
        audio_prog_row.setSpacing(10)

        self.audio_slider = QSlider(Qt.Horizontal)
        self.audio_slider.setRange(0, 1000)
        self.audio_slider.setValue(0)
        audio_prog_row.addWidget(self.audio_slider, 1)

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setObjectName("time_label")
        audio_prog_row.addWidget(self.time_label)
        footer_layout.addLayout(audio_prog_row)

        # 3B. 主操作栏（左：播放/重播/回放；中：录音或写；右：停顿+目标步进器）
        action_bar = QHBoxLayout()
        action_bar.setSpacing(10)

        self.btn_play_pause = QPushButton("⏸ 暂停")
        self.btn_play_pause.setObjectName("btn_play_pause")
        self.btn_play_pause.setToolTip("继续/暂停原音循环朗读")
        self.btn_play_pause.setFixedHeight(36)
        self.btn_play_pause.setCursor(Qt.PointingHandCursor)
        self.btn_play_pause.clicked.connect(self.play_pause_clicked.emit)
        action_bar.addWidget(self.btn_play_pause)

        self.btn_replay = QPushButton("↺ 重播本句")
        self.btn_replay.setObjectName("btn_replay")
        self.btn_replay.setFixedHeight(36)
        self.btn_replay.setToolTip("从头重新朗读当前句")
        self.btn_replay.setCursor(Qt.PointingHandCursor)
        self.btn_replay.clicked.connect(self.replay_clicked.emit)
        action_bar.addWidget(self.btn_replay)

        self.btn_replay_rec = QPushButton("回放我的录音")
        self.btn_replay_rec.setObjectName("btn_replay_rec")
        self.btn_replay_rec.setFixedHeight(36)
        self.btn_replay_rec.setToolTip("回放本句最近一次有效录音")
        self.btn_replay_rec.setCursor(Qt.PointingHandCursor)
        self.btn_replay_rec.clicked.connect(self.replay_recording_clicked.emit)
        action_bar.addWidget(self.btn_replay_rec)

        action_bar.addStretch()

        self.btn_record = QPushButton("开始录音 (0/3)")
        self.btn_record.setObjectName("btn_record_idle")
        self.btn_record.setFixedHeight(36)
        self.btn_record.setToolTip("点击开始录音，再次点击结束并检验有效朗读（≥1秒）")
        self.btn_record.setCursor(Qt.PointingHandCursor)
        self.btn_record.clicked.connect(self._on_record_btn_clicked)
        action_bar.addWidget(self.btn_record)

        self.btn_write = QPushButton("✍️ 写 · 进入默写")
        self.btn_write.setObjectName("btn_write")
        self.btn_write.setFixedHeight(36)
        self.btn_write.setToolTip("进入默写检验（将隐藏原文并暂停原音）")
        self.btn_write.setCursor(Qt.PointingHandCursor)
        self.btn_write.clicked.connect(self.enter_writing_stage)
        action_bar.addWidget(self.btn_write)

        action_bar.addStretch()

        # 右侧参数：留白停顿
        gap_pill = QFrame()
        gap_pill.setObjectName("native_param_pill")
        gap_layout = QHBoxLayout(gap_pill)
        gap_layout.setContentsMargins(10, 4, 10, 4)
        gap_layout.setSpacing(6)
        gap_lbl = QLabel("停顿")
        gap_lbl.setObjectName("char_count")
        gap_layout.addWidget(gap_lbl)

        self.gap_slider = QSlider(Qt.Horizontal)
        self.gap_slider.setRange(5, 50)
        self.gap_slider.setValue(10)
        self.gap_slider.setFixedWidth(74)
        self.gap_slider.valueChanged.connect(self._on_gap_slider_changed)
        gap_layout.addWidget(self.gap_slider)

        self.gap_val_lbl = QLabel("1.0s")
        gap_layout.addWidget(self.gap_val_lbl)
        action_bar.addWidget(gap_pill)

        # 右侧参数：目标次数 Apple Stepper（内含完整 QSpinBox API 兼容）
        target_pill = QFrame()
        target_pill.setObjectName("native_param_pill")
        target_layout = QHBoxLayout(target_pill)
        target_layout.setContentsMargins(10, 4, 8, 4)
        target_layout.setSpacing(6)
        target_lbl = QLabel("目标")
        target_lbl.setObjectName("char_count")
        target_layout.addWidget(target_lbl)

        stepper_box = QFrame()
        stepper_box.setObjectName("stepper_box")
        stepper_layout = QHBoxLayout(stepper_box)
        stepper_layout.setContentsMargins(2, 2, 2, 2)
        stepper_layout.setSpacing(2)

        self._btn_target_dec = QPushButton("−")
        self._btn_target_dec.setObjectName("stepper_btn")
        self._btn_target_dec.setFixedSize(22, 22)
        self._btn_target_dec.setCursor(Qt.PointingHandCursor)
        self._btn_target_dec.clicked.connect(lambda: self.target_spin.stepDown())
        stepper_layout.addWidget(self._btn_target_dec)

        self.target_spin = QSpinBox()
        self.target_spin.setObjectName("stepper_spin")
        self.target_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.target_spin.setAlignment(Qt.AlignCenter)
        self.target_spin.setRange(MIN_TARGET_READ_COUNT, MAX_TARGET_READ_COUNT)
        self.target_spin.setValue(DEFAULT_TARGET_READ_COUNT)
        self.target_spin.setSuffix(" 次")
        self.target_spin.setFixedWidth(50)
        self.target_spin.valueChanged.connect(self._on_target_spin_changed)
        stepper_layout.addWidget(self.target_spin)

        self._btn_target_inc = QPushButton("+")
        self._btn_target_inc.setObjectName("stepper_btn")
        self._btn_target_inc.setFixedSize(22, 22)
        self._btn_target_inc.setCursor(Qt.PointingHandCursor)
        self._btn_target_inc.clicked.connect(lambda: self.target_spin.stepUp())
        stepper_layout.addWidget(self._btn_target_inc)

        target_layout.addWidget(stepper_box)
        action_bar.addWidget(target_pill)

        footer_layout.addLayout(action_bar)
        window_layout.addWidget(footer)

        root_layout.addWidget(self.sentence_card, 1)

    # ────────────────────────── 主题同步 ──────────────────────────

    def set_theme(self, mode: str):
        self._theme = normalize_theme(mode)
        t = get_tokens(self._theme)
        self.gap_val_lbl.setStyleSheet(
            f"color: {t['blue']}; font-weight: 600; font-size: 12px; background: transparent;"
        )
        self.blind_hint_lbl.setStyleSheet(
            f"color: {t['text_2']}; font-size: 12.5px; background: transparent;"
        )
        self._review_orig_kicker.setStyleSheet(
            f"color: {t['blue']}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        self._status_divider.setStyleSheet(f"background-color: {t['border_hairline']}; border: none;")
        self._apply_sentence_display()
        self._render_rec_pips()
        self._apply_feedback_style(self._last_feedback_tone)
        if self._stage == StudyStage.S4_REVIEWING and self._last_user_text:
            u_html, o_html = build_diff_html(self._last_user_text, self._current_text, self._theme)
            self.review_user_lbl.setText(u_html)
            self.review_orig_lbl.setText(o_html)

    # ────────────────────────── 状态机流转与视图刷新 ──────────────────────────

    def _apply_sentence_display(self):
        t = get_tokens(self._theme)
        in_rec = self._stage == StudyStage.RECORDING
        if self._is_text_revealed:
            self.blind_callout.setObjectName("blind_callout")
            self.blind_callout.setStyleSheet("QFrame#blind_callout { background: transparent; border: none; }")
            self.blind_hint_lbl.setVisible(False)
            self.sentence_label.setText(self._current_text)
            self.sentence_label.setStyleSheet(
                f"color: {t['text_1']}; font-size: 24px; font-weight: 600; "
                f"background: transparent; padding: 6px 2px;"
            )
            self.btn_toggle_text.setText("隐藏原文")
        else:
            self.blind_callout.setObjectName("blind_callout_rec" if in_rec else "blind_callout")
            self.blind_callout.setStyleSheet("")
            _refresh_widget_style(self.blind_callout)
            self.blind_hint_lbl.setVisible(True)
            self.sentence_label.setText(BLIND_PLACEHOLDER)
            title_color = t["red"] if in_rec else t["text_1"]
            self.sentence_label.setStyleSheet(
                f"color: {title_color}; font-size: 16.5px; font-weight: 600; background: transparent;"
            )
            self.btn_toggle_text.setText("显示原文")

    def _render_rec_pips(self):
        t = get_tokens(self._theme)
        while self._pips_layout.count():
            item = self._pips_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._rec_pip_widgets.clear()
        for i in range(self._target_read_count):
            pip = QFrame()
            pip.setFixedSize(16, 4)
            color = t["green"] if i < self._completed_rec_count else t["border_strong"]
            pip.setStyleSheet(f"background-color: {color}; border-radius: 2px; border: none;")
            self._pips_layout.addWidget(pip)
            self._rec_pip_widgets.append(pip)

    def _sync_stepper_buttons(self, in_rec: bool):
        val = self.target_spin.value()
        self.target_spin.setEnabled(not in_rec)
        self._btn_target_dec.setEnabled(not in_rec and val > MIN_TARGET_READ_COUNT)
        self._btn_target_inc.setEnabled(not in_rec and val < MAX_TARGET_READ_COUNT)

    def _sync_stage_ui(self):
        """根据当前 StudyStage 精确控制所有控件显隐与可用性"""
        self._apply_sentence_display()
        stage = self._stage

        in_listen = stage == StudyStage.S1_LISTEN_SPEAK
        in_rec = stage == StudyStage.RECORDING
        in_ready_write = stage == StudyStage.S2_READY_TO_WRITE
        in_writing = stage == StudyStage.S3_WRITING
        in_reviewing = stage == StudyStage.S4_REVIEWING

        # 顶部 4 阶段路径芯片刷新
        self._step_speak.setText(f"说 · {self._completed_rec_count}/{self._target_read_count}")
        stage_idx = {
            StudyStage.S1_LISTEN_SPEAK: 0,
            StudyStage.RECORDING: 1,
            StudyStage.S2_READY_TO_WRITE: 1,
            StudyStage.S3_WRITING: 2,
            StudyStage.S4_REVIEWING: 3,
        }[stage]
        for idx, lbl in enumerate((self._step_listen, self._step_speak, self._step_write, self._step_review)):
            if idx < stage_idx:
                lbl.setObjectName("step_done")
            elif idx == stage_idx:
                lbl.setObjectName("step_active")
            else:
                lbl.setObjectName("step_idle")
            _refresh_widget_style(lbl)

        # 属性芯片
        self.rec_prop_chip.setText(f"开口进度 {self._completed_rec_count}/{self._target_read_count}")
        self.rec_prop_chip.setObjectName("prop_chip_rec" if in_rec else "prop_chip")
        _refresh_widget_style(self.rec_prop_chip)

        # 中央区域三选一互斥可见
        self.sentence_scroll.setVisible(in_listen or in_rec or in_ready_write)
        self.write_panel.setVisible(in_writing)
        self.review_panel.setVisible(in_reviewing)

        # 展示原文按钮：仅听读与待写态可点，写/自检态禁用
        self.btn_toggle_text.setEnabled(in_listen or in_rec or in_ready_write)

        # 原音播放与重播：仅在未录音且未进入写作/自检态时可用
        can_audio = in_listen or in_ready_write
        self.btn_play_pause.setEnabled(can_audio)
        self.btn_replay.setEnabled(can_audio)

        # 录音按钮：仅在 S1 或 RECORDING 显示，达标后彻底消失
        self.btn_record.setVisible(in_listen or in_rec)
        self.btn_record.setEnabled(in_listen or in_rec)
        if in_rec:
            self.btn_record.setText(f"⏹ 结束录音 ({self._completed_rec_count}/{self._target_read_count})")
            self.btn_record.setObjectName("btn_record_active")
        else:
            self.btn_record.setText(f"🎙️ 开始录音 ({self._completed_rec_count}/{self._target_read_count})")
            self.btn_record.setObjectName("btn_record_idle")
        _refresh_widget_style(self.btn_record)

        # 回放我的录音按钮：仅当存在最新有效录音时显示；录音/写作/自检期间禁用
        self.btn_replay_rec.setVisible(self._has_latest_recording)
        self.btn_replay_rec.setEnabled(self._has_latest_recording and can_audio)
        self.btn_replay_rec.setText("⏹ 停止回放" if self._is_replaying_recording else "🔊 回放我的录音")

        # 写按钮：仅录音达标且尚未点击进入写时显示
        self.btn_write.setVisible(in_ready_write)
        self.btn_write.setEnabled(in_ready_write)

        # 录音过程中锁定目标次数修改，其余阶段允许动态调整
        self._sync_stepper_buttons(in_rec)
        self._render_rec_pips()

    def _apply_feedback_style(self, tone: str):
        t = get_tokens(self._theme)
        color_map = {
            "warn": t["amber"],
            "ok": t["green"],
            "rec": t["red"],
            "normal": t["text_2"],
        }
        color = color_map.get(tone, t["text_2"])
        weight = "600" if tone in ("warn", "ok", "rec") else "400"
        self.playback_status_lbl.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: {weight}; background: transparent;"
        )

    def _set_feedback(self, msg: str, tone: str = "normal", hold_sec: float = 0.0):
        self._last_feedback_tone = tone
        self._apply_feedback_style(tone)
        self.playback_status_lbl.setText(msg)
        self._feedback_lock_until = (time.monotonic() + hold_sec) if hold_sec > 0 else 0.0

    def _on_rec_tick(self):
        if self._stage != StudyStage.RECORDING:
            self._rec_timer.stop()
            return
        elapsed = max(0.0, time.monotonic() - self._rec_start_ts)
        self.btn_record.setText(
            f"⏹ 结束录音 ({self._completed_rec_count}/{self._target_read_count} · {elapsed:.1f}s)"
        )
        self._set_feedback(
            f"正在录音中… 已录 {elapsed:.1f}s（请清晰朗读 ≥ 1.0 秒后点击「结束录音」）",
            tone="rec",
        )

    def set_line_content(self, text: str, round_pos: int, total_count: int, round_num: int = 1):
        """切入新句子，全量重置为盲听 + 录音初始态"""
        self._rec_timer.stop()
        self._current_text = text
        self._last_user_text = ""
        self._loop_count = 1
        self._is_text_revealed = False
        self._completed_rec_count = 0
        self._has_latest_recording = False
        self._is_replaying_recording = False
        self.write_input.clear()
        self.review_user_lbl.clear()
        self.review_orig_lbl.clear()

        self._stage = StudyStage.S1_LISTEN_SPEAK
        self._sync_stage_ui()

        pct = int((round_pos / total_count * 100)) if total_count > 0 else 0
        self.progress_label.setText(f"第 {round_pos} / {total_count} 句 · 第 {round_num} 轮 ({pct}%)")
        self.progress_bar.setValue(pct)
        self.loop_tag.setText(f"● 第 {round_num} 轮 · 第 {round_pos} 句 (第 1 遍)")
        self._set_feedback("正在盲听循环朗读中，请点击「开始录音」完成开口朗读…", tone="normal")

    def toggle_text_visibility(self):
        """手动切换显示/隐藏原文（仅 S1/RECORDING/S2 允许）"""
        if self._stage in (StudyStage.S3_WRITING, StudyStage.S4_REVIEWING):
            return
        self._is_text_revealed = not self._is_text_revealed
        self._apply_sentence_display()

    def _on_record_btn_clicked(self):
        if self._stage == StudyStage.S1_LISTEN_SPEAK:
            self.record_start_requested.emit()
        elif self._stage == StudyStage.RECORDING:
            self.record_stop_requested.emit()

    def set_recording_active(self, active: bool):
        """由外部控制器确认录音设备就绪后切换为录音态"""
        if active:
            self._stage = StudyStage.RECORDING
            self._rec_start_ts = time.monotonic()
            self._set_feedback("正在录音中… 请清晰朗读本句，完成后再次点击「结束录音」", tone="rec")
            self._sync_stage_ui()
            self._rec_timer.start()
        else:
            self._rec_timer.stop()
            if self._stage == StudyStage.RECORDING:
                self._stage = StudyStage.S1_LISTEN_SPEAK
            self._sync_stage_ui()

    def increment_recording_count(self):
        """有效录音达标后计数 +1，达到目标则隐藏录音按钮并显示【写】按钮"""
        self._rec_timer.stop()
        self._completed_rec_count += 1
        self._has_latest_recording = True
        if self._completed_rec_count >= self._target_read_count:
            self._stage = StudyStage.S2_READY_TO_WRITE
            self._set_feedback(
                f"已完成全部 {self._completed_rec_count} 次有效朗读，请点击「写 · 进入默写」",
                tone="ok",
                hold_sec=4.0,
            )
        else:
            self._stage = StudyStage.S1_LISTEN_SPEAK
            self._set_feedback(
                f"录音有效！进度：{self._completed_rec_count}/{self._target_read_count} 次（可点击回放对比）",
                tone="ok",
                hold_sec=4.0,
            )
        self._sync_stage_ui()

    def on_recording_failed(self, reason: str):
        """录音时长/音量不达标或硬件报错时恢复 S1 状态并展示错误提示"""
        self._rec_timer.stop()
        if self._stage == StudyStage.RECORDING:
            self._stage = StudyStage.S1_LISTEN_SPEAK
        self._sync_stage_ui()
        self._set_feedback(f"⚠️ {reason}", tone="warn", hold_sec=4.5)

    def set_recording_playback_active(self, is_playing: bool):
        self._is_replaying_recording = is_playing
        self._sync_stage_ui()

    def set_target_read_count(self, count: int, emit_signal: bool = False):
        """设置目标朗读次数 (3~10) 并立即重算当前句状态"""
        clamped = max(MIN_TARGET_READ_COUNT, min(MAX_TARGET_READ_COUNT, int(count)))
        self.target_spin.blockSignals(True)
        self.target_spin.setValue(clamped)
        self.target_spin.blockSignals(False)
        self._apply_target_count_change(clamped, emit_signal=emit_signal)

    def _on_target_spin_changed(self, val: int):
        self._apply_target_count_change(val, emit_signal=True)

    def _apply_target_count_change(self, new_target: int, emit_signal: bool):
        self._target_read_count = new_target
        if emit_signal:
            self.target_count_changed.emit(new_target)

        if self._stage in (StudyStage.S2_READY_TO_WRITE, StudyStage.S3_WRITING, StudyStage.S4_REVIEWING):
            if self._completed_rec_count < self._target_read_count:
                was_in_write = self._stage in (StudyStage.S3_WRITING, StudyStage.S4_REVIEWING)
                self.write_input.clear()
                self._last_user_text = ""
                self._stage = StudyStage.S1_LISTEN_SPEAK
                self._set_feedback(
                    f"目标朗读次数已调整为 {new_target} 次，请继续补录 ({self._completed_rec_count}/{new_target})",
                    tone="warn",
                    hold_sec=3.5,
                )
                self._sync_stage_ui()
                if was_in_write:
                    self.recording_stage_resumed.emit()
                return
        elif self._stage == StudyStage.S1_LISTEN_SPEAK:
            if self._completed_rec_count >= self._target_read_count:
                self._stage = StudyStage.S2_READY_TO_WRITE
                self._set_feedback(
                    f"已满足最新目标 ({self._completed_rec_count}/{new_target})，请点击「写 · 进入默写」",
                    tone="ok",
                    hold_sec=3.5,
                )
                self._sync_stage_ui()
                return

        self._sync_stage_ui()

    def enter_writing_stage(self):
        """点击【写】进入默写输入态：强制隐藏原文并锁定音频播放"""
        if self._stage != StudyStage.S2_READY_TO_WRITE:
            return
        self._is_text_revealed = False
        self._last_user_text = ""
        self.write_input.clear()
        self.btn_submit_write.setEnabled(False)
        self._stage = StudyStage.S3_WRITING
        self._sync_stage_ui()
        self._set_feedback("默写模式：已隐藏原文并暂停声音，请输入后提交", tone="normal")
        self.write_input.setFocus()
        self.write_mode_entered.emit()

    def _on_write_text_changed(self):
        has_content = bool(self.write_input.toPlainText().strip())
        self.btn_submit_write.setEnabled(has_content)

    def submit_writing(self):
        """提交默写：非空校验后生成对照 HTML 并进入 S4 自检"""
        if self._stage != StudyStage.S3_WRITING:
            return
        user_text = self.write_input.toPlainText()
        if not user_text.strip():
            return

        self._last_user_text = user_text
        user_html, orig_html = build_diff_html(user_text, self._current_text, self._theme)
        self.review_user_lbl.setText(user_html)
        self.review_orig_lbl.setText(orig_html)
        self._stage = StudyStage.S4_REVIEWING
        self._sync_stage_ui()
        self._set_feedback("请对照原文检查拼写：满意点「确认 OK」，需重练点「重新输入」", tone="normal")

    def retry_writing(self):
        """点击【重新输入】：清空输入框并再次隐藏原文回到默写输入态"""
        if self._stage != StudyStage.S4_REVIEWING:
            return
        self._is_text_revealed = False
        self._last_user_text = ""
        self.write_input.clear()
        self.btn_submit_write.setEnabled(False)
        self._stage = StudyStage.S3_WRITING
        self._sync_stage_ui()
        self._set_feedback("已清空重写，请再次输入后提交", tone="normal")
        self.write_input.setFocus()

    def confirm_writing_ok(self):
        """点击【确认 OK】：直接通知控制器进入下一随机句"""
        if self._stage != StudyStage.S4_REVIEWING:
            return
        self.sentence_completed_ok.emit()

    # ────────────────────────── 播放器状态刷新 ──────────────────────────

    def set_play_pause_text(self, is_playing: bool):
        if is_playing:
            self.btn_play_pause.setText("⏸ 暂停")
        else:
            self.btn_play_pause.setText("▶ 继续")

    def update_loop_count(self, loop_num: int, round_pos: int, round_num: int = 1):
        self._loop_count = loop_num
        self.loop_tag.setText(f"● 第 {round_num} 轮 · 第 {round_pos} 句 (第 {loop_num} 遍)")
        if (
            self._stage in (StudyStage.S1_LISTEN_SPEAK, StudyStage.S2_READY_TO_WRITE)
            and time.monotonic() >= self._feedback_lock_until
        ):
            self._set_feedback("正在循环朗读原音…", tone="normal")

    def show_gap_countdown(self, remaining_sec: float):
        if (
            self._stage in (StudyStage.S1_LISTEN_SPEAK, StudyStage.S2_READY_TO_WRITE)
            and time.monotonic() >= self._feedback_lock_until
        ):
            self._set_feedback(
                f"跟读留白停顿中（请开口模仿朗读）… 剩余 {remaining_sec:.1f} 秒",
                tone="normal",
            )

    def set_audio_progress(self, pos_ms: int, dur_ms: int):
        if dur_ms > 0:
            ratio = pos_ms / dur_ms
            self.audio_slider.setValue(int(ratio * 1000))
            self.time_label.setText(f"{self._fmt(pos_ms / 1000)} / {self._fmt(dur_ms / 1000)}")

    def set_status_message(self, msg: str):
        self._set_feedback(msg, tone="normal")

    def _on_gap_slider_changed(self, val: int):
        sec = val / 10.0
        self.gap_val_lbl.setText(f"{sec:.1f}s")
        self.gap_changed.emit(sec)

    @staticmethod
    def _fmt(seconds: float) -> str:
        s = int(seconds)
        return f"{s // 60}:{s % 60:02d}"
