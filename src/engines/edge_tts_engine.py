"""
Edge-TTS 引擎（微软云端神经网络 TTS）
无需 API Key，需要联网
"""
import asyncio
import os
import tempfile
import time
from typing import List, Tuple

from src.engines.models import VoiceInfo, SynthResult
from src.core.audio_manager import AudioManager


# 经全量 API 实时验证存活的微软云端官方发音人列表（已剔除微软已下架失效的旧角色）
EDGE_TTS_VOICES = [
    # American English (en-US)
    VoiceInfo("en-US-AriaNeural",    "Aria (US Female, 默认)",      "en-US", "Female", "首选推荐", "美式英语 · 女声"),
    VoiceInfo("en-US-JennyNeural",   "Jenny (US Female, 自然)",     "en-US", "Female", "自然口语", "美式英语 · 女声"),
    VoiceInfo("en-US-GuyNeural",     "Guy (US Male, 沉稳)",         "en-US", "Male",   "播音典范", "美式英语 · 男声"),
    VoiceInfo("en-US-AvaNeural",     "Ava (US Female, 清新)",       "en-US", "Female", "清新女声", "美式英语 · 女声"),
    VoiceInfo("en-US-EmmaNeural",    "Emma (US Female, 亲切)",      "en-US", "Female", "亲切活泼", "美式英语 · 女声"),
    VoiceInfo("en-US-BrianNeural",   "Brian (US Male, 青年)",       "en-US", "Male",   "青年男声", "美式英语 · 男声"),
    VoiceInfo("en-US-AndrewNeural",  "Andrew (US Male, 温暖)",      "en-US", "Male",   "温暖男声", "美式英语 · 男声"),
    VoiceInfo("en-US-ChristopherNeural", "Christopher (US Male)",   "en-US", "Male",   "自然对话", "美式英语 · 男声"),
    VoiceInfo("en-US-EricNeural",    "Eric (US Male)",              "en-US", "Male",   "青年男声", "美式英语 · 男声"),
    VoiceInfo("en-US-MichelleNeural","Michelle (US Female)",        "en-US", "Female", "亲切温和", "美式英语 · 女声"),
    VoiceInfo("en-US-RogerNeural",   "Roger (US Male)",             "en-US", "Male",   "成熟男声", "美式英语 · 男声"),

    # British English (en-GB)
    VoiceInfo("en-GB-SoniaNeural",   "Sonia (GB Female, 知性)",     "en-GB", "Female", "知性英音", "英式英语 · 女声"),
    VoiceInfo("en-GB-RyanNeural",    "Ryan (GB Male, 纯正)",        "en-GB", "Male",   "伦敦腔调", "英式英语 · 男声"),
    VoiceInfo("en-GB-LibbyNeural",   "Libby (GB Female)",           "en-GB", "Female", "柔和英音", "英式英语 · 女声"),
    VoiceInfo("en-GB-MaisieNeural",  "Maisie (GB Female)",          "en-GB", "Female", "轻快英音", "英式英语 · 女声"),
    VoiceInfo("en-GB-ThomasNeural",  "Thomas (GB Male)",            "en-GB", "Male",   "牛津男声", "英式英语 · 男声"),

    # Australian English (en-AU)
    VoiceInfo("en-AU-NatashaNeural", "Natasha (AU Female)",         "en-AU", "Female", "澳洲口音", "澳洲英语 · 女声"),
    VoiceInfo("en-AU-WilliamMultilingualNeural", "William (AU Male)", "en-AU", "Male", "澳洲男声", "澳洲英语 · 男声"),

    # Japanese (ja-JP)
    VoiceInfo("ja-JP-NanamiNeural",  "Nanami (JA Female, 默认)",    "ja-JP", "Female", "首选推荐", "标准日语 · 女声"),
    VoiceInfo("ja-JP-KeitaNeural",   "Keita (JA Male, 阳光)",       "ja-JP", "Male",   "自然对话", "标准日语 · 男声"),
]


class EdgeTTSEngine:

    def __init__(self):
        self._audio_mgr = AudioManager()

    def get_engine_name(self) -> str:
        return "Edge-TTS"

    def get_engine_description(self) -> str:
        return "微软云端神经网络 • 需要联网 • 高质量免费"

    def requires_internet(self) -> bool:
        return True

    def get_badge(self) -> str:
        return "CLOUD"

    def is_available(self) -> Tuple[bool, str]:
        try:
            import edge_tts
            return True, "就绪（需联网）"
        except ImportError:
            return False, "缺少依赖: edge-tts（请运行 pip install edge-tts）"
        except Exception as e:
            return False, f"引擎加载异常: {e}"

    def list_voices(self) -> List[VoiceInfo]:
        return EDGE_TTS_VOICES

    def _run_async(self, coro):
        """在新事件循环中运行异步协程，确保会话与生成器安全关闭"""
        try:
            return asyncio.run(coro)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(coro)
            finally:
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                loop.close()

    async def _synthesize_async(self, text: str, voice_id: str,
                                 speed: float, out_path: str):
        import edge_tts
        # Edge-TTS 用 +/- 百分比表示语速
        rate_str = f"+{int((speed - 1) * 100)}%" if speed >= 1 else f"{int((speed - 1) * 100)}%"
        communicate = edge_tts.Communicate(text, voice_id, rate=rate_str)
        await communicate.save(out_path)

    def synthesize(self, text: str, voice_id: str,
                   speed: float = 1.0, progress_cb=None) -> SynthResult:
        clean_text = text.strip()
        # 校验文本是否含有可发音字符（防止纯标点符号导致服务端拒绝返回音频）
        if not any(
            c.isalnum()
            or '\u4e00' <= c <= '\u9fff'
            or '\u3040' <= c <= '\u309f'
            or '\u30a0' <= c <= '\u30ff'
            or '\uac00' <= c <= '\ud7af'
            for c in clean_text
        ):
            raise RuntimeError(f"输入文本缺少有效发音字符（仅含标点或空白）：{text[:50]}")

        # 校验发音人有效性：若传入已下架的旧 voice_id，自动安全降级为对应语言官方默认发音人
        valid_voice_ids = {v.voice_id for v in EDGE_TTS_VOICES}
        actual_voice = voice_id
        if actual_voice not in valid_voice_ids:
            actual_voice = "ja-JP-NanamiNeural" if actual_voice.startswith("ja") else "en-US-AriaNeural"

        if progress_cb:
            progress_cb("正在连接微软云端神经网络服务…")
        temp_path = AudioManager.generate_temp_path()
        mp3_path = temp_path.replace(".wav", ".mp3")

        try:
            self._run_async(self._synthesize_async(clean_text, actual_voice, speed, mp3_path))
        except Exception as e:
            err_str = str(e)
            # 若触发 No audio was received 且此前未用默认发音人，进行一次默认发音人自动降级重试
            default_voice = "ja-JP-NanamiNeural" if actual_voice.startswith("ja") else "en-US-AriaNeural"
            if "No audio was received" in err_str and actual_voice != default_voice:
                try:
                    if progress_cb:
                        progress_cb("正在使用默认推荐发音人重试…")
                    self._run_async(self._synthesize_async(clean_text, default_voice, speed, mp3_path))
                    actual_voice = default_voice
                    err_str = None
                except Exception as retry_e:
                    err_str = str(retry_e)

            if err_str:
                # 清理临时文件
                if os.path.exists(mp3_path):
                    try:
                        os.remove(mp3_path)
                    except Exception:
                        pass

                if "No audio was received" in err_str:
                    raise RuntimeError(
                        f"微软云端未返回音频数据 (No audio received)。\n\n"
                        f"可能原因：\n"
                        f"1. 发音人（{voice_id}）临时不可用或已被微软下架；\n"
                        f"2. 输入文本缺少可发音内容；\n"
                        f"3. 连续请求频次过高触发了服务频控。\n\n"
                        f"建议操作：请尝试在左侧切换为推荐发音人（Nanami / Aria）或稍后重试。"
                    ) from e
                elif "403" in err_str or "Invalid response status" in err_str:
                    raise RuntimeError(
                        f"微软云端语音服务拒绝了连接请求 (403 Forbidden)。\n"
                        f"可能原因：微软云端安全握手变动或当前 IP 受到频控限制。\n"
                        f"错误详情：{err_str}"
                    ) from e
                elif any(k in err_str for k in ("TimeoutError", "Cannot connect to host", "ClientConnectorError", "getaddrinfo failed", "gaierror")):
                    raise RuntimeError(
                        f"无法连接到微软云端语音服务器，网络请求超时或连接中断。\n"
                        f"请检查您的网络连接与系统代理配置。\n"
                        f"错误详情：{err_str}"
                    ) from e
                else:
                    raise RuntimeError(f"Edge-TTS 云端合成异常: {err_str}") from e

        # 用 soundfile/pydub 转换为 WAV（若 soundfile 不支持 mp3，则直接用 mp3 路径）
        wav_path = temp_path
        try:
            import pydub
            audio = pydub.AudioSegment.from_mp3(mp3_path)
            audio.export(wav_path, format="wav")
            os.remove(mp3_path)
        except Exception:
            # 没有 pydub/ffmpeg 就直接返回 mp3（QMediaPlayer 也能播放）
            wav_path = mp3_path

        # 获取时长
        try:
            import soundfile as sf
            info = sf.info(wav_path)
            duration = info.duration
        except Exception:
            duration = 0.0

        return SynthResult(
            audio_path=wav_path,
            sample_rate=24000,
            duration_sec=duration,
            engine_name=self.get_engine_name()
        )
