"""1. 市況: LSEG から週次レポート用のデータを取得して図と表を作り、data/processed/<output_ymd>/market/ に保存する。

    data/     取得したデータ (CSV) と取得期間 (meta.json)
    figures/  図 (PNG) と表 (CSV)

設定: configs/cli/market.yaml
    uv run em-market market
    uv run em-market market --config configs/cli/market.yaml
    uv run python -m em_market.cli.market
"""

import json
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from em_market.cli._common import (
    CLI_CONFIG_DIR,
    CliConfig,
    check_range,
    clear_files,
    config_option,
    echo,
    highlight_period,
    load_config,
    to_date,
    today,
)
from em_market.paths import processed_dir


class MarketConfig(CliConfig):
    """configs/cli/market.yaml の内容 (説明は yaml 側のコメントを参照)。"""

    output_ymd: int | None = None
    fetch: bool = True
    from_ymd: int | None = None
    to_ymd: int | None = None
    period_from_ymd: int | None = None
    period_to_ymd: int | None = None


def main(
    config: Annotated[Path, config_option("market")] = CLI_CONFIG_DIR / "market.yaml",
) -> None:
    """LSEG から市況データを取得して図と表を作り、data/processed/<output_ymd>/market/ に保存します。"""
    import matplotlib

    matplotlib.use("Agg")  # 画面のない環境 (EC2 など) でも描画できるように

    from em_market.reports.weekly import WeeklyData, WeeklyReport, WeeklyReportConfig

    cfg = load_config(MarketConfig, config)
    weekly = WeeklyReportConfig.load()
    output_date = to_date(cfg.output_ymd, today())
    period_from, period_to = highlight_period(
        output_date, cfg.period_from_ymd, cfg.period_to_ymd
    )
    data_dir = processed_dir(output_date, "market", "data")
    figure_dir = processed_dir(output_date, "market", "figures")

    # 決算日・経済指標カレンダーの基準日は output_ymd。BM は data/raw/bm の output_ymd 以前の最新日
    # リターンは強調する期間の前日の値を基準にする
    report = WeeklyReport(
        base_date=output_date,
        config=weekly,
        output_dir=figure_dir,
        log=echo,
        return_period=(period_from - pd.Timedelta(days=1), period_to),
    )
    echo(f"BM: data/raw/bm/{report.bm.attrs['date']}.csv ({len(report.bm)} 銘柄)")

    if cfg.fetch:
        from em_market.market.client import LSEGClient

        end = to_date(cfg.to_ymd, output_date - pd.Timedelta(days=1))
        start = to_date(
            cfg.from_ymd,
            end - pd.DateOffset(months=weekly.commodity_months) - pd.Timedelta(days=14),
        )
        check_range(start, end)
        echo(f"時系列 {start:%Y%m%d} ～ {end:%Y%m%d} を取得")
        with LSEGClient() as client:
            data = report.fetch(client, start=start, end=end)
        paths = data.save(data_dir)
        meta = {"from_ymd": int(f"{start:%Y%m%d}"), "to_ymd": int(f"{end:%Y%m%d}")}
        (data_dir / "meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        typer.echo(f"Saved {len(paths) + 1} files to {data_dir}")
    else:
        if not data_dir.exists():
            typer.echo(
                f"{data_dir} がありません。fetch: true で取得してください", err=True
            )
            raise typer.Exit(1)
        echo(f"取得済みのデータを使います: {data_dir}")
        data = WeeklyData.load(data_dir)

    echo(f"強調する期間 {period_from:%Y%m%d} ～ {period_to:%Y%m%d}")
    clear_files(figure_dir)
    outputs = report.run(data)
    typer.echo(f"Saved {len(outputs)} files to {figure_dir}")


if __name__ == "__main__":
    typer.run(main)
