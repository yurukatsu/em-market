"""data/raw の CSV を読み込む。ファクターリターンの計算は行わない。"""

import warnings
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import pandas as pd

from em_market.const import COMMON_FACTOR
from em_market.dates import ScoreFreq, previous_ym

MAX_ABS_RTN: float = 100.0  # これ以上の絶対値 (%) はデータエラーとして除外する

RtnKind = Literal["rtn", "srtn"]
WeightKind = Literal["port", "bm"]


def load_business_days(raw_dir: str | Path, from_ymd: int, to_ymd: int) -> list[int]:
    """期間内の営業日を返す。"""
    calendar = pd.read_csv(Path(raw_dir) / "calendar.csv", usecols=["dateymd"])
    return calendar.loc[
        calendar["dateymd"].between(from_ymd, to_ymd), "dateymd"
    ].tolist()


def load_score_dates(
    raw_dir: str | Path,
    from_ymd: int,
    to_ymd: int,
    score_freq: ScoreFreq = "monthly",
) -> pd.Series:
    """基準日 → 使用するスコア日の対応を返す。

    score_freq:
        monthly: 直近の月末営業日のスコアを使う。
        daily: 当日のスコアを使う。スコアは当日朝に確定している前提。
    """
    raw_dir = Path(raw_dir)
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

    if score_dates.empty:
        raise ValueError(f"対象期間に利用できるスコアがありません: {from_ymd}-{to_ymd}")
    return score_dates


def _load_score(raw_dir: Path, score_ymd: int) -> pd.DataFrame:
    ai = pd.read_csv(
        raw_dir / "ai" / f"{score_ymd}.csv",
        usecols=["bid", "ai", "ai70_bd30", "bigdata"],
    ).rename(columns={"bigdata": "bd"})
    bigdata = pd.read_csv(raw_dir / "bd" / f"{score_ymd}.csv").reindex(
        columns=["bid", "rvl", "tvl", "rri"]
    )
    scores = ai.merge(bigdata, on="bid", how="left")
    scores["score_ymd"] = score_ymd
    return scores


def load_scores(raw_dir: str | Path, score_ymds: Iterable[int]) -> pd.DataFrame:
    """指定日の AI / Bigdata スコアを縦持ちで返す。時期により存在しない列は NaN。"""
    raw_dir = Path(raw_dir)
    return pd.concat(
        [_load_score(raw_dir, ymd) for ymd in score_ymds],
        ignore_index=True,
    )


def load_returns(
    raw_dir: str | Path,
    ymds: Iterable[int],
    rtn_kind: RtnKind = "rtn",
) -> pd.DataFrame:
    """日次リターン (ymd, bid, rtn) を返す。欠損とデータエラーは除外する。"""
    raw_dir = Path(raw_dir)
    paths = {ymd: raw_dir / rtn_kind / f"{ymd}.csv" for ymd in ymds}

    missing = [ymd for ymd, path in paths.items() if not path.exists()]
    if missing:
        warnings.warn(f"{rtn_kind} がないため該当する基準日を除外します: {missing}")
    if len(missing) == len(paths):
        raise ValueError(f"読み込める {rtn_kind} がありません")

    returns = pd.concat(
        [
            pd.read_csv(path, usecols=["ymd", "bid", "rtn"])
            for path in paths.values()
            if path.exists()
        ],
        ignore_index=True,
    ).dropna(subset=["bid", "rtn"])
    return returns[returns["rtn"].abs() < MAX_ABS_RTN].reset_index(drop=True)


def load_universe(raw_dir: str | Path, ymds: Iterable[int]) -> pd.DataFrame:
    """各日の AI スコアの銘柄をユニバース (ymd, bid) として返す。"""
    raw_dir = Path(raw_dir)
    paths = {ymd: raw_dir / "ai" / f"{ymd}.csv" for ymd in ymds}

    missing = [ymd for ymd, path in paths.items() if not path.exists()]
    if missing:
        warnings.warn(f"ai がないため該当する基準日を除外します: {missing}")
    if len(missing) == len(paths):
        raise ValueError("読み込める ai がありません")

    frames = [
        pd.read_csv(path, usecols=["bid"]).dropna().assign(ymd=ymd)
        for ymd, path in paths.items()
        if path.exists()
    ]
    return pd.concat(frames, ignore_index=True)[["ymd", "bid"]]


def load_common_factors(
    raw_dir: str | Path,
    ymds: Iterable[int],
) -> dict[int, pd.DataFrame]:
    """基準日 → その日に使う月次ファクター (bid が index) を返す。

    common/{基準日}.csv には、基準日のユニバースの銘柄について前月のファクターが
    入っている前提とする。ファイルがない・空の日は含めない。DATE が前月でない
    ファイルは、将来の情報を使わないようエラーにする。
    """
    raw_dir = Path(raw_dir)
    result: dict[int, pd.DataFrame] = {}
    missing: list[int] = []
    for ymd in ymds:
        path = raw_dir / "common" / f"{ymd}.csv"
        if not path.exists():
            missing.append(ymd)
            continue
        factors = pd.read_csv(
            path,
            usecols=["bid", "DATE", *COMMON_FACTOR],
            dtype={factor: "float64" for factor in COMMON_FACTOR},
        )
        if factors.empty:
            missing.append(ymd)
            continue

        months = sorted(set(factors["DATE"].dropna().astype(int)))
        if months != [previous_ym(ymd)]:
            raise ValueError(
                f"common/{ymd}.csv の DATE が前月 ({previous_ym(ymd)}) ではありません: {months}"
            )
        result[ymd] = factors.set_index("bid")[COMMON_FACTOR]

    if missing:
        warnings.warn(f"common がないため該当する基準日を除外します: {missing}")
    if not result:
        raise ValueError("読み込める common がありません")
    return result


def load_weights(raw_dir: str | Path, kind: WeightKind, ymd: int) -> pd.Series:
    """指定日のウェイトを bid → 比率 (全銘柄の合計が 1) で返す。

    kind: port (ファンド) または bm (ベンチマーク)。bid がない銘柄は警告を出して除き、
    その分を残りの銘柄に配り直さない。
    """
    path = Path(raw_dir) / kind / f"{ymd}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{kind} がありません: {path}")

    weights, n_no_bid, share = _read_weights(path)
    if n_no_bid:
        warnings.warn(
            f"{kind}/{ymd}.csv の bid がない {n_no_bid} 銘柄 "
            f"(ウェイト {share:.2%}) を除外します"
        )
    return weights


def load_weight_history(
    raw_dir: str | Path, kind: WeightKind, ymds: Iterable[int]
) -> pd.DataFrame:
    """複数日のウェイト (ymd, bid, weight) を返す。各日の合計は 1 (load_weights と同じ)。

    ファイルがない日は除き、bid がない銘柄を除いた日とあわせて警告を 1 回だけ出す。
    """
    raw_dir = Path(raw_dir)
    frames: list[pd.DataFrame] = []
    missing: list[int] = []
    no_bid_days: list[int] = []
    for ymd in ymds:
        path = raw_dir / kind / f"{ymd}.csv"
        if not path.exists():
            missing.append(ymd)
            continue
        weights, n_no_bid, _ = _read_weights(path)
        if n_no_bid:
            no_bid_days.append(ymd)
        frames.append(weights.reset_index().assign(ymd=ymd))

    if missing:
        warnings.warn(f"{kind} がないため該当する日を除外します: {missing}")
    if no_bid_days:
        warnings.warn(f"{kind} の bid がない銘柄を除外した日: {no_bid_days}")
    if not frames:
        raise ValueError(f"読み込める {kind} がありません")
    return pd.concat(frames, ignore_index=True)[["ymd", "bid", "weight"]]


def _read_weights(path: Path) -> tuple[pd.Series, int, float]:
    """ウェイトを bid → 比率で返す。あわせて bid がない銘柄の数とウェイトの比率を返す。"""
    holdings = pd.read_csv(path, usecols=["bid", "weight"])
    total = holdings["weight"].sum()
    no_bid = holdings["bid"].isna()
    share = holdings.loc[no_bid, "weight"].sum() / total
    weights = holdings[~no_bid].groupby("bid")["weight"].sum() / total
    weights.name = "weight"
    return weights, int(no_bid.sum()), float(share)
