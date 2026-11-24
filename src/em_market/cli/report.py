"""4. レポートの作成: data/processed/<report_ymd>/ の market と factor から図・表・パワポを作り、
data/processed/<report_ymd>/report/ に保存する。

設定: configs/cli/report.yaml
    uv run em-market report
    uv run python -m em_market.cli.report
"""

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from em_market.cli._common import (
    CLI_CONFIG_DIR,
    CliConfig,
    config_option,
    echo,
    load_config,
    to_date,
    today,
)
from em_market.paths import processed_dir


class ReportConfig(CliConfig):
    """configs/cli/report.yaml の内容 (説明は yaml 側のコメントを参照)。"""

    report_ymd: int | None = None
    period_from_ymd: int | None = None
    period_to_ymd: int | None = None
    make_slides: bool = True


def main(
    config: Annotated[Path, config_option("report")] = CLI_CONFIG_DIR / "report.yaml",
) -> None:
    """market と factor から図 (PNG)・表 (CSV)・パワポを作り、data/processed/<report_ymd>/report/ に保存します。

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

    cfg = load_config(ReportConfig, config)
    report_date = to_date(cfg.report_ymd, today())
    weekly = WeeklyReportConfig.load()
    period_from, period_to = cfg.period_from_ymd, cfg.period_to_ymd
    if period_from is None or period_to is None:
        period_from, period_to = factor_period(
            report_date, weekly.lookback_days, weekly.data_lag_days
        )
    market_dir, factor_dir, output_dir = (
        processed_dir(report_date, kind) for kind in ("market", "factor", "report")
    )
    echo(f"対象期間 {period_from} ～ {period_to}｜保存先 {output_dir}")
    if not market_dir.exists() and not factor_dir.exists():
        typer.echo(
            f"{market_dir} と {factor_dir} がありません。"
            "先に em-market market / factor を実行してください",
            err=True,
        )
        raise typer.Exit(1)

    outputs: list[Path] = []
    if market_dir.exists():
        # リターンは対象期間の前日の値を基準にする
        report = WeeklyReport(
            base_date=report_date,
            config=weekly,
            output_dir=output_dir,
            log=echo,
            return_period=(
                pd.Timestamp(str(period_from)) - pd.Timedelta(days=1),
                pd.Timestamp(str(period_to)),
            ),
        )
        outputs += report.run(WeeklyData.load(market_dir))
    else:
        echo(f"{market_dir} がないので市況の図は作りません")

    if factor_dir.exists():
        outputs += draw_factor_figures(
            FactorResults.load(factor_dir), period_from, period_to, output_dir, log=echo
        )
    else:
        echo(f"{factor_dir} がないのでファクターの図は作りません")
    typer.echo(f"Saved {len(outputs)} files to {output_dir}")

    if not (cfg.make_slides and market_dir.exists()):
        return
    slides = SlidesConfig.load()
    if not slides.template.exists():
        typer.echo(
            f"テンプレートがないのでパワポは作りません: {slides.template}", err=True
        )
        return
    pptx = build_slides(
        output_dir,
        output_dir / slides.output_name.format(date=report_date),
        slides,
        log=echo,
    )
    typer.echo(f"Saved: {pptx}")


if __name__ == "__main__":
    typer.run(main)
