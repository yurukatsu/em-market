"""日付に関する共通の定義。"""

from typing import Literal

import pandas as pd

ScoreFreq = Literal["monthly", "daily"]


def weekly_period(
    base_date: str | pd.Timestamp, lookback_days: int, data_lag_days: int
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """週次レポートの価格の期間 (起点, 終点) を返す。

    終点は基準日の data_lag_days 日前 (水曜実行なら前日の火曜)、起点はその
    lookback_days 日前。リターンは起点の値を基準に、起点より後から終点までで計算する。
    """
    end = pd.Timestamp(base_date).normalize() - pd.Timedelta(days=data_lag_days)
    return end - pd.Timedelta(days=lookback_days), end


def previous_ym(ymd: int) -> int:
    """基準日の前月を YYYYMM で返す。"""
    year, month = divmod(ymd // 100, 100)
    return (year - 1) * 100 + 12 if month == 1 else year * 100 + month - 1
