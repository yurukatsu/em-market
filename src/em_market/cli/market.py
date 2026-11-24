"""1. 市況データの取得: LSEG から週次レポート用のデータを取得し、data/processed/<output_ymd>/market/ に保存する。

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
    config_option,
    echo,
    load_config,
    to_date,
    today,
)
from em_market.paths import processed_dir


class MarketConfig(CliConfig):
    """configs/cli/market.yaml の内容 (説明は yaml 側のコメントを参照)。"""

    output_ymd: int | None = None
    from_ymd: int | None = None
    to_ymd: int | None = None


def main(
    config: Annotated[Path, config_option("market")] = CLI_CONFIG_DIR / "market.yaml",
) -> None:
    """LSEG から市況データを取得し、data/processed/<output_ymd>/market/ に保存します。"""
    from em_market.market.client import LSEGClient
    from em_market.reports.weekly import WeeklyReport, WeeklyReportConfig

    cfg = load_config(MarketConfig, config)
    weekly = WeeklyReportConfig.load()
    output_date = to_date(cfg.output_ymd, today())
    end = to_date(cfg.to_ymd, output_date - pd.Timedelta(days=1))
    start = to_date(
        cfg.from_ymd,
        end - pd.DateOffset(months=weekly.commodity_months) - pd.Timedelta(days=14),
    )
    check_range(start, end)
    echo(f"時系列 {start:%Y%m%d} ～ {end:%Y%m%d}｜保存先の日付 {output_date:%Y%m%d}")

    # 決算日・経済指標カレンダーの基準日は output_ymd。BM は data/raw/bm の output_ymd 以前の最新日
    report = WeeklyReport(base_date=output_date, config=weekly, log=echo)
    echo(f"BM: data/raw/bm/{report.bm.attrs['date']}.csv ({len(report.bm)} 銘柄)")
    with LSEGClient() as client:
        data = report.fetch(client, start=start, end=end)

    output_dir = processed_dir(output_date, "market")
    paths = data.save(output_dir)
    meta = {"from_ymd": int(f"{start:%Y%m%d}"), "to_ymd": int(f"{end:%Y%m%d}")}
    (output_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    typer.echo(f"Saved {len(paths) + 1} files to {output_dir}")


if __name__ == "__main__":
    typer.run(main)
