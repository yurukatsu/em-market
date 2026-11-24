"""ユニバース、日次リターン、月次ファクターから common ファクターのリターンを算出する。

各基準日について、当日のユニバースの銘柄で月次ファクターを正規スコアに変換する。
ファクターごとに当日の USD リターンを単回帰し、その傾きをファクターリターンとする。
どの月のファクターを使うか (通常は前月) は、入力側で決める。
"""

import warnings
from collections.abc import Mapping
from functools import cache
from statistics import NormalDist

import numpy as np
import pandas as pd

from em_market.const import COMMON_FACTOR_CATEGORIES, COMMON_FACTOR_CATEGORY_MAP

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
    factors: Mapping[int, pd.DataFrame],
) -> pd.DataFrame:
    """common ファクターの日次リターン (スコア 1 標準偏差あたりの %) を返す。

    universe: ymd, bid を持つ各日のユニバース。
    returns: ymd, bid, rtn を持つ日次リターン。
    factors: 基準日 → その日に使う月次ファクター (bid が index)。

    ユニバース、リターン、ファクターのいずれかがない日は除外する。
    """
    universes = {
        int(ymd): pd.Index(bids) for ymd, bids in universe.groupby("ymd")["bid"]
    }
    daily_returns = {
        int(ymd): day.set_index("bid")["rtn"] for ymd, day in returns.groupby("ymd")
    }
    daily_factors = {int(ymd): values for ymd, values in factors.items()}

    results: dict[int, pd.Series] = {}
    skipped: list[int] = []
    for ymd in sorted(universes.keys() | daily_returns.keys() | daily_factors.keys()):
        if ymd not in universes or ymd not in daily_returns or ymd not in daily_factors:
            skipped.append(ymd)
            continue
        results[ymd] = calc_slopes(
            make_exposures(daily_factors[ymd], universes[ymd]), daily_returns[ymd]
        )

    if skipped:
        warnings.warn(f"データがないため該当する基準日を除外します: {skipped}")
    if not results:
        raise ValueError("計算できる日がありません")

    result = pd.DataFrame(results).T
    result.index.name = "date"
    return result


def calc_active_exposures(
    factors: pd.DataFrame,
    universe: pd.Index,
    port_weights: pd.Series,
    bm_weights: pd.Series,
) -> pd.Series:
    """ファクターごとに、ファンドと BM のエクスポージャーの差 (正規スコアの σ 単位) を返す。

    factors: その日に使う月次ファクター (bid が index)。
    universe: 正規スコアに変換するときの銘柄。
    port_weights, bm_weights: bid → ウェイト (それぞれ合計 1)。

    各銘柄のエクスポージャーは、ユニバース内で正規スコアに変換し欠損を 0 で埋めたもの
    (リターンの回帰と同じ) で、ユニバース外の銘柄は 0 とする。
    アクティブエクスポージャー = Σ (ファンドのウェイト − BM のウェイト) × エクスポージャー。
    全銘柄が欠損のファクターは NaN を返す。
    """
    exposures = make_exposures(factors, universe)
    active_weights = port_weights.sub(bm_weights, fill_value=0.0)
    weighted = exposures.reindex(active_weights.index).fillna(0.0)
    result = weighted.mul(active_weights, axis=0).sum()
    return result.where(exposures.notna().any())


def calc_common_group_exposures(factor_exposures: pd.Series) -> pd.Series:
    """ファクターグループごとに、所属ファクターのエクスポージャーの単純平均を返す。

    グループの作り方は calc_common_group_returns と同じ。
    """
    return calc_common_group_returns(factor_exposures.to_frame().T).iloc[0]


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
