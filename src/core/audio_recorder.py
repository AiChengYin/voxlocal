"""
麦克风录音与轻量有效性判定模块 (基于 PySide6 QtMultimedia)
"""
import os
import time
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import soundfile as sf
from PySide6.QtCore import QBuffer, QIODevice, QObject, QUrl, Signal
from PySide6.QtMultimedia import (
    QAudio,
    QAudioDevice,
    QAudioFormat,
    QAudioOutput,
    QAudioSource,
    QMediaDevices,
    QMediaPlayer,
)

MIN_RECORD_DURATION_SEC = 1.0
MIN_RECORD_RMS = 0.0012
MIN_RECORD_PEAK = 0.006


def _enum_val(val) -> int:
    return int(getattr(val, "value", val))


def pcm_bytes_to_mono_float32(
    raw_bytes: bytes,
    sample_format: QAudioFormat.SampleFormat,
    channel_count: int,
) -> np.ndarray:
    """将 QtMultimedia 采集的原始 PCM 字节流安全对齐、解码并混音为去直流单声道 float32 [-1.0, 1.0]"""
    if not raw_bytes:
        return np.array([], dtype=np.float32)

    channels = max(1, int(channel_count))
    fmt_code = _enum_val(sample_format)

    if fmt_code == _enum_val(QAudioFormat.SampleFormat.Float):
        dtype = np.float32
        scale = 1.0
        offset = 0.0
    elif fmt_code == _enum_val(QAudioFormat.SampleFormat.Int32):
        dtype = np.int32
        scale = 2147483648.0
        offset = 0.0
    elif fmt_code == _enum_val(QAudioFormat.SampleFormat.UInt8):
        dtype = np.uint8
        scale = 128.0
        offset = 128.0
    else:
        dtype = np.int16
        scale = 32768.0
        offset = 0.0

    itemsize = np.dtype(dtype).itemsize
    frame_bytes = itemsize * channels
    usable_bytes = (len(raw_bytes) // frame_bytes) * frame_bytes
    if usable_bytes <= 0:
        return np.array([], dtype=np.float32)

    arr = np.frombuffer(raw_bytes[:usable_bytes], dtype=dtype).astype(np.float32)
    if offset != 0.0:
        arr = (arr - offset) / scale
    elif scale != 1.0:
        arr = arr / scale

    arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=-1.0)
    if channels > 1:
        arr = arr.reshape(-1, channels).mean(axis=1)

    # 消除声卡直流偏置 (DC Offset)，防止恒定偏置干扰能量计算
    if len(arr) > 1:
        arr = arr - float(np.mean(arr))

    return np.clip(arr, -1.0, 1.0).astype(np.float32)


def normalize_audio_for_playback(
    samples: np.ndarray,
    target_peak: float = 0.85,
    max_gain: float = 35.0,
) -> np.ndarray:
    """
    对采集通过的语音进行安全峰值归一化（AGC），
    解决部分笔记本麦克风阵列原始电平偏低导致【回放我的录音】声音过小的问题
    """
    if samples is None or len(samples) == 0:
        return np.array([], dtype=np.float32)
    peak = float(np.max(np.abs(samples)))
    if peak <= 1e-6:
        return samples.astype(np.float32)
    if peak < target_peak:
        gain = min(target_peak / peak, max_gain)
        return np.clip(samples * gain, -1.0, 1.0).astype(np.float32)
    return np.clip(samples, -1.0, 1.0).astype(np.float32)


def evaluate_recording_pcm(
    samples: np.ndarray,
    sample_rate: int,
    min_duration_sec: float = MIN_RECORD_DURATION_SEC,
    min_rms: float = MIN_RECORD_RMS,
    min_peak: float = MIN_RECORD_PEAK,
) -> Tuple[bool, float, float, float, str]:
    """
    轻量级录音有效性判定：
    1. 录音时长 >= min_duration_sec (默认 1.0 秒)
    2. 综合全局 RMS 与 200ms 滑动窗口最大活跃 RMS >= min_rms 或 Peak >= min_peak
    返回: (是否通过, 时长秒数, 有效RMS, Peak, 拒绝原因)
    """
    if sample_rate <= 0 or samples is None or len(samples) == 0:
        return False, 0.0, 0.0, 0.0, f"录音时长不足 {min_duration_sec:.1f} 秒（当前 0.00 秒），请完整朗读"

    mono = np.asarray(samples, dtype=np.float32).ravel()
    mono = np.nan_to_num(mono, nan=0.0, posinf=1.0, neginf=-1.0)
    duration_sec = len(mono) / float(sample_rate)
    global_rms = float(np.sqrt(np.mean(mono ** 2)))
    peak = float(np.max(np.abs(mono)))

    # 计算 200ms 窗口最大活跃 RMS，避免说话前后停顿稀释整段均值
    win_size = max(1, int(sample_rate * 0.2))
    if len(mono) >= win_size:
        n_wins = len(mono) // win_size
        frames = mono[: n_wins * win_size].reshape(n_wins, win_size)
        max_win_rms = float(np.max(np.sqrt(np.mean(frames ** 2, axis=1))))
    else:
        max_win_rms = global_rms

    effective_rms = max(global_rms, max_win_rms * 0.8)

    if duration_sec < min_duration_sec:
        return (
            False,
            duration_sec,
            effective_rms,
            peak,
            f"录音时长不足 {min_duration_sec:.1f} 秒（当前 {duration_sec:.2f} 秒），请完整朗读",
        )

    if effective_rms < min_rms and peak < min_peak:
        return (
            False,
            duration_sec,
            effective_rms,
            peak,
            "未检测到有效朗读声音，请靠近麦克风重试",
        )

    return True, duration_sec, effective_rms, peak, ""


class AudioRecorder(QObject):
    """基于 QtMultimedia 的单句跟读录音与最新录音回放控制器"""

    recording_started = Signal()
    recording_accepted = Signal(str, float)  # (wav_path, duration_sec)
    recording_rejected = Signal(str)         # reason
    error_occurred = Signal(str)             # error_msg
    playback_state_changed = Signal(bool)    # True: 正在回放我的录音, False: 已停止

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._audio_source: Optional[QAudioSource] = None
        self._buffer: Optional[QBuffer] = None
        self._active_format: Optional[QAudioFormat] = None
        self._is_recording: bool = False
        self._seq_counter: int = 0
        self._latest_wav_path: Optional[str] = None

        self._temp_dir = Path(os.environ.get("TEMP", "/tmp")) / "VoxLocal" / "recordings"
        self._temp_dir.mkdir(parents=True, exist_ok=True)

        # 独立最新录音回放播放器
        self._playback_player = QMediaPlayer(self)
        self._playback_output = QAudioOutput(self)
        self._playback_player.setAudioOutput(self._playback_output)
        self._playback_output.setVolume(1.0)
        self._playback_player.playbackStateChanged.connect(self._on_playback_state_changed)

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def is_playing_back(self) -> bool:
        return _enum_val(self._playback_player.playbackState()) == _enum_val(
            QMediaPlayer.PlaybackState.PlayingState
        )

    @property
    def latest_wav_path(self) -> Optional[str]:
        return self._latest_wav_path

    def has_latest_recording(self) -> bool:
        return bool(self._latest_wav_path and os.path.exists(self._latest_wav_path))

    # ────────────────────────── 录音控制 ──────────────────────────

    def _select_audio_format(self, device: QAudioDevice) -> QAudioFormat:
        """优先采用声卡原生首选格式，避免 WASAPI 重采样增益衰减与首帧延迟"""
        pref = device.preferredFormat()
        if pref.isValid() and pref.sampleRate() > 0 and pref.channelCount() > 0:
            return pref
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setChannelConfig(QAudioFormat.ChannelConfig.ChannelConfigMono)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        return fmt

    def start_recording(self) -> bool:
        """启动麦克风采集；失败时发出 error_occurred 并返回 False"""
        if self._is_recording:
            return True

        self.stop_playback()

        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self.error_occurred.emit("未检测到可用麦克风设备，请连接或启用麦克风后重试。")
            return False

        fmt = self._select_audio_format(device)
        self._active_format = fmt
        self._buffer = QBuffer(self)
        if not self._buffer.open(QIODevice.OpenModeFlag.WriteOnly | QIODevice.OpenModeFlag.Truncate):
            self._cleanup_capture()
            self.error_occurred.emit("无法初始化录音缓冲区，请重试。")
            return False

        self._audio_source = QAudioSource(device, fmt, self)
        self._audio_source.setVolume(1.0)
        self._audio_source.stateChanged.connect(self._on_source_state_changed)
        self._audio_source.start(self._buffer)

        err = self._audio_source.error()
        if not self._is_nonfatal_error(err):
            err_msg = self._describe_audio_error(err)
            self._cleanup_capture()
            self.error_occurred.emit(err_msg)
            return False

        self._is_recording = True
        self.recording_started.emit()
        return True

    def stop_recording(self):
        """停止录音并执行轻量有效性判定与音量归一化落盘"""
        if not self._is_recording:
            return

        self._is_recording = False
        raw_bytes = b""
        fmt = self._active_format
        err = QAudio.Error.NoError

        if self._audio_source is not None:
            try:
                self._audio_source.stateChanged.disconnect(self._on_source_state_changed)
            except Exception:
                pass
            err = self._audio_source.error()
            self._audio_source.stop()
        if self._buffer is not None:
            raw_bytes = bytes(self._buffer.data())

        self._cleanup_capture()

        if not self._is_nonfatal_error(err):
            self.error_occurred.emit(self._describe_audio_error(err))
            return

        if fmt is None:
            self.recording_rejected.emit("录音格式异常，请重新录制")
            return

        samples = pcm_bytes_to_mono_float32(raw_bytes, fmt.sampleFormat(), fmt.channelCount())
        sample_rate = fmt.sampleRate()
        ok, duration_sec, _, _, reason = evaluate_recording_pcm(samples, sample_rate)
        if not ok:
            self.recording_rejected.emit(reason)
            return

        # 对有效语音进行安全峰值增益归一化，确保回放音量清晰可闻
        norm_samples = normalize_audio_for_playback(samples)

        # 写入新 WAV 并安全清理旧录音
        self._seq_counter += 1
        out_path = str(self._temp_dir / f"rec_{int(time.time() * 1000)}_{self._seq_counter}.wav")
        try:
            sf.write(out_path, norm_samples, sample_rate, subtype="PCM_16")
        except Exception as exc:
            self.error_occurred.emit(f"保存录音文件失败：{exc}")
            return

        old_path = self._latest_wav_path
        self._latest_wav_path = out_path
        if old_path and old_path != out_path:
            self._safe_delete_file(old_path)

        self.recording_accepted.emit(out_path, duration_sec)

    def abort_recording(self):
        """中断并丢弃当前录音（不触发 accepted/rejected）"""
        self._is_recording = False
        if self._audio_source is not None:
            try:
                self._audio_source.stateChanged.disconnect(self._on_source_state_changed)
            except Exception:
                pass
            self._audio_source.stop()
        self._cleanup_capture()

    def _cleanup_capture(self):
        if self._audio_source is not None:
            self._audio_source.deleteLater()
            self._audio_source = None
        if self._buffer is not None:
            if self._buffer.isOpen():
                self._buffer.close()
            self._buffer.deleteLater()
            self._buffer = None
        self._active_format = None

    def _on_source_state_changed(self, state: QAudio.State):
        if not self._is_recording or self._audio_source is None:
            return
        if self._enum_value(state) == self._enum_value(QAudio.State.StoppedState):
            err = self._audio_source.error()
            if not self._is_nonfatal_error(err):
                self._is_recording = False
                self._cleanup_capture()
                self.error_occurred.emit(self._describe_audio_error(err))

    @staticmethod
    def _enum_value(val) -> int:
        return _enum_val(val)

    @classmethod
    def _is_nonfatal_error(cls, err) -> bool:
        """兼容 PySide6 6.11 中 QtAudio.Error 与 QAudio.Error 跨命名空间枚举比较"""
        code = cls._enum_value(err)
        return code in (
            cls._enum_value(QAudio.Error.NoError),
            cls._enum_value(QAudio.Error.UnderrunError),
        )

    @classmethod
    def _describe_audio_error(cls, err) -> str:
        mapping = {
            cls._enum_value(QAudio.Error.OpenError): "麦克风打开失败，可能被其他应用占用或缺少系统录音权限。",
            cls._enum_value(QAudio.Error.IOError): "麦克风音频数据读取失败，请检查设备连接。",
            cls._enum_value(QAudio.Error.FatalError): "麦克风发生严重硬件/驱动异常，请重新插拔后重试。",
        }
        return mapping.get(cls._enum_value(err), "麦克风录音异常，请检查音频输入设备后重试。")

    # ────────────────────────── 回放与文件清理 ──────────────────────────

    def play_latest(self) -> bool:
        """播放最近一次有效录音；若无可用录音返回 False"""
        if self._is_recording or not self.has_latest_recording():
            return False

        if self.is_playing_back:
            self.stop_playback()
            return False

        self._playback_player.setSource(QUrl.fromLocalFile(self._latest_wav_path))
        self._playback_player.play()
        return True

    def stop_playback(self):
        """停止回放并释放 Windows 文件句柄"""
        if _enum_val(self._playback_player.playbackState()) != _enum_val(
            QMediaPlayer.PlaybackState.StoppedState
        ):
            self._playback_player.stop()
        self._playback_player.setSource(QUrl())

    def clear_latest(self):
        """停止回放并删除最新临时录音文件"""
        self.stop_playback()
        old_path = self._latest_wav_path
        self._latest_wav_path = None
        if old_path:
            self._safe_delete_file(old_path)

    def _safe_delete_file(self, file_path: str):
        current_src = self._playback_player.source().toLocalFile()
        if current_src and os.path.normcase(current_src) == os.path.normcase(file_path):
            self._playback_player.stop()
            self._playback_player.setSource(QUrl())
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState):
        self.playback_state_changed.emit(
            _enum_val(state) == _enum_val(QMediaPlayer.PlaybackState.PlayingState)
        )
