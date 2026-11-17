"""
音频播放器面板
"""
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QFrame
)
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


class PlayerPanel(QWidget):

    def __init__(self):
        super().__init__()
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(1.0)
        self._duration = 0.0
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        outer = QFrame()
        outer.setObjectName("card")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(14, 12, 14, 12)
        outer_layout.setSpacing(8)

        # 标题行
        title_row = QHBoxLayout()
        section_lbl = QLabel("音频预览")
        section_lbl.setObjectName("section_title")
        title_row.addWidget(section_lbl)
        title_row.addStretch()
        self.time_label = QLabel("--:-- / --:--")
        self.time_label.setObjectName("time_label")
        title_row.addWidget(self.time_label)
        outer_layout.addLayout(title_row)

        # 进度条
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.setValue(0)
        self.progress_slider.setEnabled(False)
        self.progress_slider.sliderPressed.connect(self._on_slider_pressed)
        self.progress_slider.sliderReleased.connect(self._on_slider_released)
        outer_layout.addWidget(self.progress_slider)

        # 控制按钮行
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)

        self.btn_play = QPushButton("▶")
        self.btn_play.setObjectName("btn_play")
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self._toggle_play)
        ctrl_row.addWidget(self.btn_play)

        self.file_label = QLabel("尚未生成音频")
        self.file_label.setObjectName("char_count")
        self.file_label.setMaximumWidth(360)
        ctrl_row.addWidget(self.file_label, 1)

        outer_layout.addLayout(ctrl_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(outer)

        # 定时刷新进度
        self._timer = QTimer()
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._update_progress)

    def _connect_signals(self):
        self._player.playbackStateChanged.connect(self._on_playback_state)
        self._player.durationChanged.connect(self._on_duration_changed)

    def load_file(self, file_path: str, duration_sec: float = 0.0):
        self._duration = duration_sec
        self._player.setSource(QUrl.fromLocalFile(file_path))
        self.progress_slider.setEnabled(True)
        self.btn_play.setEnabled(True)
        fname = os.path.basename(file_path)
        self.file_label.setText(fname)
        self.time_label.setText(f"0:00 / {self._fmt(duration_sec)}")
        # 自动播放
        self._player.play()
        self._timer.start()

    def reset(self):
        self._player.stop()
        self._timer.stop()
        self.progress_slider.setValue(0)
        self.progress_slider.setEnabled(False)
        self.btn_play.setEnabled(False)
        self.btn_play.setText("▶")
        self.file_label.setText("正在生成…")
        self.time_label.setText("--:-- / --:--")

    def _toggle_play(self):
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()
            self._timer.start()

    def _on_playback_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("⏸")
        else:
            self.btn_play.setText("▶")
            if state == QMediaPlayer.PlaybackState.StoppedState:
                self._timer.stop()

    def _on_duration_changed(self, duration_ms: int):
        if duration_ms > 0:
            self._duration = duration_ms / 1000.0

    def _update_progress(self):
        pos_ms = self._player.position()
        dur_ms = self._player.duration()
        if dur_ms > 0:
            ratio = pos_ms / dur_ms
            self.progress_slider.setValue(int(ratio * 1000))
            self.time_label.setText(
                f"{self._fmt(pos_ms / 1000)} / {self._fmt(dur_ms / 1000)}"
            )

    def _on_slider_pressed(self):
        self._timer.stop()

    def _on_slider_released(self):
        dur_ms = self._player.duration()
        if dur_ms > 0:
            ratio = self.progress_slider.value() / 1000.0
            self._player.setPosition(int(ratio * dur_ms))
        self._timer.start()

    @staticmethod
    def _fmt(seconds: float) -> str:
        s = int(seconds)
        return f"{s // 60}:{s % 60:02d}"
