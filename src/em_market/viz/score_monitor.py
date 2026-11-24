"""スコアのモニター (IC、TC、リバランス相関) を可視化する。

日付の軸をそろえて上下に並べる。

- IC: 日次の値を棒、移動平均を線で描く
- TC: 日次の値を線で描く
- リバランス相関: 日次の値を棒で描く (任意)

対象期間は網掛けし、対象期間の棒は濃く、それ以前の棒は薄く描く。
値がプラスなら青、マイナスならえんじ色とする。
"""

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from em_market.viz.style import (
    ACCENT,
    BAND,
    BG,
    DN,
    FIGSIZE,
    GRID,
    INK,
    MUTED,
    ROW_RULE,
    UP,
    ZERO,
    format_ymd,
    plot_signed,
)

MA_WINDOW: int = 20
HISTORY_ALPHA: float = 0.40  # 対象期間より前の棒の濃さ
LABEL_WIDTH: float = 0.40  # 値のラベルの幅の目安 (インチ)
LABEL_MARGIN: float = 0.45  # グラフの右側に空ける幅 (インチ)


def _style_axes(ax: Axes) -> None:
    ax.set_facecolor("none")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
        ax.spines[side].set_linewidth(0.6)
    ax.tick_params(colors=MUTED, labelsize=8, length=2)
    ax.grid(axis="y", color=ROW_RULE, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.axhline(0, color=ZERO, linewidth=0.8, zorder=1)


def _panel_title(ax: Axes, left: str, right: str) -> None:
    ax.set_title(left, loc="left", fontsize=10.5, fontweight="bold", color=ACCENT)
    ax.set_title(right, loc="right", fontsize=9, color=MUTED)


def _value_label(ax: Axes, x: float, y: float, text: str, ha: str = "center") -> None:
    ax.annotate(
        text,
        (x, y),
        xytext=({"left": 3, "right": -3}.get(ha, 0), 4 if y >= 0 else -4),
        textcoords="offset points",
        ha=ha,
        va="bottom" if y >= 0 else "top",
        fontsize=7.5,
        color=INK,
    )


def _edge_marks(marks: np.ndarray) -> list[tuple[int, str]]:
    """対象期間の最初と最後の位置と、ラベルの寄せ方 (最初は左、最後は右) を返す。"""
    if len(marks) == 0:
        return []
    if len(marks) == 1:
        return [(int(marks[0]), "center")]
    return [(int(marks[0]), "right"), (int(marks[-1]), "left")]


def _signed_bars(
    ax: Axes, x: np.ndarray, values: pd.Series, in_period: np.ndarray
) -> None:
    """値の符号で色を分けた棒を描く。対象期間より前の棒は薄くする。"""
    valid = values.notna().to_numpy()
    colors = np.where(values.to_numpy() >= 0, UP, DN)
    for mask, alpha in ((valid & ~in_period, HISTORY_ALPHA), (valid & in_period, 1.0)):
        if mask.any():
            ax.bar(
                x[mask],
                values.to_numpy()[mask],
                width=0.8,
                color=colors[mask],
                alpha=alpha,
                zorder=2,
            )


def _set_ylim_with_zero(ax: Axes, values: pd.Series) -> None:
    low = min(0.0, float(values.min()))
    high = max(0.0, float(values.max()))
    pad = max((high - low) * 0.15, 1e-3)
    ax.set_ylim(low - pad, high + pad)


def _date_ticks(ax: Axes, dates: pd.Index) -> None:
    """月の最初の日に目盛りを置く。2 か月に満たない場合は 5 か所程度に置く。"""
    months = pd.Series(dates // 100, index=range(len(dates)))
    starts = months.index[months.ne(months.shift())].tolist()
    if len(starts) >= 2:
        ax.set_xticks(
            starts, [f"{dates[i] // 10000}/{dates[i] // 100 % 100:02d}" for i in starts]
        )
    else:
        step = max(len(dates) // 5, 1)
        ticks = list(range(0, len(dates), step))
        ax.set_xticks(
            ticks, [f"{dates[i] // 100 % 100}/{dates[i] % 100}" for i in ticks]
        )


def draw_score_monitor(
    ic: pd.Series,
    tc: pd.Series,
    period_from_ymd: int,
    period_to_ymd: int,
    *,
    title: str,
    rebalance: pd.Series | None = None,
    history_from_ymd: int | None = None,
    ma_window: int = MA_WINDOW,
    figsize: tuple[float, float] = FIGSIZE,
) -> Figure:
    """1 種類のスコアの IC、TC、リバランス相関 (任意) を 1 枚の図にする。

    ic, tc, rebalance は index が YYYYMMDD の Series。日付は 3 つの和集合にそろえる。
    period_from_ymd から period_to_ymd を対象期間として網掛けする。
    表示は history_from_ymd (省略時はデータの先頭) から period_to_ymd まで。
    IC の移動平均は、値がある日の直近 ma_window 日の平均とする。
    """
    if period_from_ymd > period_to_ymd:
        raise ValueError(
            f"period_from_ymd が period_to_ymd より後です: {period_from_ymd}-{period_to_ymd}"
        )
    if history_from_ymd is not None and history_from_ymd > period_from_ymd:
        raise ValueError(
            f"history_from_ymd が period_from_ymd より後です: "
            f"{history_from_ymd} > {period_from_ymd}"
        )

    panels = {"ic": ic, "tc": tc}
    if rebalance is not None:
        panels["rebalance"] = rebalance
    dates = pd.Index(sorted(set().union(*(s.dropna().index for s in panels.values()))))
    dates = dates[dates <= period_to_ymd]
    if history_from_ymd is not None:
        dates = dates[dates >= history_from_ymd]
    in_period = np.asarray(dates >= period_from_ymd)
    if not in_period.any():
        raise ValueError(f"対象期間に値がありません: {period_from_ymd}-{period_to_ymd}")
    period_dates = dates[in_period]
    x = np.arange(len(dates))
    start = int(np.argmax(in_period))

    width, height = figsize
    fig = Figure(figsize=(width, height), facecolor=BG)
    fig.text(
        0.02,
        1 - 0.28 / height,
        f"Period {format_ymd(period_dates[0])} – {format_ymd(period_dates[-1])} "
        f"({len(period_dates)} days)  |  History from {format_ymd(dates[0])}",
        color=MUTED,
        fontsize=10,
        va="center",
    )
    fig.text(
        0.02,
        1 - 0.72 / height,
        title,
        color=ACCENT,
        fontsize=12,
        fontweight="bold",
        va="center",
    )
    fig.text(
        0.98,
        1 - 0.72 / height,
        "Pearson correlation",
        color=MUTED,
        fontsize=9,
        ha="right",
        va="center",
    )
    rule_y = 1 - 0.92 / height
    fig.add_artist(
        Line2D(
            [0.02, 0.98],
            [rule_y, rule_y],
            color=ACCENT,
            lw=0.8,
            transform=fig.transFigure,
        )
    )

    ratios = [2.2, 1.3] + ([1.3] if rebalance is not None else [])
    grid = fig.add_gridspec(
        len(ratios),
        1,
        height_ratios=ratios,
        left=0.06,
        right=0.98
        - LABEL_MARGIN / width,  # 右端の値のラベルが図からはみ出さないようにする
        top=1 - 1.35 / height,
        bottom=0.55 / height,
        hspace=0.55,
    )
    axes = [fig.add_subplot(grid[0])]
    axes += [fig.add_subplot(grid[i], sharex=axes[0]) for i in range(1, len(ratios))]
    for ax in axes:
        _style_axes(ax)
        ax.axvspan(start - 0.5, x[-1] + 0.5, color=BAND, lw=0, zorder=0)
        ax.set_xlim(-0.6, len(dates) - 0.4)

    # IC: 日次の棒と移動平均
    ax = axes[0]
    ic_values = ic.reindex(dates).astype(float)
    _signed_bars(ax, x, ic_values, in_period)
    moving = ic_values.dropna().rolling(ma_window, min_periods=ma_window).mean()
    moving = moving.reindex(dates)
    ax.plot(x, moving.to_numpy(), color=ACCENT, linewidth=1.6, zorder=3)
    # 棒の間隔がラベルの幅より広ければ対象期間の全日、狭ければ最新日だけに値を書く
    labeled = np.flatnonzero(in_period & ic_values.notna().to_numpy())
    bar_spacing = (grid.right - grid.left) * width / len(dates)
    if bar_spacing < LABEL_WIDTH:
        labeled = labeled[-1:]
    for i in labeled:
        _value_label(ax, x[i], ic_values.iloc[i], f"{ic_values.iloc[i]:+.2f}")
    _set_ylim_with_zero(ax, ic_values.dropna())
    last_ma = moving.dropna()
    _panel_title(
        ax,
        f"IC  (bars: daily, line: {ma_window}-day mean)",
        f"Period mean {ic_values[in_period].mean():+.3f}   |   "
        f"Latest {ma_window}-day mean "
        f"{(last_ma.iloc[-1] if len(last_ma) else np.nan):+.3f}   |   "
        f"Mean since {format_ymd(dates[0])} {ic_values.mean():+.3f}",
    )

    # TC: 日次の線。対象期間の最初と最後に値を書く
    ax = axes[1]
    tc_values = tc.reindex(dates).astype(float)
    valid = tc_values.notna().to_numpy()
    if valid.any():
        plot_signed(ax, x[valid], tc_values.to_numpy()[valid], 0.0, 1.6)
        marks = np.flatnonzero(valid & in_period)
        for i, ha in _edge_marks(marks):
            value = tc_values.iloc[i]
            ax.scatter(
                [x[i]],
                [value],
                marker="D",
                s=22,
                zorder=4,
                color=UP if value >= 0 else DN,
            )
            _value_label(ax, x[i], value, f"{value:+.3f}", ha)
        _set_ylim_with_zero(ax, tc_values.dropna())
        period_tc = tc_values[in_period].dropna()
        right = (
            f"Period {period_tc.iloc[0]:+.3f} → {period_tc.iloc[-1]:+.3f}"
            if len(period_tc)
            else "No value in the period"
        )
    else:
        right = "No value"
    _panel_title(ax, "TC  (active weight vs score)", right)

    # リバランス相関: 日次の棒。対象期間の最初と最後に値を書く
    if rebalance is not None:
        ax = axes[2]
        reb_values = rebalance.reindex(dates).astype(float)
        _signed_bars(ax, x, reb_values, in_period)
        marks = np.flatnonzero(in_period & reb_values.notna().to_numpy())
        for i, ha in _edge_marks(marks):
            value = reb_values.iloc[i]
            _value_label(ax, x[i], value, f"{value:.3f}", ha)
        if reb_values.notna().any():
            _set_ylim_with_zero(ax, reb_values.dropna())
        reb_date = rebalance.dropna().index.min()
        _panel_title(
            ax,
            f"Rebalance correlation  (score on {format_ymd(int(reb_date))} vs each day)",
            f"Latest {reb_values.dropna().iloc[-1]:.3f}"
            if reb_values.notna().any()
            else "",
        )

    for ax in axes[:-1]:
        ax.tick_params(labelbottom=False)
    _date_ticks(axes[-1], dates)
    return fig
