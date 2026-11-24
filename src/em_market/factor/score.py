"""スコアの有効性と、ポートフォリオとの整合性を測る指標を計算する。

- IC: 各基準日に使うスコアと、当日のリターンの相関
- TC: アクティブウェイト (ファンド − BM) と、各基準日に使うスコアの相関。
  アクティブウェイトが 0 の銘柄は除く
- リバランス相関: リバランス日のスコアと、それ以降の各日のスコアの相関

相関はいずれも Pearson で、どちらかが欠損の銘柄は除く。
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd

SCORE_COLUMNS: list[str] = ["ai", "ai70_bd30", "bd"]
MIN_NAMES: int = 3  # 相関を計算する最小銘柄数


def _scores_by_date(scores: pd.DataFrame) -> dict[int, pd.DataFrame]:
    return {
        int(ymd): day.drop_duplicates("bid").set_index("bid")
        for ymd, day in scores.groupby("score_ymd")
    }


def _corr(values: pd.Series, scores: pd.DataFrame, column: str) -> float:
    if column not in scores.columns:
        return np.nan
    return values.corr(scores[column].reindex(values.index), min_periods=MIN_NAMES)


def _to_frame(
    rows: dict[int, dict[str, float]], columns: Sequence[str]
) -> pd.DataFrame:
    result = pd.DataFrame.from_dict(rows, orient="index", columns=list(columns))
    result = result.sort_index()
    result.index.name = "date"
    return result


def calc_ic(
    scores: pd.DataFrame,
    returns: pd.DataFrame,
    score_dates: pd.Series,
    columns: Sequence[str] = SCORE_COLUMNS,
) -> pd.DataFrame:
    """スコアの種類ごとに、日次の IC を返す (index は基準日)。

    scores: bid, score_ymd と各スコアの列を持つ縦持ちのスコア。
    returns: ymd, bid, rtn を持つ日次リターン。
    score_dates: 基準日 → 使用するスコア日。NAM のファクターリターンと同じものを渡す。
    """
    by_date = _scores_by_date(scores)
    rows: dict[int, dict[str, float]] = {}
    for ymd, day in returns[returns["ymd"].isin(score_dates.index)].groupby("ymd"):
        day_scores = by_date.get(int(score_dates[ymd]))
        if day_scores is None:
            continue
        day_returns = day.drop_duplicates("bid").set_index("bid")["rtn"]
        rows[int(ymd)] = {c: _corr(day_returns, day_scores, c) for c in columns}
    return _to_frame(rows, columns)


def calc_tc(
    scores: pd.DataFrame,
    score_dates: pd.Series,
    port_weights: pd.DataFrame,
    bm_weights: pd.DataFrame,
    columns: Sequence[str] = SCORE_COLUMNS,
) -> pd.DataFrame:
    """スコアの種類ごとに、日次の TC を返す (index は基準日)。

    port_weights, bm_weights: ymd, bid, weight を持つ日次のウェイト (各日の合計が 1)。
    ファンドと BM の両方のウェイトがある基準日だけを計算する。
    """
    by_date = _scores_by_date(scores)
    port = {
        int(ymd): day.set_index("bid")["weight"]
        for ymd, day in port_weights.groupby("ymd")
    }
    bm = {
        int(ymd): day.set_index("bid")["weight"]
        for ymd, day in bm_weights.groupby("ymd")
    }

    rows: dict[int, dict[str, float]] = {}
    for ymd, score_ymd in score_dates.items():
        ymd = int(ymd)
        day_scores = by_date.get(int(score_ymd))
        if day_scores is None or ymd not in port or ymd not in bm:
            continue
        active = port[ymd].sub(bm[ymd], fill_value=0.0)
        active = active[active != 0]
        rows[ymd] = {c: _corr(active, day_scores, c) for c in columns}
    return _to_frame(rows, columns)


def calc_rebalance_corr(
    scores: pd.DataFrame,
    reb_ymd: int,
    columns: Sequence[str] = SCORE_COLUMNS,
) -> pd.DataFrame:
    """スコアの種類ごとに、リバランス日のスコアと各スコア日のスコアの相関を返す。

    scores: 日次のスコア (score_ymd がスコア日)。reb_ymd 以降で最初のスコア日を
    リバランス日とし、結果の先頭の行 (相関 1) がその日になる。
    """
    by_date = _scores_by_date(scores)
    dates = sorted(ymd for ymd in by_date if ymd >= reb_ymd)
    if not dates:
        raise ValueError(f"リバランス日以降のスコアがありません: {reb_ymd}")

    base = by_date[dates[0]]
    rows: dict[int, dict[str, float]] = {}
    for ymd in dates:
        day_scores = by_date[ymd]
        rows[ymd] = {
            c: _corr(base[c], day_scores, c) if c in base.columns else np.nan
            for c in columns
        }
    return _to_frame(rows, columns)
