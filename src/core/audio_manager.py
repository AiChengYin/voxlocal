"""
音频管理器：处理音频文件的保存与格式转换
"""
import os
import wave
import struct
import time
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

from src.utils.paths import get_output_dir


class AudioManager:
    SUPPORTED_FORMATS = [".wav", ".mp3"]

    def __init__(self):
        self._output_dir = get_output_dir()

    def save_wav(self, audio_data: np.ndarray, sample_rate: int,
                 custom_path: Optional[str] = None) -> str:
        """保存 numpy 音频数据为 WAV 文件，返回文件路径"""
        if custom_path:
            out_path = custom_path
        else:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            out_path = str(self._output_dir / f"voxlocal_{timestamp}.wav")

        sf.write(out_path, audio_data, sample_rate, subtype='PCM_16')
        return out_path

    def save_bytes_as_wav(self, audio_bytes: bytes, sample_rate: int = 24000,
                          custom_path: Optional[str] = None) -> str:
        """保存原始 PCM bytes 为 WAV 文件"""
        if custom_path:
            out_path = custom_path
        else:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            out_path = str(self._output_dir / f"voxlocal_{timestamp}.wav")

        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        sf.write(out_path, audio_array, sample_rate, subtype='PCM_16')
        return out_path

    def get_duration(self, file_path: str) -> float:
        """获取音频文件时长（秒）"""
        try:
            info = sf.info(file_path)
            return info.duration
        except Exception:
            return 0.0

    @staticmethod
    def generate_temp_path() -> str:
        """生成临时音频文件路径"""
        temp_dir = Path(os.environ.get("TEMP", "/tmp")) / "VoxLocal"
        temp_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time() * 1000)
        return str(temp_dir / f"temp_{timestamp}.wav")
