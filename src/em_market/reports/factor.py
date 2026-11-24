"""ファクターパフォーマンス: data/raw から計算し、結果の保存・読み込みと作図を行う。

計算と作図は em-market factor で続けて行う (設定は configs/cli/factor.yaml):
    計算結果 → data/processed/<日付>/factor/data/
    図       → data/processed/<日付>/factor/figures/
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, fields
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from em_market.dates import ScoreFreq
from em_market.factor.common import (
    calc_common_factor_returns,
    calc_common_group_returns,
)
from em_market.factor.nam import calc_nam_factor_returns
from em_market.factor.score import (
    SCORE_COLUMNS,
    calc_ic,
    calc_rebalance_corr,
    calc_tc,
)
from em_market.paths import RAW_DIR
from em_market.raw import (
    load_business_days,
    load_common_factors,
    load_returns,
    load_score_dates,
    load_scores,
    load_universe,
    load_weight_history,
)
from em_market.viz.factor_monitor import (
    NAM_LABELS,
    draw_common_factor_groups,
    draw_nam_factors,
)
from em_market.viz.market import save_png
from em_market.viz.score_monitor import draw_score_monitor

_FRAMES = ("nam_total", "nam_specific", "common_factors", "common_groups", "ic", "tc")


@dataclass
class FactorResults:
    """ファクターパフォーマンスの計算結果。save / load で CSV と meta.json に保存・復元する。

    from_ymd, to_ymd は計算期間。図で強調する週はレポートを作るときに決める。
    """

    from_ymd: int
    to_ymd: int
    score_freq: ScoreFreq
    reb_ymd: int | None
    nam_total: pd.DataFrame
    nam_specific: pd.DataFrame
    common_factors: pd.DataFrame
    common_groups: pd.DataFrame
    ic: pd.DataFrame
    tc: pd.DataFrame
    rebalance: pd.DataFrame | None = None

    def save(self, directory: Path) -> list[Path]:
        directory.mkdir(parents=True, exist_ok=True)
        frames = {name: getattr(self, name) for name in _FRAMES}
        if self.rebalance is not None:
            frames["rebalance"] = self.rebalance
        paths = []
        for name, df in frames.items():
            paths.append(directory / f"{name}.csv")
            df.to_csv(paths[-1])
        meta = {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name not in (*_FRAMES, "rebalance")
        }
        paths.append(directory / "meta.json")
        paths[-1].write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return paths

    @classmethod
    def load(cls, directory: Path) -> "FactorResults":
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))

        def frame(name: str) -> pd.DataFrame:
            return pd.read_csv(directory / f"{name}.csv", index_col=0)

        rebalance = (
            frame("rebalance") if (directory / "rebalance.csv").exists() else None
        )
        return cls(
            **meta,
            **{name: frame(name) for name in _FRAMES},
            rebalance=rebalance,
        )


def build_factor_results(
    from_ymd: int,
    to_ymd: int,
    *,
    score_freq: ScoreFreq = "monthly",
    reb_ymd: int | None = None,
    raw_dir: Path = RAW_DIR,
    log: Callable[[str], None] = print,
) -> FactorResults:
    """data/raw を読み込み、from_ymd から to_ymd までの各指標を計算する。

    score_freq: NAM のスコア (monthly: 直近の月末 / daily: 当日)。IC と TC にも同じスコアを使う。
    reb_ymd: リバランス日。この日以降の日次スコアでリバランス相関を計算する。None なら計算しない。
    """
    days = load_business_days(raw_dir, from_ymd, to_ymd)
    if not days:
        raise ValueError(f"計算期間に営業日がありません: {from_ymd}-{to_ymd}")

    log("読み込み")
    returns = load_returns(raw_dir, days, "rtn")
    specific = load_returns(raw_dir, days, "srtn")
    score_dates = load_score_dates(raw_dir, from_ymd, to_ymd, score_freq)
    scores = load_scores(raw_dir, score_dates.unique())

    log("NAM ファクター")
    nam_total = calc_nam_factor_returns(scores, returns, score_dates)
    nam_specific = calc_nam_factor_returns(scores, specific, score_dates)
    if nam_total.index.max() < to_ymd:
        log(
            f"data/raw のデータは {nam_total.index.max()} までです。"
            "続きは em-market factor-data で取得してください"
        )

    log("common ファクター")
    common_factors = calc_common_factor_returns(
        load_universe(raw_dir, days), returns, load_common_factors(raw_dir, days)
    )

    log("IC・TC")
    port = load_weight_history(raw_dir, "port", days)
    bm = load_weight_history(raw_dir, "bm", days)
    ic = calc_ic(scores, returns, score_dates)
    tc = calc_tc(scores, score_dates, port, bm)

    rebalance = None
    if reb_ymd is not None:
        log("リバランス相関")
        reb_dates = load_score_dates(raw_dir, reb_ymd, to_ymd, "daily")
        rebalance = calc_rebalance_corr(
            load_scores(raw_dir, reb_dates.unique()), reb_ymd
        )

    return FactorResults(
        from_ymd=from_ymd,
        to_ymd=to_ymd,
        score_freq=score_freq,
        reb_ymd=reb_ymd,
        nam_total=nam_total,
        nam_specific=nam_specific,
        common_factors=common_factors,
        common_groups=calc_common_group_returns(common_factors),
        ic=ic,
        tc=tc,
        rebalance=rebalance,
    )


def draw_factor_figures(
    results: FactorResults,
    period_from: int,
    period_to: int,
    output_dir: Path,
    log: Callable[[str], None] = print,
    *,
    ic_from: int | None = None,
    ic_font_scale: float = 1.0,
) -> list[Path]:
    """ファクターの図 (PNG) を output_dir に出力し、出力したファイルのパスを返す。

    period_from から period_to を対象期間として強調し、推移は計算期間の最初から描く。
    IC・TC・リバランス相関の図は ic_from (省略時は計算期間の最初) から描き、
    文字の大きさを ic_font_scale 倍にする。
    """
    r = results
    period = (period_from, period_to)
    if r.to_ymd < period_from or r.from_ymd > period_from:
        raise ValueError(
            f"計算期間 ({r.from_ymd}-{r.to_ymd}) に対象期間 "
            f"({period_from}-{period_to}) が含まれていません"
        )
    ic_from = r.from_ymd if ic_from is None else ic_from
    if not r.from_ymd <= ic_from <= period_from:
        raise ValueError(
            f"ic_from ({ic_from}) は計算期間の最初 ({r.from_ymd}) から"
            f"対象期間の最初 ({period_from}) までの日にしてください"
        )
    figures = {
        "11_factor_common_groups.png": draw_common_factor_groups(
            r.common_groups, *period, history_from_ymd=r.from_ymd
        ),
        "12_factor_nam_total.png": draw_nam_factors(
            r.nam_total,
            *period,
            rtn_kind="rtn",
            score_freq=r.score_freq,
            history_from_ymd=r.from_ymd,
        ),
        "13_factor_nam_specific.png": draw_nam_factors(
            r.nam_specific,
            *period,
            rtn_kind="srtn",
            score_freq=r.score_freq,
            history_from_ymd=r.from_ymd,
        ),
    }
    for column in SCORE_COLUMNS:
        figures[f"14_score_monitor_{column}.png"] = draw_score_monitor(
            r.ic[column],
            r.tc[column],
            *period,
            title=f"{NAM_LABELS[column]} score",
            rebalance=None if r.rebalance is None else r.rebalance[column],
            history_from_ymd=ic_from,
            font_scale=ic_font_scale,
        )

    paths = []
    for name, fig in figures.items():
        log(f"作図: {name}")
        paths.append(save_png(fig, output_dir / name))
        plt.close(fig)
    return paths
