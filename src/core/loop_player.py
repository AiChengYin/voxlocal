"""
循环播放器：基于 QMediaPlayer 实现单句无限循环播放与留白停顿控制
"""
from typing import Optional
from PySide6.QtCore import QObject, Signal, QUrl, QTimer
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


def _enum_val(val) -> int:
    return int(getattr(val, "value", val))


class LoopPlayer(QObject):
    """带停顿间隔的无限循环音频播放器"""

    # 信号定义
    state_changed = Signal(bool)          # True: 正在播放或等待重播, False: 暂停/停止
    position_changed = Signal(int, int)   # (当前毫秒, 总毫秒)
    gap_tick = Signal(float)              # 留白停顿倒计时 (剩余秒数)
    loop_restarted = Signal(int)          # 循环重播 (当前循环第几次)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(1.0)

        self._audio_path: str = ""
        self._duration_ms: int = 0
        self._gap_seconds: float = 1.0    # 默认停顿 1 秒
        self._loop_count: int = 1
        self._is_paused: bool = False
        self._is_in_gap: bool = False
        self._gap_remaining: float = 0.0

        # 进度追踪定时器
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(100)
        self._progress_timer.timeout.connect(self._on_progress_tick)

        # 停顿倒计时定时器 (每 100ms 刷新一次剩余时间)
        self._gap_timer = QTimer(self)
        self._gap_timer.setInterval(100)
        self._gap_timer.timeout.connect(self._on_gap_step)

        self._connect_signals()

    def _connect_signals(self):
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)

    # ────────────────────────── 核心播放控制 ──────────────────────────

    def set_gap_seconds(self, seconds: float):
        """设置跟读留白停顿秒数 (>= 0.0)"""
        self._gap_seconds = max(0.0, float(seconds))

    def get_gap_seconds(self) -> float:
        return self._gap_seconds

    def is_active(self) -> bool:
        """当前是否已载入音频且处于未暂停的循环运行状态（含播放中、加载中及留白停顿中）"""
        return bool(self._audio_path) and not self._is_paused

    def load_and_play(self, audio_path: str, duration_sec: float = 0.0):
        """载入新音频并立即开启循环朗读"""
        self.stop()
        self._audio_path = audio_path
        self._duration_ms = int(duration_sec * 1000) if duration_sec > 0 else 0
        self._loop_count = 1
        self._is_paused = False
        self._is_in_gap = False

        self._player.setSource(QUrl.fromLocalFile(audio_path))
        self._player.play()
        self._progress_timer.start()
        self.state_changed.emit(True)

    def pause(self):
        """暂停播放或暂停停顿倒计时（同时关停两个定时器防止异步信号竞态重播）"""
        self._is_paused = True
        self._gap_timer.stop()
        self._progress_timer.stop()
        self._player.pause()
        self.state_changed.emit(False)

    def resume(self):
        """恢复播放或恢复停顿倒计时"""
        if not self._audio_path:
            return
        self._is_paused = False
        if self._is_in_gap:
            self._gap_timer.start()
        else:
            self._player.play()
            self._progress_timer.start()
        self.state_changed.emit(True)

    def toggle_play(self):
        """切换播放/暂停"""
        is_player_paused = _enum_val(self._player.playbackState()) == _enum_val(
            QMediaPlayer.PlaybackState.PausedState
        )
        if self._is_paused or is_player_paused:
            self.resume()
        else:
            self.pause()

    def replay_current(self):
        """重播本句（从头开始播放）"""
        if not self._audio_path:
            return
        self._gap_timer.stop()
        self._is_in_gap = False
        self._is_paused = False
        self._player.setPosition(0)
        self._player.play()
        self._progress_timer.start()
        self.state_changed.emit(True)
        self.loop_restarted.emit(self._loop_count)

    def stop(self):
        """完全停止并重置"""
        self._gap_timer.stop()
        self._progress_timer.stop()
        self._is_in_gap = False
        self._is_paused = False
        self._gap_remaining = 0.0
        self._audio_path = ""
        self._player.stop()
        self.position_changed.emit(0, self._duration_ms)
        self.state_changed.emit(False)

    def seek(self, ratio: float):
        """跳转进度 (0.0 ~ 1.0)"""
        dur = self._player.duration() or self._duration_ms
        if dur > 0:
            pos = int(ratio * dur)
            self._player.setPosition(pos)

    # ────────────────────────── 内部事件处理 ──────────────────────────

    def _on_media_status_changed(self, status):
        if _enum_val(status) != _enum_val(QMediaPlayer.MediaStatus.EndOfMedia):
            return

        self._progress_timer.stop()
        self.position_changed.emit(self._duration_ms, self._duration_ms)

        # 若此时已被暂停（例如刚进入录音或默写模式），挂起于留白态而不自动启动重播
        if self._is_paused or not self._audio_path:
            self._is_in_gap = True
            self._gap_remaining = max(0.1, self._gap_seconds)
            return

        if self._gap_seconds <= 0.05:
            self._loop_count += 1
            self._player.setPosition(0)
            self._player.play()
            self._progress_timer.start()
            self.state_changed.emit(True)
            self.loop_restarted.emit(self._loop_count)
        else:
            self._is_in_gap = True
            self._gap_remaining = self._gap_seconds
            self.state_changed.emit(True)
            self.gap_tick.emit(self._gap_remaining)
            self._gap_timer.start()

    def _on_gap_step(self):
        if self._is_paused or not self._audio_path:
            self._gap_timer.stop()
            return

        self._gap_remaining -= 0.1
        if self._gap_remaining <= 0.05:
            self._gap_timer.stop()
            self._is_in_gap = False
            self._loop_count += 1
            self._player.setPosition(0)
            self._player.play()
            self._progress_timer.start()
            self.state_changed.emit(True)
            self.loop_restarted.emit(self._loop_count)
        else:
            self.gap_tick.emit(max(0.0, self._gap_remaining))

    def _on_progress_tick(self):
        pos = self._player.position()
        dur = self._player.duration() or self._duration_ms
        if dur > 0:
            self.position_changed.emit(pos, dur)

    def _on_duration_changed(self, dur_ms: int):
        if dur_ms > 0:
            self._duration_ms = dur_ms

    def _on_playback_state_changed(self, state):
        state_code = _enum_val(state)
        if state_code == _enum_val(QMediaPlayer.PlaybackState.PlayingState):
            if not self._is_paused:
                self.state_changed.emit(True)
        elif state_code == _enum_val(QMediaPlayer.PlaybackState.StoppedState):
            # 仅在显式停止或暂停时发出 False，避免单遍结束过渡到留白时按钮闪烁为“继续”
            if self._is_paused or not self._audio_path:
                self.state_changed.emit(False)
