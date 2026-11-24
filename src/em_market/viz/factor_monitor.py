"""NAM ファクターと common ファクターグループのリターンを 1 枚に可視化する。

各行に、対象期間の累積リターン、長期の累積推移 (対象期間を網掛け)、対象期間の拡大、
対象期間のバーを並べる。累積はいずれも日次リターン (%) の単純和とする。
"""

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from em_market.const import COMMON_FACTOR, COMMON_FACTOR_CATEGORY_MAP
from em_market.factor.common import (
    calc_common_factor_returns,
    calc_common_group_returns,
)
from em_market.factor.nam import ScoreFreq, calc_nam_factor_returns

BG, FG, GRID = "#000000", "#FFA028", "#333333"
UP, DN = "#4AF626", "#FF433D"
INK, MUTED, TREND, BAND, ROW_RULE = (
    "#FFFFFF",
    "#A0A0A0",
    "#7D7D7D",
    "#3A2A12",
    "#1C1C1C",
)

# 図の横幅に対する各列の位置
COLUMNS: dict[str, tuple[float, float]] = {
    "name": (0.02, 0.205),
    "chg": (0.205, 0.285),
    "history": (0.30, 0.655),
    "period": (0.675, 0.805),
    "bar": (0.825, 0.98),
}

# 高さはインチ
FIG_WIDTH: float = 13.0
TITLE_H: float = 0.80
SECTION_H: float = 0.40
HEADER_H: float = 0.30
ROW_H: float = 0.30
SECTION_GAP: float = 0.14
FOOTER_H: float = 0.66
ROW_PAD: float = 0.035
DPI: int = 150

NAM_LABELS: dict[str, str] = {
    "ai": "AI",
    "ai70_bd30": "AI70 / BD30",
    "bd": "Bigdata",
    "rvl": "RVL",
    "tvl": "TVL",
    "rri": "RRI (class 1, 2)",
}
SCORE_LABELS: dict[str, str] = {"monthly": "month-end score", "daily": "daily score"}


def _format_ymd(ymd: int) -> str:
    return f"{ymd // 10000}/{ymd // 100 % 100:02d}/{ymd % 100:02d}"


def _clean_axes(ax: Axes) -> None:
    ax.set_facecolor("none")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)


def _set_ylim(ax: Axes, values: np.ndarray) -> None:
    low, high = np.nanmin(values), np.nanmax(values)
    pad = max((high - low) * 0.1, 1e-6)
    ax.set_ylim(low - pad, high + pad)


class _Canvas:
    """上から順に行を積むための、インチ単位の縦位置を持つ描画先。"""

    def __init__(self, fig: Figure, height: float) -> None:
        self.fig = fig
        self.height = height
        self.y = TITLE_H

    def axes(self, column: str) -> Axes:
        x0, x1 = COLUMNS[column]
        bottom = 1 - (self.y + ROW_H - ROW_PAD) / self.height
        ax = self.fig.add_axes(
            (x0, bottom, x1 - x0, (ROW_H - 2 * ROW_PAD) / self.height)
        )
        _clean_axes(ax)
        return ax

    def text(self, x: float, offset: float, text: str, **kwargs) -> None:
        self.fig.text(
            x, 1 - (self.y + offset) / self.height, text, va="center", **kwargs
        )

    def rule(self, color: str = GRID, linewidth: float = 0.6) -> None:
        y = 1 - self.y / self.height
        self.fig.add_artist(
            Line2D(
                [0.02, 0.98],
                [y, y],
                color=color,
                lw=linewidth,
                transform=self.fig.transFigure,
            )
        )


def _draw_section_header(
    canvas: _Canvas,
    title: str,
    unit: str,
    history_from: int,
    history_to: int,
) -> None:
    canvas.text(0.02, SECTION_H * 0.55, title, color=FG, fontsize=12, fontweight="bold")
    canvas.text(0.98, SECTION_H * 0.55, unit, color=MUTED, fontsize=9, ha="right")
    canvas.y += SECTION_H
    canvas.rule(FG, 0.8)

    center = HEADER_H / 2
    header = {"color": FG, "fontsize": 9, "fontweight": "bold"}
    canvas.text(COLUMNS["name"][0], center, "Name", **header)
    canvas.text(COLUMNS["chg"][1] - 0.005, center, "Chg %", ha="right", **header)
    canvas.text(
        COLUMNS["history"][0],
        center,
        _format_ymd(history_from),
        color=MUTED,
        fontsize=8,
    )
    canvas.text(
        sum(COLUMNS["history"]) / 2,
        center,
        "Cumulative (shaded = period)",
        ha="center",
        **header,
    )
    canvas.text(
        COLUMNS["history"][1],
        center,
        _format_ymd(history_to),
        color=MUTED,
        fontsize=8,
        ha="right",
    )
    canvas.text(sum(COLUMNS["period"]) / 2, center, "Period", ha="center", **header)
    canvas.text(sum(COLUMNS["bar"]) / 2, center, "Chg bar", ha="center", **header)
    canvas.y += HEADER_H
    canvas.rule()


def _draw_row(
    canvas: _Canvas,
    label: str,
    sublabel: str,
    daily: pd.Series,
    n_period: int,
    change: float,
    bar_max: float,
) -> None:
    center = ROW_H / 2
    canvas.text(COLUMNS["name"][0], center, label, color=INK, fontsize=9.5)
    if sublabel:
        canvas.text(
            COLUMNS["name"][1] - 0.008,
            center,
            sublabel,
            color=MUTED,
            fontsize=7.5,
            ha="right",
        )

    chg_x = COLUMNS["chg"][1] - 0.005
    if np.isnan(change):
        n_missing = int(daily.iloc[-n_period:].isna().sum())
        message = (
            "No returns in the period"
            if n_missing == n_period
            else f"Returns missing on {n_missing} of {n_period} days in the period"
        )
        canvas.text(
            chg_x,
            center,
            "n/a",
            color=MUTED,
            fontsize=9.5,
            ha="right",
            fontfamily="monospace",
        )
        canvas.text(
            sum(COLUMNS["history"]) / 2,
            center,
            message,
            color=MUTED,
            fontsize=8,
            ha="center",
        )
        canvas.y += ROW_H
        canvas.rule(ROW_RULE, 0.4)
        return

    color = UP if change >= 0 else DN
    canvas.text(
        chg_x,
        center,
        f"{change:+.2f}",
        color=color,
        fontsize=9.5,
        ha="right",
        fontfamily="monospace",
    )

    # 先頭に起点 0 を置き、期間の起点 (期間初日の前日の水準) を常に参照できるようにする
    level = np.concatenate([[0.0], daily.fillna(0.0).cumsum().to_numpy()])
    observed = np.concatenate([[True], daily.notna().to_numpy()])
    shown = np.where(observed, level, np.nan)  # リターンがない日は線を切る
    start = len(daily) - n_period
    base = level[start]
    x = np.arange(len(level))

    ax = canvas.axes("history")
    ax.axvspan(start, x[-1], color=BAND, lw=0)
    ax.axhline(base, color=GRID, lw=0.7, ls=":")
    ax.plot(x[: start + 1], shown[: start + 1], color=TREND, lw=1.0)
    ax.plot(x[start:], level[start:], color=color, lw=1.6)
    ax.scatter([x[-1]], [level[-1]], color=color, s=9, zorder=3)
    ax.set_xlim(0, x[-1] * 1.006)
    _set_ylim(ax, shown)

    ax = canvas.axes("period")
    period_level = level[start:]
    ax.axhline(base, color=GRID, lw=0.7, ls=":")
    ax.plot(np.arange(len(period_level)), period_level, color=color, lw=1.5)
    ax.scatter([len(period_level) - 1], [period_level[-1]], color=color, s=9, zorder=3)
    ax.set_xlim(0, (len(period_level) - 1) * 1.02)
    _set_ylim(ax, period_level)

    ax = canvas.axes("bar")
    ax.barh(0, change, color=color, height=0.62)
    ax.axvline(0, color="#888888", lw=0.8)
    ax.set_xlim(-bar_max, bar_max)
    ax.set_ylim(-0.5, 0.5)

    canvas.y += ROW_H
    canvas.rule(ROW_RULE, 0.4)


def _draw_section(
    canvas: _Canvas,
    title: str,
    unit: str,
    returns: pd.DataFrame,
    n_period: int,
    labels: dict[str, str],
    sublabels: dict[str, str],
) -> None:
    """期間リターンの降順に行を描く。期間内に欠損がある行は n/a として末尾に置く。"""
    changes = (
        returns.iloc[-n_period:].sum(min_count=n_period).sort_values(ascending=False)
    )
    largest = changes.abs().max()
    bar_max = largest * 1.15 if largest > 0 else 1.0

    _draw_section_header(canvas, title, unit, returns.index[0], returns.index[-1])
    for column, change in changes.items():
        _draw_row(
            canvas,
            labels.get(column, column),
            sublabels.get(column, ""),
            returns[column],
            n_period,
            change,
            bar_max,
        )


def draw_factor_monitor(
    nam_returns: pd.DataFrame,
    group_returns: pd.DataFrame,
    from_ymd: int,
    to_ymd: int,
    *,
    score_freq: ScoreFreq = "monthly",
) -> Figure:
    """算出済みのファクターリターンから図を作る。

    from_ymd から to_ymd を対象期間として網掛けする。to_ymd より後のデータは使わない。
    両者の日付は和集合にそろえ、片方にない日は欠損として扱う。どちらにもリターンが
    1 つもない日は除外する。
    """
    if from_ymd > to_ymd:
        raise ValueError(f"from_ymd が to_ymd より後です: {from_ymd}-{to_ymd}")

    dates = nam_returns.index.union(group_returns.index).unique().sort_values()
    dates = dates[dates <= to_ymd]
    nam = nam_returns.reindex(dates)
    groups = group_returns.reindex(dates)

    has_returns = nam.notna().any(axis=1) | groups.notna().any(axis=1)
    nam, groups = nam[has_returns], groups[has_returns]
    dates = nam.index

    period_dates = dates[dates >= from_ymd]
    if period_dates.empty:
        raise ValueError(f"対象期間にリターンがありません: {from_ymd}-{to_ymd}")
    n_period = len(period_dates)

    group_sizes = pd.Series(
        [
            COMMON_FACTOR_CATEGORY_MAP[f]
            for f in COMMON_FACTOR
            if f in COMMON_FACTOR_CATEGORY_MAP
        ]
    ).value_counts()
    sublabels = {
        group: f"{group_sizes[group]} factors"
        for group in groups.columns
        if group in group_sizes.index
    }

    height = (
        TITLE_H
        + 2 * (SECTION_H + HEADER_H)
        + ROW_H * (nam.shape[1] + groups.shape[1])
        + SECTION_GAP
        + FOOTER_H
    )
    fig = Figure(figsize=(FIG_WIDTH, height), facecolor=BG)
    canvas = _Canvas(fig, height)

    fig.text(
        0.02,
        1 - 0.30 / height,
        "EM Factor Monitor",
        color=FG,
        fontsize=17,
        fontweight="bold",
        va="center",
    )
    fig.text(
        0.02,
        1 - 0.58 / height,
        f"Period {_format_ymd(period_dates[0])} – {_format_ymd(period_dates[-1])} "
        f"({n_period} days with returns)  |  History from {_format_ymd(dates[0])}",
        color=MUTED,
        fontsize=10,
        va="center",
    )

    _draw_section(
        canvas,
        f"NAM factors ({SCORE_LABELS[score_freq]})",
        "Q5 (RRI: class 1, 2) equal-weight excess return, sum of daily %",
        nam,
        n_period,
        NAM_LABELS,
        {},
    )
    canvas.y += SECTION_GAP
    _draw_section(
        canvas,
        "Common factor groups",
        "Simple average of member slopes per 1σ of score, sum of daily %",
        groups,
        n_period,
        {},
        sublabels,
    )

    canvas.y += 0.12
    canvas.text(
        0.02,
        0.10,
        "Each line uses its own y-scale. Dotted line = level at the start of the period. "
        "NAM and Common bars use separate scales.",
        color=MUTED,
        fontsize=8,
    )
    canvas.text(
        0.02,
        0.30,
        f"Common groups use {int(group_sizes.sum())} of {len(COMMON_FACTOR)} factors. "
        "Member signs are not aligned.",
        color=MUTED,
        fontsize=8,
    )
    return fig


def plot_factor_monitor(
    from_ymd: int,
    to_ymd: int,
    *,
    history_from: int | None = None,
    raw_dir: str | Path = "data/raw",
    score_freq: ScoreFreq = "monthly",
    out: str | Path | None = None,
) -> Figure:
    """data/raw からリターンを算出して図を作り、out を指定した場合は保存する。

    history_from を省略した場合、推移は to_ymd の年の 1 月 1 日から表示する。
    対象期間がそれより前に始まる場合は from_ymd から表示する。
    """
    if from_ymd > to_ymd:
        raise ValueError(f"from_ymd が to_ymd より後です: {from_ymd}-{to_ymd}")
    if history_from is None:
        history_from = min(from_ymd, to_ymd // 10000 * 10000 + 101)
    if history_from > from_ymd:
        raise ValueError(
            f"history_from が from_ymd より後です: {history_from} > {from_ymd}"
        )

    nam_returns = calc_nam_factor_returns(
        history_from, to_ymd, raw_dir=raw_dir, score_freq=score_freq
    )
    factor_returns = calc_common_factor_returns(history_from, to_ymd, raw_dir=raw_dir)
    group_returns = calc_common_group_returns(factor_returns)

    fig = draw_factor_monitor(
        nam_returns, group_returns, from_ymd, to_ymd, score_freq=score_freq
    )
    if out is not None:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=DPI, facecolor=BG)
    return fig
