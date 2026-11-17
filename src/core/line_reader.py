"""
逐行跟读管理器：负责文本多行切分、无限乱序循环调度与音频缓存
"""
import random
import re
from typing import List, Optional, Tuple, Dict
from src.engines.models import SynthResult


class LineReaderManager:
    """管理逐行跟读逻辑、无限乱序循环与单句缓存"""

    def __init__(self):
        self._lines: List[str] = []
        self._current_index: int = 0
        self._cache: Dict[int, SynthResult] = {}

        # 无限乱序循环轮次状态
        self._round_number: int = 0
        self._round_order: List[int] = []
        self._round_cursor: int = 0
        self._next_round_order: List[int] = []

    @staticmethod
    def _is_pronounceable(text: str) -> bool:
        """检查文本是否包含至少一个有效可发音字符（字母、数字、中文、日文假名等）"""
        return any(
            c.isalnum()
            or '\u4e00' <= c <= '\u9fff'
            or '\u3040' <= c <= '\u309f'
            or '\u30a0' <= c <= '\u30ff'
            or '\uac00' <= c <= '\ud7af'
            for c in text
        )

    @staticmethod
    def split_sentences(raw_text: str) -> List[str]:
        """
        按换行及中日英标点智能切分句子
        优先按换行分段，段内若包含日文标点（。！？）或英文分句标点（[.!?]）则进一步切分
        自动忽略仅含纯标点符号的无效句段
        """
        if not raw_text:
            return []

        result = []
        raw_lines = raw_text.splitlines()
        for raw_line in raw_lines:
            line = raw_line.strip()
            if not line:
                continue

            # 若含有日文全角句末标点（。！？）
            if any(p in line for p in ("。", "！", "？")):
                sub_sentences = re.split(r'(?<=[。！？])', line)
                for s in sub_sentences:
                    s_clean = s.strip()
                    if s_clean and LineReaderManager._is_pronounceable(s_clean):
                        result.append(s_clean)
            # 若含有英文句末标点紧跟空格（如 ". ", "! ", "? "）
            elif re.search(r'[.!?]\s+', line):
                sub_sentences = re.split(r'(?<=[.!?])\s+', line)
                for s in sub_sentences:
                    s_clean = s.strip()
                    if s_clean and LineReaderManager._is_pronounceable(s_clean):
                        result.append(s_clean)
            else:
                if LineReaderManager._is_pronounceable(line):
                    result.append(line)
        return result

    @staticmethod
    def _build_shuffled_order(count: int, avoid_first: Optional[int] = None) -> List[int]:
        """生成 [0, count-1] 的乱序索引列表；当 count>=2 时尽量避免首句与上轮末句重复"""
        if count <= 0:
            return []
        order = list(range(count))
        random.shuffle(order)
        if count >= 2 and avoid_first is not None and order[0] == avoid_first:
            swap_idx = random.randint(1, count - 1)
            order[0], order[swap_idx] = order[swap_idx], order[0]
        return order

    def set_text(self, raw_text: str) -> int:
        """
        接收原始输入文本，按换行与句子标点智能切分，自动过滤空行，并初始化首轮乱序队列
        返回有效行数
        """
        self._cache.clear()
        self._lines = self.split_sentences(raw_text)
        total = len(self._lines)
        if total == 0:
            self._current_index = 0
            self._round_number = 0
            self._round_order = []
            self._round_cursor = 0
            self._next_round_order = []
            return 0

        self._round_number = 1
        self._round_order = self._build_shuffled_order(total)
        self._round_cursor = 0
        self._current_index = self._round_order[0]
        self._next_round_order = self._build_shuffled_order(total, avoid_first=self._round_order[-1])
        return total

    @property
    def total_lines(self) -> int:
        return len(self._lines)

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def round_number(self) -> int:
        return self._round_number

    def get_line(self, index: int) -> Optional[str]:
        if 0 <= index < len(self._lines):
            return self._lines[index]
        return None

    def get_current_line(self) -> Optional[str]:
        return self.get_line(self._current_index)

    def get_progress(self) -> Tuple[int, int]:
        """返回 (本轮当前位置[1-based], 总行数)"""
        if not self._lines:
            return 0, 0
        return self._round_cursor + 1, len(self._lines)

    def get_round_progress(self) -> Tuple[int, int, int]:
        """返回 (本轮当前位置[1-based], 总行数, 当前轮次)"""
        if not self._lines:
            return 0, 0, 0
        return self._round_cursor + 1, len(self._lines), self._round_number

    def peek_next_index(self) -> Optional[int]:
        """预查下一句将要随机进入的索引（支持跨轮无缝预加载）"""
        if not self._lines:
            return None
        if self._round_cursor + 1 < len(self._round_order):
            return self._round_order[self._round_cursor + 1]
        if self._next_round_order:
            return self._next_round_order[0]
        return 0

    def advance_random_next(self) -> Optional[str]:
        """
        进入无限乱序循环的下一句：
        本轮未遍历完则顺序取洗牌队列下一项；
        本轮结束后自动开启下一轮并切换预先洗好的新乱序队列。
        """
        total = len(self._lines)
        if total == 0:
            return None

        if self._round_cursor + 1 < len(self._round_order):
            self._round_cursor += 1
            self._current_index = self._round_order[self._round_cursor]
        else:
            self._round_number += 1
            self._round_order = self._next_round_order or self._build_shuffled_order(
                total, avoid_first=self._current_index
            )
            self._round_cursor = 0
            self._current_index = self._round_order[0]
            self._next_round_order = self._build_shuffled_order(
                total, avoid_first=self._round_order[-1]
            )
        return self.get_current_line()

    def seek_line(self, index: int) -> Optional[str]:
        """跳转到指定行"""
        if 0 <= index < len(self._lines):
            self._current_index = index
            return self.get_current_line()
        return None

    def set_cache(self, index: int, result: SynthResult):
        """写入单行合成缓存"""
        self._cache[index] = result

    def get_cache(self, index: int) -> Optional[SynthResult]:
        """获取单行合成缓存"""
        return self._cache.get(index)

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()

    def reset(self):
        """完全重置"""
        self._lines.clear()
        self._current_index = 0
        self._round_number = 0
        self._round_order.clear()
        self._round_cursor = 0
        self._next_round_order.clear()
        self._cache.clear()
