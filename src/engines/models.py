"""
TTS 数据模型定义 (VoiceInfo, SynthResult)
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class VoiceInfo:
    voice_id: str       # 引擎内部 ID，如 "en-US-AriaNeural"
    display_name: str   # 用户友好显示名，如 "Aria (US Female)"
    language: str       # "en-US", "en-GB", "ja-JP" 等
    gender: str         # "Female", "Male"
    tag: str = ""       # 推荐标签，如 "首选推荐", "自然口语"
    accent_desc: str = "" # 口音风格描述，如 "美式英语 · 女声"


@dataclass
class SynthResult:
    audio_path: str         # 生成的临时 WAV/MP3 文件路径
    sample_rate: int        # 采样率
    duration_sec: float     # 时长（秒）
    engine_name: str        # 引擎名称
