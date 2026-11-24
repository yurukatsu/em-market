"""図に共通の配色、大きさ、フォント、描画の補助関数。

import すると、同梱の日本語フォント (Noto Sans JP, SIL OFL) を登録し、
matplotlib の既定の文字色・背景色をこの配色に設定する。
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection

BG = "#E5E5E5"  # 背景 (グレー)。市況の図
FACTOR_BG = "#FFFFFF"  # ファクターの図の背景 (白)
ACCENT = "#3C3C3C"  # 強調色 (濃いグレー): タイトル、見出し、区切り線
BAND = "#C4C4C4"  # 対象期間の網掛け
STRIPE = "#D9D9D9"  # 表の縞、控えめな強調
UP, DN = "#1F5AA6", "#A33A44"  # プラス (青)、マイナス (えんじ色)
INK, MUTED, SUBTLE = "#1A1A1A", "#5F5F5F", "#7A7A7A"  # 文字: 本文、補足、目盛りなど
GRID, ZERO, ROW_RULE = "#9A9A9A", "#6E6E6E", "#D0D0D0"

# 図の大きさ (インチ) と PNG の解像度。16:9 のスライド全面 (13.333 × 7.5 インチ)
FIGSIZE: tuple[float, float] = (13.333, 7.5)
DPI: int = 200

for _font in (Path(__file__).resolve().parents[1] / "fonts").glob("*.ttf"):
    font_manager.fontManager.addfont(_font)

plt.rcParams.update(
    {
        "font.family": "Noto Sans JP",
        "font.size": 12,
        "text.color": INK,
        "axes.labelcolor": MUTED,
        "axes.edgecolor": ROW_RULE,
        "axes.facecolor": BG,
        "figure.facecolor": BG,
        "savefig.facecolor": BG,
        "xtick.color": SUBTLE,
        "ytick.color": SUBTLE,
    }
)


def format_ymd(ymd: int) -> str:
    return f"{ymd // 10000}/{ymd // 100 % 100:02d}/{ymd % 100:02d}"


def plot_signed(
    ax: Axes, x: np.ndarray, y: np.ndarray, base: float, linewidth: float
) -> None:
    """base より上の区間をプラスの色、下の区間をマイナスの色で線を描き、終点に点を打つ。

    base をまたぐ区間は交点で分割する。
    """
    xs, ys = [float(x[0])], [float(y[0])]
    for i in range(1, len(x)):
        y0, y1 = y[i - 1], y[i]
        if (y0 - base) * (y1 - base) < 0:
            t = (base - y0) / (y1 - y0)
            xs.append(float(x[i - 1] + t * (x[i] - x[i - 1])))
            ys.append(base)
        xs.append(float(x[i]))
        ys.append(float(y[i]))
    xs_arr, ys_arr = np.array(xs), np.array(ys)

    if len(xs_arr) > 1:
        starts = np.column_stack([xs_arr[:-1], ys_arr[:-1]])
        ends = np.column_stack([xs_arr[1:], ys_arr[1:]])
        above = (ys_arr[:-1] + ys_arr[1:]) / 2 >= base
        ax.add_collection(
            LineCollection(
                np.stack([starts, ends], axis=1),
                colors=np.where(above, UP, DN),
                linewidths=linewidth,
                capstyle="round",
            )
        )
    ax.scatter([x[-1]], [y[-1]], color=UP if y[-1] >= base else DN, s=9, zorder=3)
