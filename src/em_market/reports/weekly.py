"""週次レポート（市況）: LSEG から取得したデータから、PNG（PowerPoint 貼り付け用）と CSV を出力する。

取得と作図は別々の notebook で実行する:
    notebooks/01_market_data.ipynb   # 取得 → data/processed/<日付>/market/
    notebooks/04_report.ipynb        # 作図 → data/processed/<日付>/report/
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import yaml
from matplotlib.figure import Figure
from pydantic import BaseModel

from em_market.dates import weekly_period
from em_market.market.client import LSEGClient
from em_market.market.earnings import (
    DATE_COLUMNS,
    earnings_in_window,
    fetch_earnings_dates,
    load_benchmark,
    next_earnings_counts,
)
from em_market.market.economics import (
    fetch_release_calendar,
    load_indicators,
    releases_in_window,
)
from em_market.market.rates import curve_asof, rates_summary
from em_market.market.universe import load_universe
from em_market.paths import CONFIG_DIR, processed_dir
from em_market.viz.market import (
    period_returns,
    plot_dual_axis,
    plot_earnings_counts,
    plot_earnings_table,
    plot_econ_calendar,
    plot_period_chart,
    plot_rates_table,
    plot_top_by_date,
    plot_treemap,
    plot_yield_curve,
    save_png,
    short_name,
)


class WeeklyReportConfig(BaseModel):
    """configs/weekly_report.yaml の内容（各項目の説明は yaml 側のコメントを参照）。"""

    lookback_days: int = 7
    data_lag_days: int = 1
    country_field: str = "TR.PriceClose(Curn=USD)"
    sector_field: str = "TR.PriceClose(Curn=USD)"
    stock_field: str = "TR.PriceClose(Curn=USD)"
    yield_field: str = "MID_YLD_1"
    bm_name: str = "BM"
    benchmark: str = "MSCI EM"
    earnings_days: int = 7
    season_end: str | None = None
    min_weight: float = 0.0
    min_cap: float = 0
    top_n: int = 3
    commodity_months: int = 3
    econ_days: int = 7
    treemap_clip: float = 0.05
    table_rows_per_page: int = 18

    @classmethod
    def load(
        cls, path: Path = CONFIG_DIR / "weekly_report.yaml"
    ) -> "WeeklyReportConfig":
        with path.open("r", encoding="utf-8") as f:
            return cls.model_validate(yaml.safe_load(f) or {})


_PRICE_FRAMES = (
    "stock_prices",
    "us_yields",
    "short_yields",
    "long_yields",
    "commodity_prices",
)
_ECON_DATE_COLUMNS = ("next_release", "previous_release", "last_period", "prev_period")


@dataclass
class WeeklyData:
    """LSEG から取得したデータ一式。save / load で CSV に保存・復元する。"""

    index_prices: dict[str, pd.DataFrame]
    earnings_dates: pd.DataFrame
    stock_prices: pd.DataFrame
    us_yields: pd.DataFrame
    short_yields: pd.DataFrame
    long_yields: pd.DataFrame
    commodity_prices: pd.DataFrame
    econ_calendar: pd.DataFrame

    def save(self, directory: Path) -> list[Path]:
        """directory に CSV で保存し、保存したファイルのパスを返す。"""
        directory.mkdir(parents=True, exist_ok=True)
        frames = {f"index_prices_{g}": df for g, df in self.index_prices.items()}
        frames |= {name: getattr(self, name) for name in _PRICE_FRAMES}
        paths = []
        for name, df in frames.items():  # 日付が index の時系列
            paths.append(directory / f"{name}.csv")
            df.to_csv(paths[-1], encoding="utf-8-sig")
        for name in ("earnings_dates", "econ_calendar"):  # 表
            paths.append(directory / f"{name}.csv")
            getattr(self, name).to_csv(paths[-1], index=False, encoding="utf-8-sig")
        return paths

    @classmethod
    def load(cls, directory: Path) -> "WeeklyData":
        """save で保存した CSV から復元する。"""

        def series(path: Path) -> pd.DataFrame:
            df = pd.read_csv(path, index_col=0, encoding="utf-8-sig")
            df.index = pd.to_datetime(df.index)
            return df

        index_prices = {
            path.stem.removeprefix("index_prices_"): series(path)
            for path in sorted(directory.glob("index_prices_*.csv"))
        }
        earnings = pd.read_csv(
            directory / "earnings_dates.csv",
            dtype={"sedol": str, "ric": str},
            encoding="utf-8-sig",
        )
        for col in DATE_COLUMNS:
            if col in earnings:
                earnings[col] = pd.to_datetime(earnings[col])
        econ = pd.read_csv(
            directory / "econ_calendar.csv", dtype={"unit": str}, encoding="utf-8-sig"
        )
        econ["unit"] = econ["unit"].fillna("")
        for col in _ECON_DATE_COLUMNS:
            econ[col] = pd.to_datetime(econ[col])
        return cls(
            index_prices=index_prices,
            earnings_dates=earnings,
            econ_calendar=econ,
            **{name: series(directory / f"{name}.csv") for name in _PRICE_FRAMES},
        )


@dataclass
class WeeklyReport:
    """週次レポート。

    return_period: リターンの期間 (起点, 終点)。起点の値を基準に終点までのリターンを計算する。
        省略時は基準日の data_lag_days 日前を終点、その lookback_days 日前を起点とする。
    """

    base_date: pd.Timestamp
    config: WeeklyReportConfig = field(default_factory=WeeklyReportConfig)
    output_dir: Path | None = None
    log: Callable[[str], None] = print
    return_period: tuple[pd.Timestamp, pd.Timestamp] | None = None

    def __post_init__(self) -> None:
        self.base_date = pd.Timestamp(self.base_date).normalize()
        self.output_dir = self.output_dir or processed_dir(self.base_date, "report")
        cfg = self.config
        # 価格系はデータ基準日（= 基準日の data_lag_days 日前）までの最新値を使う
        # 水曜実行なら前日の火曜。カレンダー系は基準日以降
        if self.return_period is None:
            self.return_start, self.return_end = weekly_period(
                self.base_date, cfg.lookback_days, cfg.data_lag_days
            )
        else:
            self.return_start, self.return_end = (
                pd.Timestamp(day).normalize() for day in self.return_period
            )
        self.earnings_end = self.base_date + pd.Timedelta(days=cfg.earnings_days - 1)
        self.period_label = f"{self.return_start:%Y/%m/%d}～{self.return_end:%Y/%m/%d}"
        self.universe = load_universe()
        # BM は data/raw/bm のうち基準日以前で最も新しい日のもの
        self.bm = load_benchmark(as_of=self.base_date)
        self.outputs: list[Path] = []

    # ---- 出力 ----------------------------------------------------------------

    def _png(self, fig: Figure, name: str) -> None:
        self.outputs.append(save_png(fig, self.output_dir / name))
        plt.close(fig)

    def _csv(self, df: pd.DataFrame, name: str, index: bool = False) -> None:
        path = self.output_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=index, encoding="utf-8-sig")
        self.outputs.append(path)

    def _pages(self, figs: list[Figure], prefix: str) -> None:
        for n, fig in enumerate(figs, start=1):
            self._png(fig, f"{prefix}_{n:02d}.png")

    # ---- データ取得 ------------------------------------------------------------

    def fetch(
        self,
        client: LSEGClient,
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> WeeklyData:
        """LSEG からデータを取得する。

        時系列は start から end まで取得する。省略時は、指数・株価・利回りは起点の
        2 週間前から、コモディティは commodity_months か月前から、終点までとする。
        決算日と経済指標は取得した時点の予定を取る。
        """
        cfg, u = self.config, self.universe
        end = pd.Timestamp(end) if end is not None else self.return_end
        # 起点の直前営業日を拾えるよう、期間の頭は2週間前倒しで取得する
        default_start = self.return_start - pd.Timedelta(days=14)
        price_range = {
            "start": f"{pd.Timestamp(start) if start is not None else default_start:%Y-%m-%d}",
            "end": f"{end:%Y-%m-%d}",
        }
        commodity_start = (
            pd.Timestamp(start)
            if start is not None
            else end - pd.DateOffset(months=cfg.commodity_months) - pd.Timedelta(days=7)
        )

        self.log("指数")
        index_prices = {
            group: client.get_instrument_history(
                u[group], default_field=field, **price_range
            )
            for group, field in [
                ("countries", cfg.country_field),
                ("sectors", cfg.sector_field),
            ]
        }
        self.log("決算日（BM 構成銘柄）")
        dates = fetch_earnings_dates(client, self.bm["sedol"].tolist())
        self.log("BM 構成銘柄の株価")
        stock_prices = client.get_history_chunked(
            dates["ric"].dropna().unique().tolist(), cfg.stock_field, **price_range
        )
        self.log("国債利回り")
        us_yields = client.get_instrument_history(
            u["us_treasury"], default_field=cfg.yield_field, **price_range
        )
        short_yields = client.get_instrument_history(
            u["govt_short"], default_field=cfg.yield_field, **price_range
        )
        long_yields = client.get_instrument_history(
            u["govt_10y"], default_field=cfg.yield_field, **price_range
        )
        self.log("コモディティ")
        commodity_prices = client.get_instrument_history(
            u["commodities"],
            start=f"{commodity_start:%Y-%m-%d}",
            end=f"{end:%Y-%m-%d}",
        )
        self.log("経済指標カレンダー")
        econ_calendar = fetch_release_calendar(
            client, load_indicators(), self.base_date
        )

        return WeeklyData(
            index_prices=index_prices,
            earnings_dates=dates,
            stock_prices=stock_prices,
            us_yields=us_yields,
            short_yields=short_yields,
            long_yields=long_yields,
            commodity_prices=commodity_prices,
            econ_calendar=econ_calendar,
        )

    # ---- 各図表 ----------------------------------------------------------------

    def index_returns(self, data: WeeklyData) -> None:
        cfg = self.config
        country = period_returns(
            data.index_prices["countries"], self.return_start, self.return_end
        )
        sector = period_returns(
            data.index_prices["sectors"], self.return_start, self.return_end
        )
        usd = "USD" in cfg.country_field
        country_prices = data.index_prices["countries"]
        if usd:
            # 通貨をそろえたときだけ、各国の図にもベンチマーク (USD 建て) の行を加える
            country_prices = pd.concat(
                [data.index_prices["sectors"][[cfg.benchmark]], country_prices], axis=1
            )
        fig = plot_period_chart(
            country_prices,
            self.return_start,
            self.return_end,
            title="各国株式インデックス リターン",
            note=f"{'USD' if usd else '現地通貨'}建て、期間の累積リターン (%)",
            subtitle=self.period_label,
            benchmark=cfg.benchmark if usd else None,
            name_header="国",
        )
        self._png(fig, "01_country_returns.png")

        fig = plot_period_chart(
            data.index_prices["sectors"],
            self.return_start,
            self.return_end,
            title=f"{cfg.benchmark} セクター別リターン",
            note="USD 建て、期間の累積リターン (%)",
            subtitle=self.period_label,
            benchmark=cfg.benchmark,
            name_header="セクター",
        )
        self._png(fig, "02_sector_returns.png")
        self._csv(
            pd.concat({"country": country, "sector": sector}),
            "01_02_index_returns.csv",
            True,
        )

    def earnings(self, data: WeeklyData) -> None:
        cfg, dates, bm = self.config, data.earnings_dates, self.bm

        counts = next_earnings_counts(dates, bm, self.base_date, cfg.season_end)
        this_week = counts.loc[self.base_date : self.earnings_end, "count"].sum()
        fig = plot_earnings_counts(
            counts,
            title=f"{cfg.bm_name} 構成銘柄の決算発表予定件数",
            subtitle=f"{counts.index.min():%Y/%m/%d}～{counts.index.max():%Y/%m/%d}｜日次｜"
            f"今週 {this_week} 件 / 期間計 {counts['count'].sum()} 件",
            highlight=(self.base_date, self.earnings_end),
        )
        self._png(fig, "03_earnings_counts.png")

        calendar = earnings_in_window(dates, bm, self.base_date, days=cfg.earnings_days)
        calendar = calendar[calendar["weight"] >= cfg.min_weight]
        # cap は BM に時価総額があるときだけ使える (data/raw/bm にはない)
        use_cap = cfg.min_cap > 0 and calendar["cap"].notna().any()
        if cfg.min_cap > 0 and not use_cap:
            self.log("BM に時価総額 (cap) がないので min_cap の絞り込みはしません")
        if use_cap:
            calendar = calendar[calendar["cap"] >= cfg.min_cap]
        self._csv(calendar, "04_earnings_calendar.csv")
        filters = "".join(
            [f"｜weight ≥ {cfg.min_weight:.2%}"] * (cfg.min_weight > 0)
            + [f"｜cap ≥ {cfg.min_cap / 1e9:,.1f}bn"] * use_cap
        )
        window = f"{self.base_date:%Y/%m/%d}～{self.earnings_end:%m/%d}"
        figs = plot_earnings_table(
            calendar,
            title="今週の決算発表銘柄",
            subtitle=f"{window}｜{len(calendar)}社・weight 計 {calendar['weight'].sum():.1%}"
            + filters,
            rows_per_page=cfg.table_rows_per_page,
        )
        self._pages(figs, "04_earnings_calendar")

        top = calendar.groupby("date", group_keys=False).apply(
            lambda g: g.nlargest(cfg.top_n, "weight")
        )
        self._csv(top, "05_earnings_top_by_date.csv")
        fig = plot_top_by_date(
            calendar,
            title=f"今週の決算発表銘柄（日付別 weight 上位{cfg.top_n}社）",
            subtitle=f"{window}｜上位{cfg.top_n}社の weight 計 {top['weight'].sum():.1%}"
            f"（全 {len(calendar)} 社 {calendar['weight'].sum():.1%}）" + filters,
            top_n=cfg.top_n,
        )
        self._png(fig, "05_earnings_top_by_date.png")

    def us_yield_curve(self, data: WeeklyData) -> None:
        base = curve_asof(data.us_yields, self.return_end)
        prev = curve_asof(data.us_yields, self.return_start)
        fig = plot_yield_curve(
            base,
            prev,
            title="米国債イールドカーブ",
            subtitle=f"{base.name:%Y/%m/%d} vs {prev.name:%Y/%m/%d}｜"
            "仲値利回り｜下段：変化幅（bp）",
        )
        self._png(fig, "06_us_yield_curve.png")

    def commodities(self, data: WeeklyData) -> None:
        cfg = self.config
        instruments = self.universe["commodities"]
        wti, gold = (i.name for i in instruments)
        prices = data.commodity_prices
        returns = period_returns(prices, self.return_start, self.return_end)
        window = prices.loc[
            self.return_end
            - pd.DateOffset(months=cfg.commodity_months) : self.return_end
        ]
        fig = plot_dual_axis(
            window,
            left=wti,
            right=gold,
            title="コモディティ価格（WTI原油・金）",
            subtitle=f"{window.index.min():%Y/%m/%d}～{window.index.max():%Y/%m/%d}｜"
            "左軸：WTI原油（NYMEX 先物期近・決済値）、右軸：金（スポット）",
            units={i.name: i.unit for i in instruments if i.unit},
            end_labels={
                name: f"{r['end_value']:,.2f}（週間 {r['return']:+.1%}）"
                for name, r in returns.iterrows()
            },
            highlight=(self.return_start, self.return_end),
        )
        self._png(fig, "07_commodities.png")

    def em_rates(self, data: WeeklyData) -> None:
        govt_short = self.universe["govt_short"]
        rates = rates_summary(
            data.short_yields,
            data.long_yields,
            govt_short,
            self.return_end,
            self.return_start,
        )
        substituted = [i.name for i in govt_short if i.tenor and i.tenor != "2Y"]
        no_short = [c for c in rates.index if pd.isna(rates.loc[c, "short"])]
        notes = [f"※ 2年債がないため3年債で代用：{'・'.join(substituted)}"] * bool(
            substituted
        )
        notes += [f"短期側なし：{'・'.join(no_short)}"] * bool(no_short)
        notes += ["UAE・サウジアラビアはジェネリックの現地通貨建て国債がないため対象外"]
        fig = plot_rates_table(
            rates,
            title="新興国 国債利回り",
            subtitle=f"{rates.attrs['base_date']:%Y/%m/%d} 時点｜"
            f"変化は {rates.attrs['compare_date']:%Y/%m/%d} 比｜仲値利回り・現地通貨建て",
            reference_rows=["米国"],
            notes=notes,
        )
        self._png(fig, "08_em_rates.png")
        self._csv(rates, "08_em_rates.csv", index=True)

    def econ_calendar(self, data: WeeklyData) -> None:
        cfg = self.config
        events = releases_in_window(
            data.econ_calendar, self.base_date, days=cfg.econ_days
        )
        end = self.base_date + pd.Timedelta(days=cfg.econ_days - 1)
        self._csv(events, "09_econ_calendar.csv")
        figs = plot_econ_calendar(
            events,
            title="今週の主要経済指標",
            subtitle=f"{self.base_date:%Y/%m/%d}～{end:%m/%d}｜{len(events)}件｜"
            "前回値はロイター調査対象系列の直近値",
            rows_per_page=cfg.table_rows_per_page,
        )
        self._pages(figs, "09_econ_calendar")

    def treemaps(self, data: WeeklyData) -> None:
        cfg = self.config
        returns = period_returns(data.stock_prices, self.return_start, self.return_end)[
            "return"
        ]
        stocks = data.earnings_dates[["sedol", "ric", "country", "sector"]].merge(
            self.bm[["sedol", "name", "weight"]], on="sedol"
        )
        stocks["return"] = stocks["ric"].map(returns)
        stocks["label"] = stocks["name"].map(short_name)
        self._csv(stocks, "10_stock_returns.csv")

        currency = "USD" if "USD" in cfg.stock_field else "現地通貨"
        subtitle = f"{self.period_label}｜{currency}建て｜面積 = weight、見出し = weight 加重リターン"
        for suffix, groups, label in [
            ("country", ["country"], "国別"),
            ("sector", ["sector"], "セクター別"),
            ("country_sector", ["country", "sector"], "国 × セクター"),
        ]:
            fig = plot_treemap(
                stocks,
                groups,
                title=f"{cfg.bm_name} 構成銘柄 1週間リターン（{label}）",
                subtitle=subtitle,
                clip=cfg.treemap_clip,
            )
            self._png(fig, f"10_treemap_{suffix}.png")

    # ---- 実行 ------------------------------------------------------------------

    SECTIONS = (
        "index_returns",
        "earnings",
        "us_yield_curve",
        "commodities",
        "em_rates",
        "econ_calendar",
        "treemaps",
    )

    def run(self, data: WeeklyData) -> list[Path]:
        """取得済みのデータから全図表を出力する。出力したファイルのパスを返す。"""
        self.log(
            f"基準日 {self.base_date:%Y-%m-%d}（カレンダーはこの日以降）｜"
            f"価格データ {self.period_label}"
        )
        for name in self.SECTIONS:
            self.log(f"作図: {name}")
            getattr(self, name)(data)
        return self.outputs
