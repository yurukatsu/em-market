"""日付に関する共通の定義。"""

from typing import Literal

ScoreFreq = Literal["monthly", "daily"]


def previous_ym(ymd: int) -> int:
    """基準日の前月を YYYYMM で返す。"""
    year, month = divmod(ymd // 100, 100)
    return (year - 1) * 100 + 12 if month == 1 else year * 100 + month - 1
