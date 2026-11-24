"""common ファクターのファクターリターンを data/raw の CSV から算出する。

各基準日について、当日の AI スコアの銘柄をユニバースとし、前月の月次ファクターを
正規スコアに変換する。ファクターごとに当日の USD リターンを単回帰し、その傾きを
ファクターリターンとする。
"""

import warnings
from functools import cache
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

from em_market.const import (
    COMMON_FACTOR,
    COMMON_FACTOR_CATEGORIES,
    COMMON_FACTOR_CATEGORY_MAP,
)

MISSING_THRESHOLD: float = -100.0  # これ以下のファクター値は欠損として扱う
MAX_ABS_RTN: float = 100.0  # これ以上の絶対値 (%) はデータエラーとして除外する
BLOM_ALPHA: float = 3 / 8


def previous_ym(ymd: int) -> int:
    """基準日の前月を YYYYMM で返す。"""
    year, month = divmod(ymd // 100, 100)
    return (year - 1) * 100 + 12 if month == 1 else year * 100 + month - 1


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


def load_monthly_factors(raw_dir: Path, ym: int) -> pd.DataFrame | None:
    """月次ファクターを bid を index にして返す。ファイルがない・空の場合は None。"""
    path = raw_dir / "common" / f"{ym}.csv"
    if not path.exists():
        return None

    factors = pd.read_csv(
        path,
        usecols=["bid", *COMMON_FACTOR],
        dtype={factor: "float64" for factor in COMMON_FACTOR},
    )
    if factors.empty:
        return None
    return factors.set_index("bid")[COMMON_FACTOR]


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
    from_ymd: int,
    to_ymd: int,
    *,
    raw_dir: str | Path = "data/raw",
) -> pd.DataFrame:
    """common ファクターの日次リターン (スコア 1 標準偏差あたりの %) を返す。"""
    raw_dir = Path(raw_dir)
    calendar = pd.read_csv(raw_dir / "calendar.csv")
    ymds = calendar.loc[calendar["dateymd"].between(from_ymd, to_ymd), "dateymd"]

    monthly_factors: dict[int, pd.DataFrame | None] = {}
    results: dict[int, pd.Series] = {}
    skipped: list[int] = []

    for ymd in ymds.tolist():
        factor_ym = previous_ym(ymd)
        if factor_ym not in monthly_factors:
            monthly_factors[factor_ym] = load_monthly_factors(raw_dir, factor_ym)
        factors = monthly_factors[factor_ym]

        ai_path = raw_dir / "ai" / f"{ymd}.csv"
        rtn_path = raw_dir / "rtn" / f"{ymd}.csv"
        if factors is None or not ai_path.exists() or not rtn_path.exists():
            skipped.append(ymd)
            continue

        universe = pd.Index(pd.read_csv(ai_path, usecols=["bid"])["bid"].dropna())
        returns = (
            pd.read_csv(rtn_path, usecols=["bid", "rtn"])
            .dropna()
            .query("abs(rtn) < @MAX_ABS_RTN")
            .set_index("bid")["rtn"]
        )
        results[ymd] = calc_slopes(make_exposures(factors, universe), returns)

    if skipped:
        warnings.warn(f"データがないため該当する基準日を除外します: {skipped}")
    if not results:
        raise ValueError(f"対象期間に計算できる日がありません: {from_ymd}-{to_ymd}")

    result = pd.DataFrame(results).T[COMMON_FACTOR]
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
