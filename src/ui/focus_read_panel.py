"""
沉浸式逐行朗读聚焦面板 (FocusReadPanel)
用于 Tab 2：实现“盲听输入 -> 开口录音(可配3~10次) -> 防作弊默写 -> 自检OK直通下一乱序句”全闭环
"""
import difflib
import html
import time
from enum import Enum, auto
from typing import Optional, Tuple

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
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


def build_diff_html(user_text: str, orig_text: str) -> Tuple[str, str]:
    """
    基于 difflib.SequenceMatcher 生成“我的输入”与“正确原文”的差异高亮 HTML
    仅用于视觉自检对比，不阻断学习者确认通过
    """
    u_clean = user_text.strip()
    o_clean = orig_text.strip()
    matcher = difflib.SequenceMatcher(None, u_clean, o_clean)

    user_parts = []
    orig_parts = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        u_seg = html.escape(u_clean[i1:i2])
        o_seg = html.escape(o_clean[j1:j2])
        if tag == "equal":
            user_parts.append(f'<span style="color:#3fb950;">{u_seg}</span>')
            orig_parts.append(f'<span style="color:#e6edf3;">{o_seg}</span>')
        elif tag == "replace":
            if u_seg:
                user_parts.append(
                    f'<span style="color:#f85149;background:#f8514925;text-decoration:underline;">{u_seg}</span>'
                )
            if o_seg:
                orig_parts.append(
                    f'<span style="color:#ffa657;background:#ffa65725;font-weight:700;">{o_seg}</span>'
                )
        elif tag == "delete":
            if u_seg:
                user_parts.append(
                    f'<span style="color:#f85149;background:#f8514925;text-decoration:line-through;">{u_seg}</span>'
                )
        elif tag == "insert":
            if o_seg:
                orig_parts.append(
                    f'<span style="color:#ffa657;background:#ffa65725;font-weight:700;">{o_seg}</span>'
                )

    return "".join(user_parts), "".join(orig_parts)


class FocusReadPanel(QWidget):
    """逐行跟读与听说读写闭环沉浸面板"""

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
        self._current_text: str = ""
        self._loop_count: int = 1
        self._stage: StudyStage = StudyStage.S1_LISTEN_SPEAK
        self._is_text_revealed: bool = False
        self._target_read_count: int = DEFAULT_TARGET_READ_COUNT
        self._completed_rec_count: int = 0
        self._has_latest_recording: bool = False
        self._is_replaying_recording: bool = False
        self._feedback_lock_until: float = 0.0
        self._rec_start_ts: float = 0.0

        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(100)
        self._rec_timer.timeout.connect(self._on_rec_tick)

        self._setup_ui()
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── 1. 顶部状态栏行 ──
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        title_badge = QLabel("🎧 沉浸跟读台")
        title_badge.setStyleSheet("""
            background: #1f6feb20;
            color: #58a6ff;
            font-weight: 700;
            font-size: 13px;
            padding: 4px 10px;
            border-radius: 6px;
            border: 1px solid #388bfd40;
        """)
        top_row.addWidget(title_badge)

        self.progress_label = QLabel("第 0 / 0 句 · 第 0 轮 (0%)")
        self.progress_label.setStyleSheet("color: #8b949e; font-size: 12px; font-weight: 600;")
        top_row.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: #21262d;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #238636, stop:1 #388bfd);
                border-radius: 3px;
            }
        """)
        top_row.addWidget(self.progress_bar, 1)

        self.btn_back = QPushButton("📝 返回文本库")
        self.btn_back.setStyleSheet("""
            QPushButton {
                background: #21262d;
                color: #8b949e;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #30363d;
                color: #e6edf3;
            }
        """)
        self.btn_back.clicked.connect(self.back_to_text_clicked.emit)
        top_row.addWidget(self.btn_back)

        layout.addLayout(top_row)

        # ── 2. 中央单句卡片（含盲听区、写作区、自检对照区）──
        self.sentence_card = QFrame()
        self.sentence_card.setObjectName("focus_sentence_card")
        self.sentence_card.setStyleSheet("""
            QFrame#focus_sentence_card {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #121720, stop:1 #0d1117);
                border: 1px solid #388bfd50;
                border-radius: 14px;
                padding: 14px;
            }
        """)
        card_layout = QVBoxLayout(self.sentence_card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)

        # 卡片顶部行：循环标签 + 展示/隐藏原文切换按钮
        card_header_row = QHBoxLayout()
        self.loop_tag = QLabel("● 准备中…")
        self.loop_tag.setStyleSheet("color: #388bfd; font-size: 12px; font-weight: 600;")
        card_header_row.addWidget(self.loop_tag)
        card_header_row.addStretch()

        self.btn_toggle_text = QPushButton("👁️ 展示原文")
        self.btn_toggle_text.setObjectName("btn_toggle_text")
        self.btn_toggle_text.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_text.setStyleSheet("""
            QPushButton#btn_toggle_text {
                background: #21262d;
                color: #58a6ff;
                border: 1px solid #388bfd50;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#btn_toggle_text:hover:enabled {
                background: #1f6feb30;
                border-color: #58a6ff;
            }
            QPushButton#btn_toggle_text:disabled {
                background: #161b22;
                color: #484f58;
                border-color: #21262d;
            }
        """)
        self.btn_toggle_text.clicked.connect(self.toggle_text_visibility)
        card_header_row.addWidget(self.btn_toggle_text)
        card_layout.addLayout(card_header_row)

        # 2A. 盲听/原文展示区
        self.sentence_scroll = QScrollArea()
        self.sentence_scroll.setWidgetResizable(True)
        self.sentence_scroll.setFrameShape(QFrame.NoFrame)
        self.sentence_scroll.setStyleSheet("background: transparent;")

        self.sentence_label = QLabel(BLIND_PLACEHOLDER)
        self.sentence_label.setWordWrap(True)
        self.sentence_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.sentence_scroll.setWidget(self.sentence_label)
        card_layout.addWidget(self.sentence_scroll, 1)

        # 2B. 默写输入区 (S3_WRITING)
        self.write_panel = QWidget()
        write_layout = QVBoxLayout(self.write_panel)
        write_layout.setContentsMargins(0, 4, 0, 4)
        write_layout.setSpacing(10)

        write_hint = QLabel("✍️ 请根据记忆与听音默写当前句子（写作期间已屏蔽原音与原文）：")
        write_hint.setStyleSheet("color: #d2a8ff; font-size: 13px; font-weight: 600;")
        write_layout.addWidget(write_hint)

        self.write_input = QPlainTextEdit()
        self.write_input.setPlaceholderText("在此输入您刚才跟读的句子…")
        self.write_input.setMinimumHeight(110)
        self.write_input.setStyleSheet("""
            QPlainTextEdit {
                background: #0d1117;
                color: #f0f6fc;
                border: 1px solid #8957e5;
                border-radius: 8px;
                padding: 12px;
                font-size: 17px;
            }
            QPlainTextEdit:focus {
                border: 2px solid #a371f7;
            }
        """)
        self.write_input.textChanged.connect(self._on_write_text_changed)
        write_layout.addWidget(self.write_input, 1)

        write_btn_row = QHBoxLayout()
        write_btn_row.addStretch()
        self.btn_submit_write = QPushButton("📩 提交默写")
        self.btn_submit_write.setObjectName("btn_submit_write")
        self.btn_submit_write.setFixedHeight(38)
        self.btn_submit_write.setEnabled(False)
        self.btn_submit_write.setStyleSheet("""
            QPushButton#btn_submit_write {
                background: #8957e5;
                color: #ffffff;
                font-weight: 700;
                border: none;
                border-radius: 8px;
                padding: 0 24px;
            }
            QPushButton#btn_submit_write:hover:enabled {
                background: #a371f7;
            }
            QPushButton#btn_submit_write:disabled {
                background: #21262d;
                color: #484f58;
            }
        """)
        self.btn_submit_write.clicked.connect(self.submit_writing)
        write_btn_row.addWidget(self.btn_submit_write)
        write_layout.addLayout(write_btn_row)

        card_layout.addWidget(self.write_panel, 1)

        # 2C. 默写自检对照区 (S4_REVIEWING)
        self.review_panel = QWidget()
        review_layout = QVBoxLayout(self.review_panel)
        review_layout.setContentsMargins(0, 4, 0, 4)
        review_layout.setSpacing(10)

        review_title = QLabel("🔍 默写自检对照：请核对您的输入与正确原文")
        review_title.setStyleSheet("color: #58a6ff; font-size: 13px; font-weight: 600;")
        review_layout.addWidget(review_title)

        review_scroll = QScrollArea()
        review_scroll.setWidgetResizable(True)
        review_scroll.setFrameShape(QFrame.NoFrame)
        review_scroll.setStyleSheet("background: transparent;")

        review_inner = QWidget()
        review_inner_layout = QVBoxLayout(review_inner)
        review_inner_layout.setContentsMargins(0, 0, 0, 0)
        review_inner_layout.setSpacing(8)

        user_title = QLabel("📝 我的输入：")
        user_title.setStyleSheet("color: #8b949e; font-size: 12px; font-weight: 600;")
        review_inner_layout.addWidget(user_title)

        self.review_user_lbl = QLabel("")
        self.review_user_lbl.setWordWrap(True)
        self.review_user_lbl.setTextFormat(Qt.RichText)
        self.review_user_lbl.setStyleSheet("""
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 10px 12px;
            font-size: 16px;
        """)
        review_inner_layout.addWidget(self.review_user_lbl)

        orig_title = QLabel("📖 正确原文：")
        orig_title.setStyleSheet("color: #8b949e; font-size: 12px; font-weight: 600;")
        review_inner_layout.addWidget(orig_title)

        self.review_orig_lbl = QLabel("")
        self.review_orig_lbl.setWordWrap(True)
        self.review_orig_lbl.setTextFormat(Qt.RichText)
        self.review_orig_lbl.setStyleSheet("""
            background: #161b22;
            border: 1px solid #388bfd50;
            border-radius: 8px;
            padding: 10px 12px;
            font-size: 16px;
        """)
        review_inner_layout.addWidget(self.review_orig_lbl)
        review_inner_layout.addStretch()

        review_scroll.setWidget(review_inner)
        review_layout.addWidget(review_scroll, 1)

        review_btn_row = QHBoxLayout()
        review_btn_row.setSpacing(12)
        review_btn_row.addStretch()

        self.btn_rewrite = QPushButton("🔄 重新输入")
        self.btn_rewrite.setObjectName("btn_rewrite")
        self.btn_rewrite.setFixedHeight(38)
        self.btn_rewrite.setStyleSheet("""
            QPushButton#btn_rewrite {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 0 18px;
                font-weight: 600;
            }
            QPushButton#btn_rewrite:hover {
                background: #30363d;
                border-color: #8b949e;
            }
        """)
        self.btn_rewrite.clicked.connect(self.retry_writing)
        review_btn_row.addWidget(self.btn_rewrite)

        self.btn_confirm_ok = QPushButton("✅ 确认 OK（进入下一句）")
        self.btn_confirm_ok.setObjectName("btn_confirm_ok")
        self.btn_confirm_ok.setFixedHeight(38)
        self.btn_confirm_ok.setStyleSheet("""
            QPushButton#btn_confirm_ok {
                background: #238636;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 0 22px;
                font-weight: 700;
            }
            QPushButton#btn_confirm_ok:hover {
                background: #2ea043;
            }
        """)
        self.btn_confirm_ok.clicked.connect(self.confirm_writing_ok)
        review_btn_row.addWidget(self.btn_confirm_ok)
        review_layout.addLayout(review_btn_row)

        card_layout.addWidget(self.review_panel, 1)

        # 播放/录音动态状态提示
        self.playback_status_lbl = QLabel("正在初始化…")
        self.playback_status_lbl.setStyleSheet("""
            color: #8b949e;
            font-size: 12px;
            background: transparent;
        """)
        card_layout.addWidget(self.playback_status_lbl)

        layout.addWidget(self.sentence_card, 1)

        # ── 3. 音频单句播放进度与时间 ──
        audio_prog_row = QHBoxLayout()
        audio_prog_row.setSpacing(10)

        self.audio_slider = QSlider(Qt.Horizontal)
        self.audio_slider.setRange(0, 1000)
        self.audio_slider.setValue(0)
        self.audio_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #21262d;
                height: 5px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #388bfd;
                border: 2px solid #1f6feb;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #238636, stop:1 #388bfd);
                border-radius: 2px;
            }
        """)
        audio_prog_row.addWidget(self.audio_slider, 1)

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setStyleSheet("color: #8b949e; font-size: 11px;")
        audio_prog_row.addWidget(self.time_label)

        layout.addLayout(audio_prog_row)

        # ── 4. 核心控制按键栏（移除上一个/下一个，集成录音/回放/写/参数配置）──
        ctrl_card = QFrame()
        ctrl_card.setObjectName("card")
        ctrl_outer = QVBoxLayout(ctrl_card)
        ctrl_outer.setContentsMargins(14, 10, 14, 10)
        ctrl_outer.setSpacing(10)

        # 4A. 主控制按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_play_pause = QPushButton("⏸ 暂停")
        self.btn_play_pause.setObjectName("btn_play_pause")
        self.btn_play_pause.setToolTip("继续/暂停原音循环朗读")
        self.btn_play_pause.setFixedHeight(40)
        self.btn_play_pause.setStyleSheet("""
            QPushButton#btn_play_pause {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1f6feb, stop:1 #388bfd);
                color: #ffffff;
                font-weight: 700;
                font-size: 13px;
                border: none;
                border-radius: 8px;
                padding: 0 18px;
            }
            QPushButton#btn_play_pause:hover:enabled {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #388bfd, stop:1 #58a6ff);
            }
            QPushButton#btn_play_pause:disabled {
                background: #21262d;
                color: #484f58;
            }
        """)
        self.btn_play_pause.clicked.connect(self.play_pause_clicked.emit)
        btn_row.addWidget(self.btn_play_pause)

        self.btn_replay = QPushButton("🔄 重播本句")
        self.btn_replay.setObjectName("btn_replay")
        self.btn_replay.setFixedHeight(40)
        self.btn_replay.setToolTip("从头重新朗读当前句")
        self.btn_replay.clicked.connect(self.replay_clicked.emit)
        btn_row.addWidget(self.btn_replay)

        self.btn_record = QPushButton("🎙️ 开始录音 (0/3)")
        self.btn_record.setObjectName("btn_record")
        self.btn_record.setFixedHeight(40)
        self.btn_record.setToolTip("点击开始录音，再次点击结束并检验有效朗读（≥1秒）")
        self.btn_record.clicked.connect(self._on_record_btn_clicked)
        btn_row.addWidget(self.btn_record)

        self.btn_replay_rec = QPushButton("🔊 回放我的录音")
        self.btn_replay_rec.setObjectName("btn_replay_rec")
        self.btn_replay_rec.setFixedHeight(40)
        self.btn_replay_rec.setToolTip("回放本句最近一次有效录音")
        self.btn_replay_rec.setStyleSheet("""
            QPushButton#btn_replay_rec {
                background: #1f6feb20;
                color: #58a6ff;
                border: 1px solid #388bfd50;
                border-radius: 8px;
                padding: 0 14px;
                font-weight: 600;
            }
            QPushButton#btn_replay_rec:hover:enabled {
                background: #1f6feb35;
                border-color: #58a6ff;
            }
            QPushButton#btn_replay_rec:disabled {
                background: #161b22;
                color: #484f58;
                border-color: #21262d;
            }
        """)
        self.btn_replay_rec.clicked.connect(self.replay_recording_clicked.emit)
        btn_row.addWidget(self.btn_replay_rec)

        self.btn_write = QPushButton("✍️ 写")
        self.btn_write.setObjectName("btn_write")
        self.btn_write.setFixedHeight(40)
        self.btn_write.setToolTip("进入默写检验（将隐藏原文并暂停原音）")
        self.btn_write.setStyleSheet("""
            QPushButton#btn_write {
                background: #8957e5;
                color: #ffffff;
                font-weight: 700;
                font-size: 14px;
                border: none;
                border-radius: 8px;
                padding: 0 24px;
            }
            QPushButton#btn_write:hover:enabled {
                background: #a371f7;
            }
        """)
        self.btn_write.clicked.connect(self.enter_writing_stage)
        btn_row.addWidget(self.btn_write)

        btn_row.addStretch()
        ctrl_outer.addLayout(btn_row)

        # 4B. 参数配置行（留白停顿 + 目标朗读次数 3~10）
        cfg_row = QHBoxLayout()
        cfg_row.setSpacing(16)

        gap_layout = QHBoxLayout()
        gap_layout.setSpacing(6)
        gap_lbl = QLabel("⏱ 留白停顿:")
        gap_lbl.setStyleSheet("color: #8b949e; font-size: 12px;")
        gap_layout.addWidget(gap_lbl)

        self.gap_slider = QSlider(Qt.Horizontal)
        self.gap_slider.setRange(5, 50)
        self.gap_slider.setValue(10)
        self.gap_slider.setFixedWidth(110)
        self.gap_slider.valueChanged.connect(self._on_gap_slider_changed)
        gap_layout.addWidget(self.gap_slider)

        self.gap_val_lbl = QLabel("1.0 秒")
        self.gap_val_lbl.setStyleSheet("color: #58a6ff; font-weight: 600; font-size: 12px;")
        gap_layout.addWidget(self.gap_val_lbl)
        cfg_row.addLayout(gap_layout)

        target_layout = QHBoxLayout()
        target_layout.setSpacing(6)
        target_lbl = QLabel("🎯 目标朗读次数:")
        target_lbl.setStyleSheet("color: #8b949e; font-size: 12px;")
        target_layout.addWidget(target_lbl)

        self.target_spin = QSpinBox()
        self.target_spin.setRange(MIN_TARGET_READ_COUNT, MAX_TARGET_READ_COUNT)
        self.target_spin.setValue(DEFAULT_TARGET_READ_COUNT)
        self.target_spin.setSuffix(" 次")
        self.target_spin.setFixedWidth(104)
        self.target_spin.setStyleSheet("""
            QSpinBox {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 4px 24px 4px 10px;
                font-weight: 600;
            }
            QSpinBox:disabled {
                color: #484f58;
                border-color: #21262d;
            }
        """)
        self.target_spin.valueChanged.connect(self._on_target_spin_changed)
        target_layout.addWidget(self.target_spin)
        cfg_row.addLayout(target_layout)

        cfg_row.addStretch()
        ctrl_outer.addLayout(cfg_row)

        layout.addWidget(ctrl_card)

    # ────────────────────────── 状态机流转与视图刷新 ──────────────────────────

    def _apply_sentence_display(self):
        if self._is_text_revealed:
            self.sentence_label.setText(self._current_text)
            self.sentence_label.setStyleSheet("""
                color: #f0f6fc;
                font-size: 22px;
                font-weight: 500;
                line-height: 1.6;
                background: transparent;
                padding: 8px 4px;
            """)
            self.btn_toggle_text.setText("🙈 隐藏原文")
        else:
            self.sentence_label.setText(BLIND_PLACEHOLDER)
            self.sentence_label.setStyleSheet("""
                color: #58a6ff;
                font-size: 18px;
                font-weight: 500;
                font-style: italic;
                background: transparent;
                padding: 8px 4px;
            """)
            self.btn_toggle_text.setText("👁️ 展示原文")

    def _sync_stage_ui(self):
        """根据当前 StudyStage 精确控制所有控件显隐与可用性"""
        self._apply_sentence_display()
        stage = self._stage

        in_listen = stage == StudyStage.S1_LISTEN_SPEAK
        in_rec = stage == StudyStage.RECORDING
        in_ready_write = stage == StudyStage.S2_READY_TO_WRITE
        in_writing = stage == StudyStage.S3_WRITING
        in_reviewing = stage == StudyStage.S4_REVIEWING

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
            self.btn_record.setStyleSheet("""
                QPushButton#btn_record {
                    background: #da3633;
                    color: #ffffff;
                    font-weight: 700;
                    border: none;
                    border-radius: 8px;
                    padding: 0 18px;
                }
                QPushButton#btn_record:hover {
                    background: #f85149;
                }
            """)
        else:
            self.btn_record.setText(f"🎙️ 开始录音 ({self._completed_rec_count}/{self._target_read_count})")
            self.btn_record.setStyleSheet("""
                QPushButton#btn_record {
                    background: #1f6feb25;
                    color: #58a6ff;
                    font-weight: 700;
                    border: 1px solid #388bfd;
                    border-radius: 8px;
                    padding: 0 18px;
                }
                QPushButton#btn_record:hover:enabled {
                    background: #1f6feb45;
                }
            """)

        # 回放我的录音按钮：仅当存在最新有效录音时显示；录音/写作/自检期间禁用
        self.btn_replay_rec.setVisible(self._has_latest_recording)
        self.btn_replay_rec.setEnabled(self._has_latest_recording and can_audio)
        self.btn_replay_rec.setText("⏹ 停止回放" if self._is_replaying_recording else "🔊 回放我的录音")

        # 写按钮：仅录音达标且尚未点击进入写时显示
        self.btn_write.setVisible(in_ready_write)
        self.btn_write.setEnabled(in_ready_write)

        # 录音过程中锁定目标次数修改，其余阶段允许动态调整
        self.target_spin.setEnabled(not in_rec)

    def _set_feedback(self, msg: str, tone: str = "normal", hold_sec: float = 0.0):
        color_map = {
            "warn": "#ffa657",
            "ok": "#3fb950",
            "rec": "#f85149",
            "normal": "#8b949e",
        }
        color = color_map.get(tone, "#8b949e")
        weight = "600" if tone in ("warn", "ok", "rec") else "400"
        self.playback_status_lbl.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: {weight}; background: transparent;"
        )
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
            f"🎙️ 正在录音中… 已录 {elapsed:.1f}s（请清晰朗读 ≥ 1.0 秒后点击【结束录音】）",
            tone="rec",
        )

    def set_line_content(self, text: str, round_pos: int, total_count: int, round_num: int = 1):
        """切入新句子，全量重置为盲听 + 录音初始态"""
        self._rec_timer.stop()
        self._current_text = text
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
        self._set_feedback("🔊 正在盲听循环朗读中，请点击【开始录音】完成朗读任务…", tone="normal")

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
            self._set_feedback("🎙️ 正在录音中… 请清晰朗读本句，完成后再次点击【结束录音】", tone="rec")
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
                f"✅ 已完成全部 {self._completed_rec_count} 次有效朗读！请点击【✍️ 写】进入默写检验",
                tone="ok",
                hold_sec=4.0,
            )
        else:
            self._stage = StudyStage.S1_LISTEN_SPEAK
            self._set_feedback(
                f"✅ 录音有效！进度：{self._completed_rec_count}/{self._target_read_count} 次（可点击【回放我的录音】试听）",
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
                self._stage = StudyStage.S1_LISTEN_SPEAK
                self._set_feedback(
                    f"🎯 目标朗读次数已调整为 {new_target} 次，请继续补录 ({self._completed_rec_count}/{new_target})",
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
                    f"✅ 已满足最新目标 ({self._completed_rec_count}/{new_target})，请点击【✍️ 写】进入默写",
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
        self.write_input.clear()
        self.btn_submit_write.setEnabled(False)
        self._stage = StudyStage.S3_WRITING
        self._sync_stage_ui()
        self._set_feedback("✍️ 默写模式：已隐藏原文并暂停声音，请输入后提交", tone="normal")
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

        user_html, orig_html = build_diff_html(user_text, self._current_text)
        self.review_user_lbl.setText(user_html)
        self.review_orig_lbl.setText(orig_html)
        self._stage = StudyStage.S4_REVIEWING
        self._sync_stage_ui()
        self._set_feedback("🔍 请对照原文检查拼写：满意请点【确认 OK】，如需重练请点【重新输入】", tone="normal")

    def retry_writing(self):
        """点击【重新输入】：清空输入框并再次隐藏原文回到默写输入态"""
        if self._stage != StudyStage.S4_REVIEWING:
            return
        self._is_text_revealed = False
        self.write_input.clear()
        self.btn_submit_write.setEnabled(False)
        self._stage = StudyStage.S3_WRITING
        self._sync_stage_ui()
        self._set_feedback("✍️ 已清空重写，请再次输入后提交", tone="normal")
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
            self._set_feedback("🔊 正在循环朗读原音…", tone="normal")

    def show_gap_countdown(self, remaining_sec: float):
        if (
            self._stage in (StudyStage.S1_LISTEN_SPEAK, StudyStage.S2_READY_TO_WRITE)
            and time.monotonic() >= self._feedback_lock_until
        ):
            self._set_feedback(
                f"⏱ 跟读留白停顿中（请开口模仿朗读）… 剩余 {remaining_sec:.1f} 秒",
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
        self.gap_val_lbl.setText(f"{sec:.1f} 秒")
        self.gap_changed.emit(sec)

    @staticmethod
    def _fmt(seconds: float) -> str:
        s = int(seconds)
        return f"{s // 60}:{s % 60:02d}"
