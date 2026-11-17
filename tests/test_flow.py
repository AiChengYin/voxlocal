"""
验证沉浸跟读台听说读写全闭环、无限乱序循环、录音校验与配置持久化 (覆盖 AC-01 ~ AC-12)
"""
import os
import sys
from unittest.mock import patch

import numpy as np

# 设置 UTF-8 输出与离屏渲染
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtMultimedia import QAudio, QAudioDevice, QAudioFormat
from PySide6.QtWidgets import QApplication, QMessageBox

from src.core.audio_recorder import (
    AudioRecorder,
    evaluate_recording_pcm,
    normalize_audio_for_playback,
    pcm_bytes_to_mono_float32,
)
from src.core.line_reader import LineReaderManager
from src.core.loop_player import LoopPlayer
from src.ui.focus_read_panel import BLIND_PLACEHOLDER, FocusReadPanel, StudyStage
from src.ui.main_window import MainWindow


def test_line_reader_random_infinite_loop():
    print("=== 1. 测试 LineReaderManager 无限乱序循环 (AC-02, AC-12) ===")
    mgr = LineReaderManager()
    text = """
    The quick brown fox jumps over the lazy dog.

    Practice makes perfect!

    Keep pushing forward.
    """
    count = mgr.set_text(text)
    assert count == 3
    assert mgr.round_number == 1

    # 验证第1轮遍历全量3句无重复，且 peek_next_index 与实际推进一致（含跨轮）
    round1_indices = [mgr.current_index]
    for _ in range(2):
        expected_next = mgr.peek_next_index()
        mgr.advance_random_next()
        assert mgr.current_index == expected_next
        round1_indices.append(mgr.current_index)

    assert sorted(round1_indices) == [0, 1, 2], f"第1轮应遍历全部3句: {round1_indices}"
    round1_last = round1_indices[-1]

    # 跨入第2轮：peek_next_index 必须提前预知第2轮首句且不与第1轮末句重复
    cross_peek = mgr.peek_next_index()
    assert cross_peek is not None and cross_peek != round1_last
    mgr.advance_random_next()
    assert mgr.round_number == 2
    assert mgr.current_index == cross_peek

    round2_indices = [mgr.current_index]
    for _ in range(2):
        mgr.advance_random_next()
        round2_indices.append(mgr.current_index)
    assert sorted(round2_indices) == [0, 1, 2]

    # 单句无限循环测试 (AC-12)
    assert mgr.set_text("Single sentence only.") == 1
    assert mgr.current_index == 0
    assert mgr.peek_next_index() == 0
    mgr.advance_random_next()
    assert mgr.round_number == 2
    assert mgr.current_index == 0
    print("  [PASS] 乱序洗牌、跨轮防连号、peek_next_index 及单句无限循环通过")


def test_audio_validation_and_recorder():
    print("=== 2. 测试录音有效性判定与硬件异常拦截 (AC-04, AC-08, AC-09) ===")
    sr = 16000

    # 2.1 时长不足 1.0 秒 (0.5 秒有声音频) -> 拒绝
    t_short = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    short_wave = (0.3 * np.sin(2 * np.pi * 440 * t_short)).astype(np.float32)
    ok, dur, _, _, reason = evaluate_recording_pcm(short_wave, sr)
    assert ok is False and dur < 1.0 and "1.0" in reason

    # 2.2 时长 >= 1.0 秒但纯静音/底噪 -> 拒绝
    silent_wave = np.zeros(int(sr * 1.2), dtype=np.float32)
    ok, dur, rms, peak, reason = evaluate_recording_pcm(silent_wave, sr)
    assert ok is False and dur >= 1.0 and rms < 0.0012 and peak < 0.006 and "未检测到有效" in reason

    # 2.3 时长 >= 1.0 秒且有有效轻声朗读 (含前后停顿的短词语音突发) -> 通过
    burst_wave = np.zeros(int(sr * 1.5), dtype=np.float32)
    t_burst = np.linspace(0, 0.3, int(sr * 0.3), endpoint=False)
    burst_wave[int(sr * 0.5) : int(sr * 0.8)] = (0.005 * np.sin(2 * np.pi * 440 * t_burst)).astype(np.float32)
    ok, dur, rms, peak, reason = evaluate_recording_pcm(burst_wave, sr)
    assert ok is True and dur >= 1.0 and reason == ""

    # 2.4 双声道 Int16 混音解码、非对齐尾字节防崩与回放峰值归一化验证
    stereo = np.array([16384, -16384, 8192, 8192, -8192, -8192], dtype=np.int16)
    unaligned_bytes = stereo.tobytes() + b"\x99"  # 故意附加1个残缺字节
    mono = pcm_bytes_to_mono_float32(unaligned_bytes, QAudioFormat.SampleFormat.Int16, 2)
    assert len(mono) == 3

    quiet_voice = np.array([0.0, 0.03, -0.03, 0.015], dtype=np.float32)
    boosted = normalize_audio_for_playback(quiet_voice, target_peak=0.85)
    assert abs(float(np.max(np.abs(boosted))) - 0.85) < 1e-3

    # 2.5 PySide6 跨命名空间枚举值判断与无麦克风设备异常阻断测试 (AC-09)
    assert AudioRecorder._is_nonfatal_error(QAudio.Error.NoError) is True
    assert AudioRecorder._is_nonfatal_error(QAudio.Error.UnderrunError) is True
    assert AudioRecorder._is_nonfatal_error(QAudio.Error.OpenError) is False
    assert "占用" in AudioRecorder._describe_audio_error(QAudio.Error.OpenError)

    rec = AudioRecorder()
    errors = []
    rec.error_occurred.connect(errors.append)
    with patch("src.core.audio_recorder.QMediaDevices.defaultAudioInput", return_value=QAudioDevice()):
        started = rec.start_recording()
    assert started is False
    assert len(errors) == 1 and "未检测到可用麦克风" in errors[0]

    # 2.6 旧录音清理与新录音保留（模拟最新录音文件生命周期）
    f1 = str(rec._temp_dir / "test_old_rec.wav")
    f2 = str(rec._temp_dir / "test_new_rec.wav")
    with open(f1, "wb") as fp:
        fp.write(b"RIFF")
    with open(f2, "wb") as fp:
        fp.write(b"RIFF")
    rec._latest_wav_path = f1
    rec._safe_delete_file(f1)
    assert not os.path.exists(f1)
    rec._latest_wav_path = f2
    rec.clear_latest()
    assert not os.path.exists(f2)
    # 2.7 LoopPlayer 暂停态下 EndOfMedia 与 gap_step 竞态防护验证
    lp = LoopPlayer()
    lp._audio_path = "dummy.wav"
    lp.pause()
    assert lp.is_active() is False
    from PySide6.QtMultimedia import QMediaPlayer
    lp._on_media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)
    assert not lp._gap_timer.isActive(), "暂停状态下收到 EndOfMedia 不得启动倒计时定时器"
    lp._on_gap_step()
    assert lp.is_active() is False
    print("  [PASS] 时长/静音阈值校验、滑动窗口语音检测、AGC归一化、无麦阻断与暂停竞态防护通过")


def test_focus_panel_state_machine():
    print("=== 3. 测试 FocusReadPanel 四阶段状态机与全部交互约束 (AC-01~AC-11) ===")
    panel = FocusReadPanel()
    panel.show()

    # AC-02: 不存在上一个 / 下一个按钮
    assert not hasattr(panel, "btn_prev")
    assert not hasattr(panel, "btn_next")

    # AC-03: 目标朗读次数范围 3~10，默认 3
    assert panel.target_spin.minimum() == 3
    assert panel.target_spin.maximum() == 10
    assert panel.target_spin.value() == 3

    # AC-01 & AC-04: 进入句子默认盲听隐藏，立即显示录音 (0/3)，无回放与写按钮
    sentence = "Practice makes perfect!"
    panel.set_line_content(sentence, 1, 3, 1)
    assert panel.stage == StudyStage.S1_LISTEN_SPEAK
    assert panel.is_text_revealed is False
    assert panel.sentence_label.text() == BLIND_PLACEHOLDER
    assert not panel.btn_record.isHidden()
    assert "(0/3)" in panel.btn_record.text()
    assert panel.btn_replay_rec.isHidden()
    assert panel.btn_write.isHidden()

    # AC-01: 手动切换展示/隐藏原文
    panel.toggle_text_visibility()
    assert panel.is_text_revealed is True
    assert panel.sentence_label.text() == sentence
    panel.toggle_text_visibility()
    assert panel.is_text_revealed is False
    assert panel.sentence_label.text() == BLIND_PLACEHOLDER

    # AC-08: 录音中锁定与失败不计数
    panel.set_recording_active(True)
    assert panel.stage == StudyStage.RECORDING
    assert not panel.btn_play_pause.isEnabled()
    assert not panel.target_spin.isEnabled()
    panel.on_recording_failed("录音时长不足 1.0 秒")
    assert panel.stage == StudyStage.S1_LISTEN_SPEAK
    assert panel.completed_rec_count == 0
    assert panel.btn_play_pause.isEnabled()
    # 验证 4.5 秒提示锁定期间不被循环/留白刷新覆盖
    panel.show_gap_countdown(0.8)
    assert "录音时长不足" in panel.playback_status_lbl.text()

    # AC-04 & AC-05: 有效录音 3 次 -> 第1次出现回放，第3次录音按钮消失且【写】按钮出现
    panel.increment_recording_count()
    assert panel.completed_rec_count == 1
    assert not panel.btn_replay_rec.isHidden()
    assert panel.btn_write.isHidden()

    panel.increment_recording_count()
    panel.increment_recording_count()
    assert panel.completed_rec_count == 3
    assert panel.stage == StudyStage.S2_READY_TO_WRITE
    assert panel.btn_record.isHidden()
    assert not panel.btn_write.isHidden()

    # AC-11: S2 下将目标次数调高到 5 -> 立即回退 S1 (3/5)
    panel.set_target_read_count(5, emit_signal=False)
    assert panel.stage == StudyStage.S1_LISTEN_SPEAK
    assert not panel.btn_record.isHidden()
    assert "(3/5)" in panel.btn_record.text()
    assert panel.btn_write.isHidden()

    # AC-11: S1 下将目标次数调低回 3 -> 立即晋升 S2
    panel.set_target_read_count(3, emit_signal=False)
    assert panel.stage == StudyStage.S2_READY_TO_WRITE
    assert panel.btn_record.isHidden()
    assert not panel.btn_write.isHidden()

    # AC-06 & AC-10: 先展开原文，再点击【写】-> 强制隐藏原文、禁用播放与回放、空输入禁止提交
    panel.toggle_text_visibility()
    assert panel.is_text_revealed is True
    write_entered = []
    panel.write_mode_entered.connect(lambda: write_entered.append(True))
    panel.enter_writing_stage()
    assert len(write_entered) == 1
    assert panel.stage == StudyStage.S3_WRITING
    assert panel.is_text_revealed is False
    assert panel.sentence_label.text() == BLIND_PLACEHOLDER
    assert not panel.btn_toggle_text.isEnabled()
    assert not panel.btn_play_pause.isEnabled()
    assert not panel.btn_replay.isEnabled()
    assert not panel.btn_replay_rec.isEnabled()
    assert not panel.write_panel.isHidden()
    assert not panel.btn_submit_write.isEnabled()

    # 纯空格不可提交 (AC-10)
    panel.write_input.setPlainText("   \n\t ")
    assert not panel.btn_submit_write.isEnabled()
    panel.submit_writing()
    assert panel.stage == StudyStage.S3_WRITING

    # AC-11: S3 写作中途调高目标次数到 4 -> 立即退出写作区并回退 S1 (3/4)
    resumed_signals = []
    panel.recording_stage_resumed.connect(lambda: resumed_signals.append(True))
    panel.set_target_read_count(4, emit_signal=False)
    assert len(resumed_signals) == 1
    assert panel.stage == StudyStage.S1_LISTEN_SPEAK
    assert panel.write_panel.isHidden()
    assert panel.btn_play_pause.isEnabled()
    assert panel.btn_toggle_text.isEnabled()
    assert "(3/4)" in panel.btn_record.text()

    # 降回 3 再次进入写 -> 提交 -> 对照 -> 重新输入 -> 再提交 -> 确认 OK (AC-06, AC-07)
    panel.set_target_read_count(3, emit_signal=False)
    panel.enter_writing_stage()
    panel.write_input.setPlainText("Practice makes perfct")
    assert panel.btn_submit_write.isEnabled()
    panel.submit_writing()
    assert panel.stage == StudyStage.S4_REVIEWING
    assert not panel.review_panel.isHidden()
    assert "Practice" in panel.review_orig_lbl.text()

    # 重新输入：清空输入框且原文仍保持隐藏
    panel.retry_writing()
    assert panel.stage == StudyStage.S3_WRITING
    assert panel.write_input.toPlainText() == ""
    assert panel.is_text_revealed is False

    # 再次输入并提交后确认 OK
    ok_signals = []
    panel.sentence_completed_ok.connect(lambda: ok_signals.append(True))
    panel.write_input.setPlainText("Practice makes perfect!")
    panel.submit_writing()
    panel.confirm_writing_ok()
    assert len(ok_signals) == 1
    panel.close()
    print("  [PASS] FocusReadPanel 四阶段流转、防作弊锁、空拦截、动态调参及自检确认全部通过")


def test_main_window_integration_and_persistence():
    print("=== 4. 测试 MainWindow 集成、配置持久化与乱序切句 (AC-03, AC-07) ===")
    w = MainWindow()
    orig_saved_target = w._db.get_setting("target_read_count", "3")
    try:
        assert w.tabs.count() == 2
        assert "课文文本库" in w.tabs.tabText(0)
        assert "沉浸跟读台" in w.tabs.tabText(1)

        # AC-03: 修改目标次数并持久化，重启新窗口后仍生效
        w.focus_read_panel.target_spin.setValue(6)
        assert w._db.get_setting("target_read_count") == "6"
        w.close()

        w2 = MainWindow()
        assert w2.focus_read_panel.target_spin.value() == 6

        # 模拟开始练习 -> 乱序进入某句 -> 完成 OK 直通下一句
        text = "Sentence Alpha.\nSentence Beta.\nSentence Gamma."
        w2.text_input.set_text(text)
        with patch.object(w2, "_play_line", wraps=w2._play_line):
            # 拦截 SynthWorker 避免离屏测试触发真实网络请求
            with patch("src.ui.main_window.SynthWorker.start", return_value=None):
                w2._start_reading()
                assert w2.tabs.currentIndex() == 1
                first_idx = w2._line_mgr.current_index
                assert first_idx in (0, 1, 2)
                assert w2.focus_read_panel.is_text_revealed is False
                assert w2.focus_read_panel.sentence_label.text() == BLIND_PLACEHOLDER

                expected_second = w2._line_mgr.peek_next_index()
                # 验证录音与写作状态下 TTS 暂停/恢复及 _on_line_ready 防打断保护
                with patch.object(w2._player, "is_active", return_value=True), \
                        patch.object(w2._player, "pause") as mock_pause, \
                        patch.object(w2._player, "resume") as mock_resume, \
                        patch.object(w2._player, "load_and_play") as mock_load_play:
                    with patch.object(w2._recorder, "start_recording", return_value=True):
                        w2._on_record_start_requested()
                        w2.focus_read_panel.set_recording_active(True)
                    mock_pause.assert_called()

                    # 拒绝录音不计次但恢复播放
                    w2._on_recording_rejected("时长不足")
                    assert w2.focus_read_panel.completed_rec_count == 0
                    mock_resume.assert_called()

                    # 当前配置目标为 6 次，录 3 次后仍处于 S1，补满 6 次后进入 S2
                    for _ in range(3):
                        w2._resume_tts_after_rec = True
                        w2._on_recording_accepted("dummy.wav", 1.5)
                    assert w2.focus_read_panel.stage == StudyStage.S1_LISTEN_SPEAK

                    for _ in range(3):
                        w2._on_recording_accepted("dummy.wav", 1.5)
                    assert w2.focus_read_panel.stage == StudyStage.S2_READY_TO_WRITE

                    # 进入写作态后，迟到的 _on_line_ready 不得触发 load_and_play
                    w2.focus_read_panel.enter_writing_stage()
                    assert w2.focus_read_panel.stage == StudyStage.S3_WRITING
                    from src.engines.models import SynthResult
                    w2._on_line_ready(first_idx, SynthResult(audio_path="a.wav", duration_sec=1.0, sample_rate=24000, engine_name="Edge-TTS"))
                    mock_load_play.assert_not_called()

                w2._on_sentence_completed_ok()
                assert w2._line_mgr.current_index == expected_second
                assert w2.focus_read_panel.completed_rec_count == 0
                assert w2.focus_read_panel.stage == StudyStage.S1_LISTEN_SPEAK

                # 直接点击顶部 Tab 0 切换时也必须安全停止录音与播放
                w2.tabs.setCurrentIndex(0)
                assert w2.tabs.currentIndex() == 0
                assert w2._player.is_active() is False
        w2.close()
    finally:
        # 恢复测试前数据库配置，不污染本地环境
        w_restore = MainWindow()
        w_restore._db.set_setting("target_read_count", orig_saved_target)
        w_restore.close()
    print("  [PASS] MainWindow 集成、DB 持久化与乱序直通下一句测试通过")


if __name__ == "__main__":
    app = QApplication([])
    # 防止离屏测试中弹窗阻塞
    with patch.object(QMessageBox, "critical"), patch.object(QMessageBox, "warning"):
        test_line_reader_random_infinite_loop()
        test_audio_validation_and_recorder()
        test_focus_panel_state_machine()
        test_main_window_integration_and_persistence()
    app.quit()
    print("\n>>> ALL ACCEPTANCE TESTS PASSED SUCCESSFULLY! <<<")
    sys.exit(0)
