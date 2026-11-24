"""NAM ファクターのファクターリターンを data/raw の CSV から算出する。

各基準日について、直近の月末営業日のスコア (monthly) または当日朝に確定する
当日のスコア (daily) を使い、以下の銘柄の等ウェイトリターンをファクターリターンとする。

- ai, ai70_bd30, bd, rvl, tvl: Region ごとの 5 分位の最上位 (Q5)
- rri: スコアが 1 または 2 の銘柄

Region に対応付けられない銘柄はポートフォリオに含めず、市場平均の計算にのみ含める。
"""

import warnings
from pathlib import Path
from typing import Literal

import pandas as pd

from em_market.const import COUNTRY_INFO

QUANTILE_FACTORS: list[str] = ["ai", "ai70_bd30", "bd", "rvl", "tvl"]
FACTORS: list[str] = [*QUANTILE_FACTORS, "rri"]
N_QUANTILES: int = 5
RRI_LONG_VALUES: list[int] = [1, 2]
MAX_ABS_RTN: float = 100.0  # これ以上の絶対値 (%) はデータエラーとして除外する

RtnKind = Literal["rtn", "srtn"]
Breakpoints = Literal["by_date", "pooled"]
ScoreFreq = Literal["monthly", "daily"]


def load_score_dates(
    raw_dir: Path,
    from_ymd: int,
    to_ymd: int,
    score_freq: ScoreFreq = "monthly",
) -> pd.Series:
    """基準日 → 使用するスコア日の対応を返す。

    score_freq:
        monthly: 直近の月末営業日のスコアを使う。
        daily: 当日のスコアを使う。スコアは当日朝に確定している前提。
    """
    calendar = pd.read_csv(raw_dir / "calendar.csv")
    calendar = calendar[calendar["dateymd"].between(from_ymd, to_ymd)]
    calendar = calendar.set_index("dateymd")

    if score_freq == "monthly":
        score_dates = calendar["latest_month_end"].dropna().astype(int)
    elif score_freq == "daily":
        score_dates = pd.Series(calendar.index, index=calendar.index)
    else:
        raise ValueError(f"score_freq が不正です: {score_freq!r}")

    missing = [
        ymd
        for ymd in score_dates.unique()
        if not (raw_dir / "ai" / f"{ymd}.csv").exists()
        or not (raw_dir / "bd" / f"{ymd}.csv").exists()
    ]
    if missing:
        warnings.warn(f"スコアがないため該当する基準日を除外します: {missing}")
        score_dates = score_dates[~score_dates.isin(missing)]

    return score_dates


def load_scores(raw_dir: Path, score_ymd: int) -> pd.DataFrame:
    """指定日の AI / Bigdata スコアを結合して返す。時期により存在しない列は NaN。"""
    ai = pd.read_csv(
        raw_dir / "ai" / f"{score_ymd}.csv",
        usecols=["bid", "ai", "ai70_bd30", "bigdata"],
    ).rename(columns={"bigdata": "bd"})
    bigdata = pd.read_csv(raw_dir / "bd" / f"{score_ymd}.csv").reindex(
        columns=["bid", "rvl", "tvl", "rri"]
    )

    scores = ai.merge(bigdata, on="bid", how="left")
    scores["score_ymd"] = score_ymd
    scores["region"] = (
        scores["bid"]
        .str[:3]
        .map({country: info["region"] for country, info in COUNTRY_INFO.items()})
    )
    return scores


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


def load_returns(raw_dir: Path, ymds: list[int], rtn_kind: RtnKind) -> pd.DataFrame:
    paths = {ymd: raw_dir / rtn_kind / f"{ymd}.csv" for ymd in ymds}

    missing = [ymd for ymd, path in paths.items() if not path.exists()]
    if missing:
        warnings.warn(f"{rtn_kind} がないため該当する基準日を除外します: {missing}")

    returns = pd.concat(
        [
            pd.read_csv(path, usecols=["ymd", "bid", "rtn"])
            for path in paths.values()
            if path.exists()
        ],
        ignore_index=True,
    )
    return returns[returns["rtn"].abs() < MAX_ABS_RTN]


def calc_nam_factor_returns(
    from_ymd: int,
    to_ymd: int,
    *,
    raw_dir: str | Path = "data/raw",
    rtn_kind: RtnKind = "rtn",
    score_freq: ScoreFreq = "monthly",
    breakpoints: Breakpoints = "by_date",
    excess: bool = True,
) -> pd.DataFrame:
    """NAM ファクターの日次リターン (%) を返す。

    excess=True の場合は、ユニバースの等ウェイト平均を控除する。ユニバースは
    by_date ではその日に使うスコアの銘柄、pooled では現行方式と同じく
    計算期間のいずれかのスコアに含まれる銘柄とする。
    """
    raw_dir = Path(raw_dir)
    score_dates = load_score_dates(raw_dir, from_ymd, to_ymd, score_freq)
    if score_dates.empty:
        raise ValueError(f"対象期間に利用できるスコアがありません: {from_ymd}-{to_ymd}")

    scores = pd.concat(
        [load_scores(raw_dir, ymd) for ymd in score_dates.unique()],
        ignore_index=True,
    )
    flags = flag_long_names(scores, score_dates, breakpoints)

    returns = load_returns(raw_dir, score_dates.index.tolist(), rtn_kind)
    returns["score_ymd"] = returns["ymd"].map(score_dates)
    if breakpoints == "pooled":
        returns = returns[returns["bid"].isin(scores["bid"])].copy()
    else:
        returns = returns.merge(scores[["bid", "score_ymd"]], on=["bid", "score_ymd"])

    if excess:
        returns["rtn"] -= returns.groupby("ymd")["rtn"].transform("mean")

    panel = returns.merge(flags, on=["bid", "score_ymd"], how="inner")

    result = pd.DataFrame(
        {
            factor: panel.loc[panel[factor]].groupby("ymd")["rtn"].mean()
            for factor in FACTORS
        },
        index=pd.Index(sorted(panel["ymd"].unique()), name="date"),
    )
    return result
