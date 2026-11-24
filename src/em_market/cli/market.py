"""1. 市況データの作成: LSEG から週次レポート用のデータを取得し、data/processed/<日付>/market/ に保存する。

uv run em-market market --from-date 2026-07-01 --to-date 2026-10-20 --output-date 2026-10-21
uv run python -m em_market.cli.market --output-date 2026-10-21
"""

import json
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from em_market.cli._common import OutputDateOption, echo, parse_date, parse_range
from em_market.paths import CONFIG_DIR, processed_dir


def main(
    from_date: Annotated[
        str,
        typer.Option(
            "--from-date",
            help="時系列 (指数・株価・利回り・コモディティ) の取得開始日。"
            "省略時は --to-date の commodity_months か月と 2 週間前",
        ),
    ] = "",
    to_date: Annotated[
        str,
        typer.Option(
            "--to-date", help="時系列の取得終了日。省略時は --output-date の前日"
        ),
    ] = "",
    output_date: OutputDateOption = "",
    config_path: Annotated[
        Path,
        typer.Option(
            "--config", "-c", help="週次レポートの設定", exists=True, dir_okay=False
        ),
    ] = CONFIG_DIR / "weekly_report.yaml",
) -> None:
    """LSEG から市況データを取得し、data/processed/<--output-date>/market/ に保存します。

    決算日と経済指標は取得した時点の予定を保存します (経済指標の値は --output-date まで)。
    """
    from em_market.market.client import LSEGClient
    from em_market.reports.weekly import WeeklyReport, WeeklyReportConfig

    config = WeeklyReportConfig.load(config_path)
    output = parse_date(output_date)
    start, end = parse_range(
        from_date,
        to_date,
        output,
        lambda to: (
            to - pd.DateOffset(months=config.commodity_months) - pd.Timedelta(days=14)
        ),
    )
    echo(f"時系列 {start:%Y-%m-%d} ～ {end:%Y-%m-%d}｜保存先の日付 {output:%Y-%m-%d}")

    report = WeeklyReport(base_date=output, config=config, log=echo)
    with LSEGClient() as client:
        data = report.fetch(client, start=start, end=end)

    output_dir = processed_dir(output, "market")
    paths = data.save(output_dir)
    meta = {"from_date": f"{start:%Y-%m-%d}", "to_date": f"{end:%Y-%m-%d}"}
    (output_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    typer.echo(f"Saved {len(paths) + 1} files to {output_dir}")


if __name__ == "__main__":
    typer.run(main)
