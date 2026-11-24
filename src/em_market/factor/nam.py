"""スコアと日次リターンから NAM ファクターのファクターリターンを算出する。

各基準日について、対応するスコア日のスコアを使い、以下の銘柄の等ウェイトリターンを
ファクターリターンとする。

- ai, ai70_bd30, bd, rvl, tvl: Region ごとの 5 分位の最上位 (Q5)
- rri: スコアが 1 または 2 の銘柄

Region に対応付けられない銘柄はポートフォリオに含めず、市場平均の計算にのみ含める。
"""

from typing import Literal

import pandas as pd

from em_market.const import COUNTRY_INFO

QUANTILE_FACTORS: list[str] = ["ai", "ai70_bd30", "bd", "rvl", "tvl"]
FACTORS: list[str] = [*QUANTILE_FACTORS, "rri"]
N_QUANTILES: int = 5
RRI_LONG_VALUES: list[int] = [1, 2]

Breakpoints = Literal["by_date", "pooled"]


def _is_top_quantile(values: pd.Series) -> pd.Series:
    valid = values.dropna()
    if valid.empty:
        return pd.Series(False, index=values.index)

    labels = pd.qcut(valid, N_QUANTILES, labels=False, duplicates="drop")
    return (labels == N_QUANTILES - 1).reindex(values.index, fill_value=False)


def flag_long_names(
    scores: pd.DataFrame,
    score_dates: pd.Series,
    breakpoints: Breakpoints = "by_date",
) -> pd.DataFrame:
    """銘柄 × スコア日ごとに、各ファクターのポートフォリオに入るかを返す。

    breakpoints:
        by_date: 基準日ごとに、その日に使うスコアを Region 内で分位化する。
            同じスコアを使う基準日は同じ銘柄になるため、スコア日単位で計算する。
        pooled: 現行方式 (BLF.fret_nam_daily) との突合用。期間全体の営業日に展開した
            スコアを Region 内でまとめて分位化する。将来のスコアが分位点に影響するため、
            同じ日付でも計算期間によって値が変わる。
    """
    if breakpoints == "by_date":
        panel = scores
        group_keys = ["score_ymd", "region"]
    elif breakpoints == "pooled":
        n_days = scores["score_ymd"].map(score_dates.value_counts())
        panel = scores.loc[scores.index.repeat(n_days)].reset_index(drop=True)
        group_keys = ["region"]
    else:
        raise ValueError(f"breakpoints が不正です: {breakpoints!r}")

    flags = panel[["bid", "score_ymd"]].copy()
    for factor in QUANTILE_FACTORS:
        flags[factor] = (
            panel.groupby(group_keys)[factor].transform(_is_top_quantile).eq(True)
        )
    flags["rri"] = panel["rri"].isin(RRI_LONG_VALUES) & panel["region"].notna()

    return flags.drop_duplicates(["bid", "score_ymd"]).reset_index(drop=True)


def calc_nam_factor_returns(
    scores: pd.DataFrame,
    returns: pd.DataFrame,
    score_dates: pd.Series,
    *,
    breakpoints: Breakpoints = "by_date",
    excess: bool = True,
) -> pd.DataFrame:
    """NAM ファクターの日次リターン (%) を返す。入力は変更しない。

    scores: bid, score_ymd と各ファクターの列を持つ縦持ちのスコア。
    returns: ymd, bid, rtn を持つ日次リターン。
    score_dates: 基準日を index、使用するスコア日を値とする Series。計算対象の日を決める。

    excess=True の場合は、ユニバースの等ウェイト平均を控除する。ユニバースは
    by_date ではその日に使うスコアの銘柄、pooled では現行方式と同じく
    計算期間のいずれかのスコアに含まれる銘柄とする。
    """
    regions = {country: info["region"] for country, info in COUNTRY_INFO.items()}
    scores = scores[scores["score_ymd"].isin(score_dates)]
    scores = scores.assign(region=scores["bid"].str[:3].map(regions))
    flags = flag_long_names(scores, score_dates, breakpoints)

    returns = returns[returns["ymd"].isin(score_dates.index)]
    returns = returns.assign(score_ymd=returns["ymd"].map(score_dates))
    if breakpoints == "pooled":
        returns = returns[returns["bid"].isin(scores["bid"])]
    else:
        returns = returns.merge(scores[["bid", "score_ymd"]], on=["bid", "score_ymd"])

    if excess:
        market = returns.groupby("ymd")["rtn"].transform("mean")
        returns = returns.assign(rtn=returns["rtn"] - market)

    panel = returns.merge(flags, on=["bid", "score_ymd"], how="inner")

    result = pd.DataFrame(
        {
            factor: panel.loc[panel[factor]].groupby("ymd")["rtn"].mean()
            for factor in FACTORS
        },
        index=pd.Index(sorted(panel["ymd"].unique()), name="date"),
    )
    return result
