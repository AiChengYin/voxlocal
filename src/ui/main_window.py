"""
VoxLocal 主窗口 — 逐行循环朗读与沉浸式跟读工作台
"""
import os
import sys
import time
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QTabWidget,
    QMessageBox, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QFont, QKeySequence, QShortcut

from src.engines.models import SynthResult
from src.engines.edge_tts_engine import EdgeTTSEngine, EDGE_TTS_VOICES
from src.core.history_db import HistoryDB
from src.core.audio_manager import AudioManager
from src.core.audio_recorder import AudioRecorder
from src.core.line_reader import LineReaderManager
from src.core.loop_player import LoopPlayer

from src.ui.text_input_panel import TextInputPanel
from src.ui.voice_panel import VoiceParamPanel
from src.ui.focus_read_panel import FocusReadPanel, StudyStage
from src.ui.status_bar import StatusBarWidget
from src.ui.theme import (
    DEFAULT_THEME,
    apply_theme,
    apply_windows_titlebar_theme,
    normalize_theme,
)
from src.utils.paths import get_resource_path


APP_TITLE = "VoxLocal"


class SynthWorker(QThread):
    """后台合成工作线程"""
    finished = Signal(int, object)  # line_idx, SynthResult
    error = Signal(int, str)        # line_idx, error_msg
    progress = Signal(str)

    def __init__(self, engine: EdgeTTSEngine, text: str,
                 voice_id: str, speed: float, line_idx: int):
        super().__init__()
        self.engine = engine
        self.text = text
        self.voice_id = voice_id
        self.speed = speed
        self.line_idx = line_idx

    def run(self):
        try:
            result = self.engine.synthesize(
                self.text, self.voice_id, self.speed,
                progress_cb=lambda msg: self.progress.emit(msg)
            )
            self.finished.emit(self.line_idx, result)
        except Exception as e:
            self.error.emit(self.line_idx, str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1020, 700)
        self.resize(1140, 760)

        # 纯微软云端神经网络引擎
        self._engine = EdgeTTSEngine()

        # 核心跟读控制器与播放器
        self._line_mgr = LineReaderManager()
        self._player = LoopPlayer(self)
        self._current_worker: Optional[SynthWorker] = None
        self._prefetch_worker: Optional[SynthWorker] = None

        self._db = HistoryDB()
        self._audio_mgr = AudioManager()
        self._recorder = AudioRecorder(self)
        self._resume_tts_after_rec: bool = False
        self._resume_tts_after_replay: bool = False

        # 合成计时与状态追踪
        self._synth_timer = QTimer(self)
        self._synth_timer.setInterval(1000)
        self._synth_timer.timeout.connect(self._on_synth_tick)
        self._synth_start_time = 0.0
        self._synth_current_stage = ""
        self._theme: str = DEFAULT_THEME

        self._setup_ui()
        self._init_engine()
        self._init_settings()
        self._connect_signals()

    @property
    def current_theme(self) -> str:
        return self._theme

    # ──────────────────────────────── UI 构建 ────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 顶部 Header
        root_layout.addWidget(self._build_header())

        # 内容区
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(20, 16, 20, 16)
        content_layout.setSpacing(16)

        # 左栏（现代声波流光语音控制面板）
        left_panel = QWidget()
        left_panel.setFixedWidth(290)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        self.voice_panel = VoiceParamPanel()
        left_layout.addWidget(self.voice_panel)

        left_layout.addStretch()

        # 右栏：基于 QTabWidget 的双 Tab 架构
        self.tabs = QTabWidget()
        self.tabs.setObjectName("main_tabs")

        # Tab 0: 📝 课文文本库
        tab_input_widget = QWidget()
        tab_input_widget.setObjectName("transparent_box")
        tab_input_layout = QVBoxLayout(tab_input_widget)
        tab_input_layout.setContentsMargins(0, 0, 0, 0)
        tab_input_layout.setSpacing(12)

        self.text_input = TextInputPanel()
        tab_input_layout.addWidget(self.text_input, 1)

        # 底部操作栏
        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self.btn_start_reading = QPushButton("▶  开始逐行跟读练习")
        self.btn_start_reading.setObjectName("btn_generate")
        self.btn_start_reading.setToolTip("按换行切分句子并进入逐行沉浸循环朗读")
        action_row.addWidget(self.btn_start_reading, 1)

        self.btn_clear = QPushButton("🗑 清空")
        self.btn_clear.setFixedHeight(44)
        self.btn_clear.setFixedWidth(80)
        action_row.addWidget(self.btn_clear)

        tab_input_layout.addLayout(action_row)

        # Tab 1: 🎧 沉浸跟读台
        self.focus_read_panel = FocusReadPanel()

        self.tabs.addTab(tab_input_widget, "📝 课文文本库")
        self.tabs.addTab(self.focus_read_panel, "🎧 沉浸跟读台")

        content_layout.addWidget(left_panel)
        content_layout.addWidget(self.tabs, 1)
        root_layout.addWidget(content, 1)

        # 底部状态栏
        self.status_bar_widget = StatusBarWidget()
        root_layout.addWidget(self.status_bar_widget)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("header")
        header.setFixedHeight(56)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(22, 0, 22, 0)
        layout.setSpacing(10)

        # Logo 区
        logo_label = QLabel("🎙️")
        logo_label.setStyleSheet("font-size: 20px; background: transparent;")
        layout.addWidget(logo_label)

        title_label = QLabel("VoxLocal")
        title_label.setObjectName("header_title")
        layout.addWidget(title_label)

        subtitle = QLabel("逐行循环跟读工作台")
        subtitle.setObjectName("header_subtitle")
        layout.addWidget(subtitle)
        layout.addStretch()

        # 浅色 / 深色主题无缝切换器
        theme_box = QFrame()
        theme_box.setObjectName("theme_switch_box")
        theme_box.setFixedHeight(32)
        theme_layout = QHBoxLayout(theme_box)
        theme_layout.setContentsMargins(3, 3, 3, 3)
        theme_layout.setSpacing(2)

        self.btn_theme_light = QPushButton("☀️ 浅色")
        self.btn_theme_light.setObjectName("theme_btn_active")
        self.btn_theme_light.setFixedHeight(24)
        self.btn_theme_light.setCursor(Qt.PointingHandCursor)
        self.btn_theme_light.setToolTip("切换为 macOS × Notion 极简浅色风")
        self.btn_theme_light.clicked.connect(lambda: self.set_theme("light"))
        theme_layout.addWidget(self.btn_theme_light)

        self.btn_theme_dark = QPushButton("🌙 深色")
        self.btn_theme_dark.setObjectName("theme_btn_inactive")
        self.btn_theme_dark.setFixedHeight(24)
        self.btn_theme_dark.setCursor(Qt.PointingHandCursor)
        self.btn_theme_dark.setToolTip("切换为 macOS 极简深色风")
        self.btn_theme_dark.clicked.connect(lambda: self.set_theme("dark"))
        theme_layout.addWidget(self.btn_theme_dark)

        layout.addWidget(theme_box, 0, Qt.AlignVCenter)

        ver_label = QLabel("v1.2 · Shadowing")
        ver_label.setObjectName("header_version")
        ver_label.setFixedHeight(24)
        layout.addWidget(ver_label, 0, Qt.AlignVCenter)

        return header

    def set_theme(self, mode: str, persist: bool = True):
        """无缝切换全局浅色/深色主题并持久化配置"""
        normalized = normalize_theme(mode)
        self._theme = normalized
        if persist:
            self._db.set_setting("ui_theme", normalized)

        if normalized == "dark":
            self.btn_theme_dark.setObjectName("theme_btn_active")
            self.btn_theme_light.setObjectName("theme_btn_inactive")
        else:
            self.btn_theme_light.setObjectName("theme_btn_active")
            self.btn_theme_dark.setObjectName("theme_btn_inactive")

        for btn in (self.btn_theme_light, self.btn_theme_dark):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        app = QApplication.instance()
        apply_theme(app, normalized, window=self)
        self.voice_panel.set_theme(normalized)
        self.focus_read_panel.set_theme(normalized)
        self.status_bar_widget.set_theme(normalized)

    def showEvent(self, event):
        super().showEvent(event)
        apply_windows_titlebar_theme(self, self._theme)

    # ──────────────────────────────── 信号连接 ────────────────────────────────

    def _connect_signals(self):
        # 语音参数交互
        self.voice_panel.voice_changed.connect(self._on_voice_changed)
        self.voice_panel.speed_changed.connect(self._on_param_changed)
        self.voice_panel.language_changed.connect(self._on_language_changed)

        # 文本库交互
        self.text_input.text_changed.connect(self._on_text_changed)
        self.btn_start_reading.clicked.connect(self._start_reading)
        self.btn_clear.clicked.connect(lambda: self.text_input.set_text(""))

        # 沉浸跟读台控制
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.focus_read_panel.play_pause_clicked.connect(self._on_tts_play_pause_clicked)
        self.focus_read_panel.replay_clicked.connect(self._on_tts_replay_clicked)
        self.focus_read_panel.gap_changed.connect(self._player.set_gap_seconds)
        self.focus_read_panel.back_to_text_clicked.connect(self._back_to_text)

        # 听说读写闭环信号
        self.focus_read_panel.record_start_requested.connect(self._on_record_start_requested)
        self.focus_read_panel.record_stop_requested.connect(self._on_record_stop_requested)
        self.focus_read_panel.replay_recording_clicked.connect(self._on_replay_recording_clicked)
        self.focus_read_panel.target_count_changed.connect(self._on_target_count_changed)
        self.focus_read_panel.write_mode_entered.connect(self._on_write_mode_entered)
        self.focus_read_panel.recording_stage_resumed.connect(self._on_recording_stage_resumed)
        self.focus_read_panel.sentence_completed_ok.connect(self._on_sentence_completed_ok)

        # 麦克风录音器信号
        self._recorder.recording_started.connect(lambda: self.focus_read_panel.set_recording_active(True))
        self._recorder.recording_accepted.connect(self._on_recording_accepted)
        self._recorder.recording_rejected.connect(self._on_recording_rejected)
        self._recorder.error_occurred.connect(self._on_recorder_error)
        self._recorder.playback_state_changed.connect(self._on_rec_playback_state_changed)

        # 循环播放器信号
        self._player.state_changed.connect(self.focus_read_panel.set_play_pause_text)
        self._player.position_changed.connect(self.focus_read_panel.set_audio_progress)
        self._player.gap_tick.connect(self.focus_read_panel.show_gap_countdown)
        self._player.loop_restarted.connect(self._on_loop_restarted)

    # ──────────────────────────────── 引擎加载 ────────────────────────────────

    def _init_engine(self):
        available, reason = self._engine.is_available()
        voices = self._engine.list_voices()
        self.voice_panel.update_voices(voices)
        self.status_bar_widget.set_engine_status(self._engine.get_engine_name(), available, reason)

        lines_count = len(self.text_input.get_lines())
        self.btn_start_reading.setEnabled(available and lines_count > 0)
        self._line_mgr.clear_cache()

    def _init_settings(self):
        valid_voice_ids = {v.voice_id for v in EDGE_TTS_VOICES}
        saved_lang = self._db.get_setting("target_language", "en")
        saved_voice_en = self._db.get_setting("last_voice_en", "en-US-AriaNeural")
        saved_voice_ja = self._db.get_setting("last_voice_ja", "ja-JP-NanamiNeural")
        # 安全降级：旧本地引擎发音人自动迁移为 Edge-TTS 默认发音人
        if saved_voice_en not in valid_voice_ids:
            saved_voice_en = "en-US-AriaNeural"
        if saved_voice_ja not in valid_voice_ids:
            saved_voice_ja = "ja-JP-NanamiNeural"

        self.voice_panel.set_preferred_voice("en", saved_voice_en)
        self.voice_panel.set_preferred_voice("ja", saved_voice_ja)
        self.voice_panel.set_language(saved_lang, emit_signal=False)
        self.text_input.set_language(saved_lang)

        # 加载目标朗读次数配置 (3~10，默认 3)
        raw_target = self._db.get_setting("target_read_count", "3")
        try:
            saved_target = int(raw_target)
        except (TypeError, ValueError):
            saved_target = 3
        self.focus_read_panel.set_target_read_count(saved_target, emit_signal=False)

        # 加载 UI 主题配置 (light / dark，默认 light)
        saved_theme = self._db.get_setting("ui_theme", DEFAULT_THEME)
        self.set_theme(saved_theme, persist=False)

    def _on_language_changed(self, lang: str):
        self._db.set_setting("target_language", lang)
        self.text_input.set_language(lang)
        self._line_mgr.clear_cache()
        self._on_text_changed(self.text_input.get_text())

    def _on_voice_changed(self, voice_id: str):
        if self.voice_panel.get_language() == "ja":
            self._db.set_setting("last_voice_ja", voice_id)
        else:
            self._db.set_setting("last_voice_en", voice_id)
        self._on_param_changed()

    def _on_param_changed(self, *args):
        # 发音人或语速改变，清空当前文本的音频缓存
        self._line_mgr.clear_cache()

    def _on_text_changed(self, text: str):
        available, _ = self._engine.is_available()
        lines_count = len(self.text_input.get_lines())
        self.btn_start_reading.setEnabled(available and lines_count > 0)

    # ────────────────────────── 跟读核心流程控制 ──────────────────────────

    def _start_reading(self):
        """点击开始逐行跟读"""
        raw_text = self.text_input.get_text()
        count = self._line_mgr.set_text(raw_text)
        if count == 0:
            QMessageBox.warning(self, "提示", "请先在文本库中输入要跟读的文本（至少包含一行有效内容）")
            return

        available, reason = self._engine.is_available()
        if not available:
            QMessageBox.critical(self, "引擎不可用", f"当前引擎不可用：\n{reason}")
            return

        # 切换到沉浸跟读 Tab（首句即由 LineReaderManager 随机洗牌抽取）
        self.tabs.setCurrentIndex(1)
        self._play_line(self._line_mgr.current_index)

    def _play_line(self, line_idx: int):
        """播放指定索引行并重置该句听说读写状态"""
        self._player.stop()
        self._recorder.abort_recording()
        self._recorder.clear_latest()
        self._resume_tts_after_rec = False
        self._resume_tts_after_replay = False

        # 停止可能正在执行的当前行合成工作线程
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.terminate()
            self._current_worker.wait(500)
            self._current_worker = None

        line_text = self._line_mgr.get_line(line_idx)
        if not line_text:
            return

        # 更新沉浸界面单句内容与轮次进度（默认盲听隐藏原文）
        round_pos, total, round_num = self._line_mgr.get_round_progress()
        self.focus_read_panel.set_line_content(line_text, round_pos, total, round_num)

        # 1. 检查本地缓存池
        cached = self._line_mgr.get_cache(line_idx)
        if cached:
            # 秒切秒播
            self._on_line_ready(line_idx, cached)
            # 触发乱序队列下一句后台静默预合成
            next_idx = self._line_mgr.peek_next_index()
            if next_idx is not None:
                self._trigger_prefetch(next_idx)
            return

        # 2. 检查后台预合成是否刚好在跑这一句
        if (self._prefetch_worker and self._prefetch_worker.isRunning()
                and self._prefetch_worker.line_idx == line_idx):
            self.focus_read_panel.set_status_message(f"⏳ 正在完成第 {line_idx+1} 句预生成计算…")
            self._current_worker = self._prefetch_worker
            self._prefetch_worker = None
            self._current_worker.finished.disconnect()
            self._current_worker.finished.connect(self._on_worker_finished)
            self._current_worker.error.connect(self._on_worker_error)
            self._current_worker.progress.connect(self.focus_read_panel.set_status_message)
            return

        # 3. 现场启动合成
        self._synth_start_time = time.time()
        self._synth_current_stage = "正在准备合成…"
        self._synth_timer.start()
        self.focus_read_panel.set_status_message(f"⏳ 正在生成第 {line_idx+1} 句语音…")
        self.status_bar_widget.set_busy(True)

        voice_id = self.voice_panel.get_selected_voice_id()
        speed = self.voice_panel.get_speed()

        self._current_worker = SynthWorker(self._engine, line_text, voice_id, speed, line_idx)
        self._current_worker.finished.connect(self._on_worker_finished)
        self._current_worker.error.connect(self._on_worker_error)
        self._current_worker.progress.connect(self._on_worker_progress)
        self._current_worker.start()

    def _on_worker_progress(self, msg: str):
        self._synth_current_stage = msg
        self.focus_read_panel.set_status_message(msg)
        self._on_synth_tick()

    def _on_synth_tick(self):
        if not self._current_worker or not self._current_worker.isRunning():
            return
        elapsed = int(time.time() - self._synth_start_time)
        msg = self._synth_current_stage or "正在合成语音"
        self.status_bar_widget.set_message(f"⏳ {msg} | 已耗时 {elapsed}s")

    def _on_worker_finished(self, line_idx: int, result: SynthResult):
        self._synth_timer.stop()
        self.status_bar_widget.set_busy(False)
        self._line_mgr.set_cache(line_idx, result)

        if line_idx == self._line_mgr.current_index:
            self._on_line_ready(line_idx, result)
            # 立即触发乱序队列下一句的后台异步预合成
            next_idx = self._line_mgr.peek_next_index()
            if next_idx is not None:
                self._trigger_prefetch(next_idx)

    def _on_worker_error(self, line_idx: int, err_msg: str):
        self._synth_timer.stop()
        self.status_bar_widget.set_busy(False)
        self.focus_read_panel.set_status_message(f"❌ 第 {line_idx+1} 句合成失败")
        self.status_bar_widget.set_message(f"❌ 合成失败: {err_msg[:60]}")
        QMessageBox.critical(self, "合成失败", f"第 {line_idx+1} 句生成出错：\n\n{err_msg}")

    def _on_line_ready(self, line_idx: int, result: SynthResult):
        """单句音频准备就绪，载入播放器开启无限循环（录音/写作防作弊态不打断）"""
        stage = self.focus_read_panel.stage
        if stage in (StudyStage.S3_WRITING, StudyStage.S4_REVIEWING):
            return

        self._player.load_and_play(result.audio_path, result.duration_sec)
        if stage == StudyStage.RECORDING:
            self._player.pause()
            self._resume_tts_after_rec = True
            self.focus_read_panel.set_play_pause_text(False)
        else:
            self.focus_read_panel.set_play_pause_text(True)
            self.status_bar_widget.set_message(
                f"🔊 正在循环朗读第 {line_idx+1} 句 [{result.engine_name}] (时长: {result.duration_sec:.1f}s)"
            )

        # 写入历史记录
        try:
            line_text = self._line_mgr.get_line(line_idx) or ""
            voice_id = self.voice_panel.get_selected_voice_id()
            speed = self.voice_panel.get_speed()
            self._db.add_record(
                text=line_text[:200],
                engine=result.engine_name,
                voice=voice_id,
                speed=speed,
                audio_path=result.audio_path,
                duration_sec=result.duration_sec
            )
        except Exception:
            pass

    # ────────────────────────── 预生成流水线 ──────────────────────────

    def _trigger_prefetch(self, next_idx: int):
        """后台静默异步预合成第 next_idx 行"""
        if next_idx is None or next_idx < 0 or next_idx >= self._line_mgr.total_lines:
            return

        # 若已在缓存中，直接跳过
        if self._line_mgr.get_cache(next_idx) is not None:
            return

        # 若预生成线程已在跑这一句，保持运行
        if (self._prefetch_worker and self._prefetch_worker.isRunning()
                and self._prefetch_worker.line_idx == next_idx):
            return

        # 终止跑偏的预生成线程
        if self._prefetch_worker and self._prefetch_worker.isRunning():
            self._prefetch_worker.terminate()
            self._prefetch_worker.wait(300)

        next_text = self._line_mgr.get_line(next_idx)
        if not next_text:
            return

        voice_id = self.voice_panel.get_selected_voice_id()
        speed = self.voice_panel.get_speed()

        self._prefetch_worker = SynthWorker(self._engine, next_text, voice_id, speed, next_idx)
        self._prefetch_worker.finished.connect(self._on_prefetch_finished)
        self._prefetch_worker.start()

    def _on_prefetch_finished(self, line_idx: int, result: SynthResult):
        # 预加载成功静默写入缓存
        self._line_mgr.set_cache(line_idx, result)

    # ────────────────────────── 听说读写闭环控制 ──────────────────────────

    def _on_tab_changed(self, index: int):
        """用户直接点击顶部 Tab 切换回文本库时，自动停止录音与播放"""
        if index == 0:
            self._resume_tts_after_rec = False
            self._resume_tts_after_replay = False
            self._recorder.abort_recording()
            self._recorder.stop_playback()
            self._player.stop()

    def _on_tts_play_pause_clicked(self):
        if self._recorder.is_playing_back:
            self._resume_tts_after_replay = False
            self._recorder.stop_playback()
        self._player.toggle_play()

    def _on_tts_replay_clicked(self):
        if self._recorder.is_playing_back:
            self._resume_tts_after_replay = False
            self._recorder.stop_playback()
        self._player.replay_current()

    def _on_loop_restarted(self, loop_num: int):
        round_pos, _, round_num = self._line_mgr.get_round_progress()
        self.focus_read_panel.update_loop_count(loop_num, round_pos, round_num)

    def _on_record_start_requested(self):
        self._recorder.stop_playback()
        self._resume_tts_after_replay = False
        self._resume_tts_after_rec = self._player.is_active()
        self._player.pause()
        self._recorder.start_recording()

    def _on_record_stop_requested(self):
        self._recorder.stop_recording()

    def _on_recording_accepted(self, wav_path: str, duration_sec: float):
        self.focus_read_panel.increment_recording_count()
        self.status_bar_widget.set_message(
            f"✅ 录音有效 ({duration_sec:.1f}s)，已完成 "
            f"{self.focus_read_panel.completed_rec_count}/{self.focus_read_panel.target_read_count} 次"
        )
        if (
            self._resume_tts_after_rec
            and self.focus_read_panel.stage in (StudyStage.S1_LISTEN_SPEAK, StudyStage.S2_READY_TO_WRITE)
        ):
            self._player.resume()
        self._resume_tts_after_rec = False

    def _on_recording_rejected(self, reason: str):
        self.focus_read_panel.on_recording_failed(reason)
        self.status_bar_widget.set_message(f"⚠️ {reason}")
        if (
            self._resume_tts_after_rec
            and self.focus_read_panel.stage in (StudyStage.S1_LISTEN_SPEAK, StudyStage.S2_READY_TO_WRITE)
        ):
            self._player.resume()
        self._resume_tts_after_rec = False

    def _on_recorder_error(self, err_msg: str):
        self.focus_read_panel.on_recording_failed(err_msg)
        self.status_bar_widget.set_message(f"❌ 麦克风异常: {err_msg[:50]}")
        if (
            self._resume_tts_after_rec
            and self.focus_read_panel.stage in (StudyStage.S1_LISTEN_SPEAK, StudyStage.S2_READY_TO_WRITE)
        ):
            self._player.resume()
        self._resume_tts_after_rec = False
        QMessageBox.critical(self, "麦克风录音错误", err_msg)

    def _on_replay_recording_clicked(self):
        if not self._recorder.has_latest_recording():
            return
        if self._recorder.is_playing_back:
            self._recorder.stop_playback()
            return
        self._resume_tts_after_replay = self._player.is_active()
        self._player.pause()
        started = self._recorder.play_latest()
        if not started and self._resume_tts_after_replay:
            self._resume_tts_after_replay = False
            self._player.resume()

    def _on_rec_playback_state_changed(self, is_playing: bool):
        self.focus_read_panel.set_recording_playback_active(is_playing)
        if not is_playing and self._resume_tts_after_replay:
            self._resume_tts_after_replay = False
            if self.focus_read_panel.stage in (StudyStage.S1_LISTEN_SPEAK, StudyStage.S2_READY_TO_WRITE):
                self._player.resume()

    def _on_target_count_changed(self, count: int):
        self._db.set_setting("target_read_count", str(count))

    def _on_write_mode_entered(self):
        self._resume_tts_after_rec = False
        self._resume_tts_after_replay = False
        self._recorder.stop_playback()
        self._player.pause()
        self.status_bar_widget.set_message("✍️ 已进入默写模式（原文已强制隐藏，声音已暂停）")

    def _on_recording_stage_resumed(self):
        self._player.resume()
        self.status_bar_widget.set_message("🎯 目标朗读次数调高，已回退至录音阶段")

    def _on_sentence_completed_ok(self):
        """默写确认 OK，直接切入下一随机句"""
        self._recorder.clear_latest()
        self._line_mgr.advance_random_next()
        self._play_line(self._line_mgr.current_index)

    def _back_to_text(self):
        """返回文本库 Tab"""
        self._recorder.abort_recording()
        self._recorder.clear_latest()
        self._player.stop()
        self.tabs.setCurrentIndex(0)
        self.status_bar_widget.set_message("已暂停朗读，返回文本库")

    def closeEvent(self, event):
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.terminate()
            self._current_worker.wait(500)
        if self._prefetch_worker and self._prefetch_worker.isRunning():
            self._prefetch_worker.terminate()
            self._prefetch_worker.wait(500)
        self._recorder.abort_recording()
        self._recorder.clear_latest()
        self._player.stop()
        self._db.close()
        super().closeEvent(event)
