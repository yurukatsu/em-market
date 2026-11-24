"""ユニバース、日次リターン、月次ファクターから common ファクターのリターンを算出する。

各基準日について、当日のユニバースの銘柄で前月の月次ファクターを正規スコアに変換する。
ファクターごとに当日の USD リターンを単回帰し、その傾きをファクターリターンとする。
"""

import warnings
from collections.abc import Mapping
from functools import cache
from statistics import NormalDist

import numpy as np
import pandas as pd

from em_market.const import COMMON_FACTOR_CATEGORIES, COMMON_FACTOR_CATEGORY_MAP
from em_market.dates import previous_ym

MISSING_THRESHOLD: float = -100.0  # これ以下のファクター値は欠損として扱う
BLOM_ALPHA: float = 3 / 8


@cache
def _blom_table(n: int) -> np.ndarray:
    """順位 → 正規スコアの変換表。平均順位は 0.5 刻みなので 2 × 順位を添字にする。"""
    normal = NormalDist()
    table = np.full(2 * n + 1, np.nan)
    for i in range(2, 2 * n + 1):
        table[i] = normal.inv_cdf((i / 2 - BLOM_ALPHA) / (n + 1 - 2 * BLOM_ALPHA))
    return table


def blom_score(values: pd.DataFrame) -> pd.DataFrame:
    """列ごとに平均順位を Blom 変換した正規スコアを返す。欠損は欠損のまま。"""
    ranks = values.rank(method="average").to_numpy()
    scores = np.full_like(ranks, np.nan)
    for j in range(ranks.shape[1]):
        valid = ~np.isnan(ranks[:, j])
        n = int(valid.sum())
        if n > 0:
            index = np.rint(2 * ranks[valid, j]).astype(int)
            scores[valid, j] = _blom_table(n)[index]
    return pd.DataFrame(scores, index=values.index, columns=values.columns)


def make_exposures(factors: pd.DataFrame, universe: pd.Index) -> pd.DataFrame:
    """ユニバース内で正規スコアに変換し、ファクターごとの欠損を 0 で埋める。

    全ファクターが欠損の銘柄は除外する。全銘柄が欠損のファクターは欠損のまま残す。
    """
    values = factors.loc[factors.index.intersection(universe)]
    values = values.where(values > MISSING_THRESHOLD).dropna(how="all")

    exposures = blom_score(values)
    covered = exposures.columns[exposures.notna().any()]
    exposures[covered] = exposures[covered].fillna(0.0)
    return exposures


def calc_slopes(exposures: pd.DataFrame, returns: pd.Series) -> pd.Series:
    """リターンのある銘柄で再度正規化し、ファクターごとの単回帰の傾きを返す。"""
    bids = exposures.index.intersection(returns.index)
    if len(bids) < 2:
        return pd.Series(np.nan, index=exposures.columns)

    x = blom_score(exposures.loc[bids]).to_numpy()
    y = returns.loc[bids].to_numpy()

    x_dev = x - x.mean(axis=0)
    y_dev = y - y.mean()
    numerator = (x_dev * y_dev[:, np.newaxis]).sum(axis=0)
    denominator = (x_dev**2).sum(axis=0)
    slopes = np.divide(
        numerator,
        denominator,
        out=np.full_like(numerator, np.nan),
        where=denominator > 0,
    )
    return pd.Series(slopes, index=exposures.columns)


def calc_common_factor_returns(
    universe: pd.DataFrame,
    returns: pd.DataFrame,
    monthly_factors: Mapping[int, pd.DataFrame],
) -> pd.DataFrame:
    """common ファクターの日次リターン (スコア 1 標準偏差あたりの %) を返す。

    universe: ymd, bid を持つ各日のユニバース。
    returns: ymd, bid, rtn を持つ日次リターン。
    monthly_factors: YYYYMM → 月次ファクター (bid が index)。

    ユニバース、リターン、前月のファクターのいずれかがない日は除外する。
    """
    universes = {
        int(ymd): pd.Index(bids) for ymd, bids in universe.groupby("ymd")["bid"]
    }
    daily_returns = {
        int(ymd): day.set_index("bid")["rtn"] for ymd, day in returns.groupby("ymd")
    }

    results: dict[int, pd.Series] = {}
    skipped: list[int] = []
    for ymd in sorted(universes.keys() | daily_returns.keys()):
        factors = monthly_factors.get(previous_ym(ymd))
        if factors is None or ymd not in universes or ymd not in daily_returns:
            skipped.append(ymd)
            continue
        results[ymd] = calc_slopes(
            make_exposures(factors, universes[ymd]), daily_returns[ymd]
        )

    if skipped:
        warnings.warn(f"データがないため該当する基準日を除外します: {skipped}")
    if not results:
        raise ValueError("計算できる日がありません")

    result = pd.DataFrame(results).T
    result.index.name = "date"
    return result


def calc_common_group_returns(factor_returns: pd.DataFrame) -> pd.DataFrame:
    """ファクターグループごとに、所属ファクターの単純平均リターンを返す。

    グループに属さないファクターは使わない。所属ファクターが 1 つもないグループは
    結果に含めない。符号の向きは調整しない。
    """
    groups: dict[str, pd.Series] = {}
    for group in COMMON_FACTOR_CATEGORIES:
        members = [
            factor
            for factor in factor_returns.columns
            if COMMON_FACTOR_CATEGORY_MAP.get(factor) == group
        ]
        if members:
            groups[group] = factor_returns[members].mean(axis=1)
    return pd.DataFrame(groups, index=factor_returns.index)
