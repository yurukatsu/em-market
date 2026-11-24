"""ファクターリターンを可視化する。

NAM ファクター (トータルリターン、スペシフィックリターン) と common ファクターグループを
それぞれ別の図にする。各行に、長期の累積推移 (対象期間を網掛け)、対象期間の拡大、対象期間のバー、
対象期間の累積リターンを並べる。累積はいずれも日次リターン (%) の単純和とする。
線は、Cumulative では表示開始時点、Period では期間の始点より上をプラスの色、
下をマイナスの色で描く。common ファクターグループには、アクティブエクスポージャーの列を
加えられる。
"""

from collections.abc import Mapping, Sequence
from typing import Literal

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from em_market.const import COMMON_FACTOR, COMMON_FACTOR_CATEGORY_MAP
from em_market.dates import ScoreFreq
from em_market.viz.style import (
    ACCENT,
    BAND,
    DN,
    FACTOR_BG,
    FIGSIZE,
    GRID,
    INK,
    MUTED,
    ROW_RULE,
    UP,
    ZERO,
)
from em_market.viz.style import format_ymd as _format_ymd
from em_market.viz.style import plot_signed as _plot_signed

# 図の横幅に対する各列の位置
COLUMNS: dict[str, tuple[float, float]] = {
    "name": (0.02, 0.24),
    "history": (0.255, 0.585),
    "period": (0.60, 0.73),
    "bar": (0.745, 0.885),
    "chg": (0.89, 0.98),
}
# Cumulative の列を省く場合 (対象期間だけを見る図)
COLUMNS_PERIOD_ONLY: dict[str, tuple[float, float]] = {
    "name": (0.02, 0.26),
    "period": (0.28, 0.64),
    "bar": (0.66, 0.88),
    "chg": (0.89, 0.98),
}
# アクティブエクスポージャーの列を加える場合
COLUMNS_WITH_EXPOSURE: dict[str, tuple[float, float]] = {
    "name": (0.02, 0.22),
    "history": (0.235, 0.50),
    "period": (0.515, 0.625),
    "bar": (0.64, 0.75),
    "chg": (0.755, 0.83),
    "exp_bar": (0.85, 0.915),
    "exp": (0.915, 0.98),
}

# 高さはインチ。行の高さは、図の高さに収まるように行数から決める
TITLE_H: float = 0.50
SECTION_H: float = 0.40
HEADER_H: float = 0.30
BOTTOM_H: float = 0.20
ROW_PAD_RATIO: float = 0.10  # 行の上下の余白 (行の高さに対する比率)
MAX_BAR_H: float = 0.28  # 棒の太さの上限

NAM_LABELS: dict[str, str] = {
    "ai": "AI",
    "ai70_bd30": "AI70 / BD30",
    "bd": "Bigdata",
    "rvl": "RVL",
    "tvl": "TVL",
    "rri": "RRI (class 1, 2)",
}
SCORE_LABELS: dict[str, str] = {"monthly": "month-end score", "daily": "daily score"}
RTN_LABELS: dict[str, str] = {"rtn": "total return", "srtn": "specific return"}


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


def _bar_limit(values: pd.Series) -> float:
    largest = values.abs().max()
    return largest * 1.15 if largest > 0 else 1.0


class _Canvas:
    """上から順に行を積むための、インチ単位の縦位置を持つ描画先。"""

    def __init__(
        self,
        fig: Figure,
        height: float,
        row_h: float,
        columns: dict[str, tuple[float, float]],
    ) -> None:
        self.fig = fig
        self.height = height
        self.row_h = row_h
        self.axes_h = row_h * (1 - 2 * ROW_PAD_RATIO)  # 行内のグラフの高さ
        self.columns = columns
        self.y = TITLE_H

    def axes(self, column: str) -> Axes:
        x0, x1 = self.columns[column]
        bottom = 1 - (self.y + self.row_h * (1 - ROW_PAD_RATIO)) / self.height
        ax = self.fig.add_axes((x0, bottom, x1 - x0, self.axes_h / self.height))
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

    def signed_bar(self, column: str, value: float, limit: float) -> None:
        """ゼロ中心の横棒を描く。行が高いときも棒が太くなりすぎないようにする。"""
        ax = self.axes(column)
        ax.barh(
            0,
            value,
            color=UP if value >= 0 else DN,
            height=min(0.62, MAX_BAR_H / self.axes_h),
        )
        ax.axvline(0, color=ZERO, lw=0.8)
        ax.set_xlim(-limit, limit)
        ax.set_ylim(-0.5, 0.5)

    def value_text(self, column: str, value: float, digits: int) -> None:
        """列の右端に符号付きの値を書く。欠損は n/a とする。"""
        x = self.columns[column][1] - 0.005
        style = {"fontsize": 9.5, "ha": "right", "fontfamily": "monospace"}
        if np.isnan(value):
            self.text(x, self.row_h / 2, "n/a", color=MUTED, **style)
        else:
            color = UP if value >= 0 else DN
            text = f"{value:+.{digits}f}"
            self.text(x, self.row_h / 2, text, color=color, fontweight="bold", **style)


def _draw_section_header(
    canvas: _Canvas,
    title: str,
    unit: str,
    history_from: int,
    history_to: int,
    name_header: str = "Name",
) -> None:
    columns = canvas.columns
    canvas.text(
        0.02, SECTION_H * 0.55, title, color=ACCENT, fontsize=12, fontweight="bold"
    )
    canvas.text(0.98, SECTION_H * 0.55, unit, color=MUTED, fontsize=9, ha="right")
    canvas.y += SECTION_H
    canvas.rule(ACCENT, 0.8)

    center = HEADER_H / 2
    header = {"color": ACCENT, "fontsize": 9, "fontweight": "bold"}
    canvas.text(columns["name"][0], center, name_header, **header)
    if "history" in columns:
        canvas.text(
            columns["history"][0],
            center,
            _format_ymd(history_from),
            color=MUTED,
            fontsize=8,
        )
        canvas.text(
            sum(columns["history"]) / 2, center, "Cumulative", ha="center", **header
        )
        canvas.text(
            columns["history"][1],
            center,
            _format_ymd(history_to),
            color=MUTED,
            fontsize=8,
            ha="right",
        )
    canvas.text(sum(columns["period"]) / 2, center, "Period", ha="center", **header)
    canvas.text(sum(columns["bar"]) / 2, center, "Chg Bar", ha="center", **header)
    canvas.text(columns["chg"][1] - 0.005, center, "Chg %", ha="right", **header)
    if "exp" in columns:
        exp_center = (columns["exp_bar"][0] + columns["exp"][1]) / 2
        canvas.text(exp_center, center, "Active Exp.", ha="center", **header)
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
    exposure: float | None,
    exposure_max: float,
    emphasis: bool = False,
) -> None:
    columns = canvas.columns
    center = canvas.row_h / 2
    canvas.text(
        columns["name"][0],
        center,
        label,
        color=INK,
        fontsize=9.5,
        fontweight="bold" if emphasis else "normal",
    )
    if sublabel:
        canvas.text(
            columns["name"][1] - 0.008,
            center,
            sublabel,
            color=MUTED,
            fontsize=7.5,
            ha="right",
        )

    if exposure is not None:
        if not np.isnan(exposure):
            canvas.signed_bar("exp_bar", exposure, exposure_max)
        canvas.value_text("exp", exposure, 3)

    canvas.value_text("chg", change, 2)
    if np.isnan(change):
        canvas.y += canvas.row_h
        canvas.rule(ROW_RULE, 0.4)
        return

    # 先頭に起点 0 を置き、期間の起点 (期間初日の前日の水準) を常に参照できるようにする。
    # 途中でリターンがない日は変化なしとして線をつなぐ
    level = np.concatenate([[0.0], daily.fillna(0.0).cumsum().to_numpy()])
    start = len(daily) - n_period
    base = level[start]
    x = np.arange(len(level))

    # 最初に値が出る日より前は描かず、その直前 (累積 0) から線を始める。
    # 期間内に欠損がない行だけを描くので、first は常に start 以下になる
    first = int(np.argmax(daily.notna().to_numpy()))

    # Cumulative: 累積 0 より上をプラス、下をマイナスの色で描く
    if "history" in columns:
        ax = canvas.axes("history")
        ax.axvspan(start, x[-1], color=BAND, lw=0)
        ax.hlines(0.0, x[first], x[-1], color=GRID, lw=0.7, ls=":")
        _plot_signed(ax, x[first:], level[first:], 0.0, 1.2)
        ax.set_xlim(0, x[-1] * 1.006)
        _set_ylim(ax, level[first:])

    # Period: 期間の始点より上をプラス、下をマイナスの色で描く
    ax = canvas.axes("period")
    period_level = level[start:]
    ax.axhline(base, color=GRID, lw=0.7, ls=":")
    _plot_signed(ax, np.arange(len(period_level)), period_level, base, 1.5)
    ax.set_xlim(0, (len(period_level) - 1) * 1.02)
    _set_ylim(ax, period_level)

    canvas.signed_bar("bar", change, bar_max)

    canvas.y += canvas.row_h
    canvas.rule(ROW_RULE, 0.4)


def _draw_section(
    canvas: _Canvas,
    title: str,
    unit: str,
    returns: pd.DataFrame,
    n_period: int,
    labels: dict[str, str],
    sublabels: dict[str, str],
    exposures: pd.Series | None,
    pinned: list[str],
    name_header: str,
) -> None:
    """期間リターンの降順に行を描く。期間内に欠損がある行は n/a として末尾に置く。

    pinned の行は太字で先頭に置き、ほかの行と線で区切る。
    """
    changes = returns.iloc[-n_period:].sum(min_count=n_period)
    pinned = [column for column in pinned if column in changes.index]
    changes = pd.concat(
        [changes[pinned], changes.drop(pinned).sort_values(ascending=False)]
    )
    bar_max = _bar_limit(changes)
    if exposures is not None:
        exposures = exposures.reindex(changes.index).astype(float)
        exposure_max = _bar_limit(exposures)
    else:
        exposure_max = 1.0

    _draw_section_header(
        canvas, title, unit, returns.index[0], returns.index[-1], name_header
    )
    for i, (column, change) in enumerate(changes.items()):
        _draw_row(
            canvas,
            labels.get(column, column),
            sublabels.get(column, ""),
            returns[column],
            n_period,
            change,
            bar_max,
            None if exposures is None else exposures[column],
            exposure_max,
            emphasis=column in pinned,
        )
        if i == len(pinned) - 1:
            canvas.rule(ACCENT, 0.8)


def draw_factor_chart(
    returns: pd.DataFrame,
    period_from_ymd: int,
    period_to_ymd: int,
    *,
    title: str,
    note: str = "",
    labels: Mapping[str, str] | None = None,
    sublabels: Mapping[str, str] | None = None,
    history_from_ymd: int | None = None,
    exposures: pd.Series | None = None,
    exposure_note: str = "",
    show_history: bool = True,
    pinned: Sequence[str] = (),
    name_header: str = "Name",
    subtitle: str | None = None,
    figsize: tuple[float, float] = FIGSIZE,
) -> Figure:
    """1 種類のファクターリターン (列がファクター、index が YYYYMMDD) を 1 枚の図にする。

    period_from_ymd から period_to_ymd を対象期間として網掛けし、Period、Chg Bar、
    Chg % に使う。Cumulative は history_from_ymd (省略時はデータの先頭) から
    period_to_ymd までを表示する。period_to_ymd より後のデータは使わない。

    リターンが 1 つもない日は除外する。対象期間に 1 日も値がないファクターは描かない。
    note はタイトルの右に表示する注釈。labels と sublabels で行の表示名と補足を指定する。
    exposures (ファクター → 値) を渡すと Active Exp. の列を加え、exposure_note を
    期間の表示に続けて書く。show_history=False なら Cumulative の列を省く。
    pinned の行は太字で先頭に置く。name_header は名前の列の見出し、subtitle は
    図の最上部の 1 行 (省略時は期間を書く)。figsize (インチ) は既定で 16:9 の
    スライド全面に合わせ、行の高さは行数から決める。
    """
    if exposures is not None and not show_history:
        raise ValueError("exposures と show_history=False は同時に指定できません")
    if period_from_ymd > period_to_ymd:
        raise ValueError(
            f"period_from_ymd が period_to_ymd より後です: {period_from_ymd}-{period_to_ymd}"
        )
    if history_from_ymd is not None and history_from_ymd > period_from_ymd:
        raise ValueError(
            f"history_from_ymd が period_from_ymd より後です: "
            f"{history_from_ymd} > {period_from_ymd}"
        )

    dates = returns.index.unique().sort_values()
    dates = dates[dates <= period_to_ymd]
    if history_from_ymd is not None:
        dates = dates[dates >= history_from_ymd]
    data = returns.reindex(dates)
    data = data[data.notna().any(axis=1)]

    period_dates = data.index[data.index >= period_from_ymd]
    if period_dates.empty:
        raise ValueError(
            f"対象期間にリターンがありません: {period_from_ymd}-{period_to_ymd}"
        )
    n_period = len(period_dates)

    # 対象期間に 1 日も値がないファクターは描かない
    data = data.loc[:, data.loc[period_dates].notna().any()]
    if data.shape[1] == 0:
        raise ValueError(
            f"対象期間に値のあるファクターがありません: {period_from_ymd}-{period_to_ymd}"
        )

    width, height = figsize
    row_h = (height - TITLE_H - SECTION_H - HEADER_H - BOTTOM_H) / data.shape[1]
    if row_h <= 0:
        raise ValueError(f"figsize の高さが足りません: {figsize}")
    if exposures is not None:
        columns = COLUMNS_WITH_EXPOSURE
    elif show_history:
        columns = COLUMNS
    else:
        columns = COLUMNS_PERIOD_ONLY
    fig = Figure(figsize=(width, height), facecolor=FACTOR_BG)
    canvas = _Canvas(fig, height, row_h, columns)

    if subtitle is None:
        subtitle = (
            f"Period {_format_ymd(period_dates[0])} – {_format_ymd(period_dates[-1])} "
            f"({n_period} days with returns)"
        )
        if show_history:
            subtitle += f"  |  History from {_format_ymd(data.index[0])}"
        if exposure_note:
            subtitle += f"  |  {exposure_note}"
    fig.text(0.02, 1 - 0.28 / height, subtitle, color=MUTED, fontsize=10, va="center")
    _draw_section(
        canvas,
        title,
        note,
        data,
        n_period,
        dict(labels or {}),
        dict(sublabels or {}),
        exposures,
        list(pinned),
        name_header,
    )
    return fig


def draw_nam_factors(
    nam_returns: pd.DataFrame,
    period_from_ymd: int,
    period_to_ymd: int,
    *,
    rtn_kind: Literal["rtn", "srtn"] = "rtn",
    score_freq: ScoreFreq = "monthly",
    history_from_ymd: int | None = None,
    figsize: tuple[float, float] = FIGSIZE,
) -> Figure:
    """NAM ファクターの図を作る。rtn_kind と score_freq は計算に使ったものを指定する。"""
    return draw_factor_chart(
        nam_returns,
        period_from_ymd,
        period_to_ymd,
        title=f"NAM factors ({RTN_LABELS[rtn_kind]})",
        note=(
            "Q5 (RRI: class 1, 2) equal-weight excess return, "
            f"{SCORE_LABELS[score_freq]}, sum of daily %"
        ),
        labels=NAM_LABELS,
        history_from_ymd=history_from_ymd,
        figsize=figsize,
    )


def draw_common_factor_groups(
    group_returns: pd.DataFrame,
    period_from_ymd: int,
    period_to_ymd: int,
    *,
    history_from_ymd: int | None = None,
    active_exposures: pd.Series | None = None,
    exposure_ymd: int | None = None,
    figsize: tuple[float, float] = FIGSIZE,
) -> Figure:
    """common ファクターグループ (トータルリターンへの回帰) の図を作る。

    active_exposures (グループ → ファンドと BM のエクスポージャーの差) を渡すと
    Active Exp. の列を加える。exposure_ymd はその基準日で、期間の表示に書き添える。
    """
    group_sizes = pd.Series(
        [
            COMMON_FACTOR_CATEGORY_MAP[f]
            for f in COMMON_FACTOR
            if f in COMMON_FACTOR_CATEGORY_MAP
        ]
    ).value_counts()

    exposure_note = ""
    if active_exposures is not None:
        exposure_note = "Active exposure (fund − BM, σ)"
        if exposure_ymd is not None:
            exposure_note += f" as of {_format_ymd(exposure_ymd)}"

    return draw_factor_chart(
        group_returns,
        period_from_ymd,
        period_to_ymd,
        title="Common factor groups (total return)",
        note="Simple average of member slopes per 1σ of score, sum of daily %",
        sublabels={group: f"{size} factors" for group, size in group_sizes.items()},
        history_from_ymd=history_from_ymd,
        exposures=active_exposures,
        exposure_note=exposure_note,
        figsize=figsize,
    )
