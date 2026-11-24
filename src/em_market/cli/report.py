"""4. レポートの更新: 市況データとファクターの計算結果から図とパワポを作り、
data/processed/<日付>/report/ に保存する。対象期間 (強調する週) は日付から決める。

uv run em-market report --date 2026-11-25
uv run python -m em_market.cli.report --date 2026-11-25
"""

from pathlib import Path
from typing import Annotated

import typer

from em_market.cli._common import BaseDateOption, echo, parse_date
from em_market.paths import CONFIG_DIR, processed_dir


def main(
    base_date: BaseDateOption = "",
    slides: Annotated[
        bool,
        typer.Option(help="市況の図をパワポのテンプレートに差し込んだファイルも作る"),
    ] = True,
    weekly_config: Annotated[
        Path,
        typer.Option(help="週次レポートの設定", exists=True, dir_okay=False),
    ] = CONFIG_DIR / "weekly_report.yaml",
    slides_config: Annotated[
        Path,
        typer.Option(help="パワポの差し込みの設定", exists=True, dir_okay=False),
    ] = CONFIG_DIR / "weekly_slides.yaml",
) -> None:
    """data/processed/<日付>/ の market と factor から、図 (PNG) とパワポを作り、同じ日付の report/ に保存します。

    片方しかない場合は、ある方だけ作ります。
    """
    import matplotlib

    matplotlib.use("Agg")  # 画面のない環境 (EC2 など) でも描画できるように

    from em_market.reports.factor import (
        FactorResults,
        draw_factor_figures,
        factor_period,
    )
    from em_market.reports.slides import SlidesConfig, build_slides
    from em_market.reports.weekly import WeeklyData, WeeklyReport, WeeklyReportConfig

    day = parse_date(base_date)
    weekly = WeeklyReportConfig.load(weekly_config)
    market_dir = processed_dir(day, "market")
    factor_dir = processed_dir(day, "factor")
    output_dir = processed_dir(day, "report")
    if not market_dir.exists() and not factor_dir.exists():
        typer.echo(
            f"{market_dir} と {factor_dir} がありません。"
            "先に em-market market / factor を実行してください",
            err=True,
        )
        raise typer.Exit(1)

    outputs = []
    if market_dir.exists():
        report = WeeklyReport(
            base_date=day, config=weekly, output_dir=output_dir, log=echo
        )
        outputs += report.run(WeeklyData.load(market_dir))
    else:
        echo(f"{market_dir} がないので市況の図は作りません")

    if factor_dir.exists():
        # 強調する週は市況のリターンと同じ (日付の data_lag_days 日前までの lookback_days 日)
        period_from, period_to = factor_period(
            day, weekly.lookback_days, weekly.data_lag_days
        )
        echo(f"ファクターの対象期間 {period_from} ～ {period_to}")
        outputs += draw_factor_figures(
            FactorResults.load(factor_dir), period_from, period_to, output_dir, log=echo
        )
    else:
        echo(f"{factor_dir} がないのでファクターの図は作りません")
    typer.echo(f"Saved {len(outputs)} files to {output_dir}")

    if slides and market_dir.exists():
        config = SlidesConfig.load(slides_config)
        if not config.template.exists():
            typer.echo(
                f"テンプレートがないのでパワポは作りません: {config.template}", err=True
            )
            return
        output = build_slides(
            output_dir,
            output_dir / config.output_name.format(date=day),
            config,
            log=echo,
        )
        typer.echo(f"Saved: {output}")


if __name__ == "__main__":
    typer.run(main)
