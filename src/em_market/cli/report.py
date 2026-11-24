"""4. レポート: market と factor で作った図をパワポのテンプレートに貼り、
data/processed/<report_ymd>/report/ に保存する。図はここでは作らない。

設定: configs/cli/report.yaml
    uv run em-market report
    uv run python -m em_market.cli.report
"""

from pathlib import Path
from typing import Annotated

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


def main(
    config: Annotated[Path, config_option("report")] = CLI_CONFIG_DIR / "report.yaml",
) -> None:
    """market/figures と factor/figures の図をパワポに貼り、data/processed/<report_ymd>/report/ に保存します。"""
    from em_market.reports.slides import SlidesConfig, build_slides

    cfg = load_config(ReportConfig, config)
    report_date = to_date(cfg.report_ymd, today())
    figure_dirs = [
        processed_dir(report_date, kind, "figures") for kind in ("market", "factor")
    ]
    for directory in figure_dirs:
        if not directory.exists():
            echo(f"{directory} がありません")
    if not any(directory.exists() for directory in figure_dirs):
        typer.echo(
            "図がありません。先に em-market market / factor を実行してください",
            err=True,
        )
        raise typer.Exit(1)

    slides = SlidesConfig.load()
    if not slides.template.exists():
        typer.echo(f"テンプレートがありません: {slides.template}", err=True)
        raise typer.Exit(1)
    output_dir = processed_dir(report_date, "report")
    pptx = build_slides(
        figure_dirs,
        output_dir / slides.output_name.format(date=report_date),
        slides,
        log=echo,
    )
    typer.echo(f"Saved: {pptx}")


if __name__ == "__main__":
    typer.run(main)
