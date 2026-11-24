"""3. factor performance の計算: data/raw から計算し、data/processed/<日付>/factor/ に保存する。

uv run em-market factor --from-date 2026-01-01 --to-date 2026-11-24 --output-date 2026-11-25
uv run python -m em_market.cli.factor --output-date 2026-11-25
"""

from pathlib import Path
from typing import Annotated

import typer

from em_market.cli._common import (
    OutputDateOption,
    echo,
    parse_date,
    parse_range,
    start_of_year,
    to_ymd,
)
from em_market.paths import CONFIG_DIR, RAW_DIR, processed_dir


def main(
    from_date: Annotated[
        str,
        typer.Option(
            "--from-date", help="計算開始日。省略時は --to-date の年の 1 月 1 日"
        ),
    ] = "",
    to_date: Annotated[
        str,
        typer.Option("--to-date", help="計算終了日。省略時は --output-date の前日"),
    ] = "",
    output_date: OutputDateOption = "",
    factor_config: Annotated[
        Path,
        typer.Option(
            help="ファクターパフォーマンスの設定 (スコアの種類、リバランス日)",
            exists=True,
            dir_okay=False,
        ),
    ] = CONFIG_DIR / "factor_performance.yaml",
) -> None:
    """NAM・common ファクターのリターンと IC・TC を計算し、data/processed/<--output-date>/factor/ に保存します。"""
    from em_market.reports.factor import FactorPerformanceConfig, build_factor_results

    output = parse_date(output_date)
    start, end = parse_range(from_date, to_date, output, start_of_year)
    echo(f"計算期間 {start:%Y-%m-%d} ～ {end:%Y-%m-%d}｜保存先の日付 {output:%Y-%m-%d}")
    results = build_factor_results(
        to_ymd(start),
        to_ymd(end),
        FactorPerformanceConfig.load(factor_config),
        raw_dir=RAW_DIR,
        log=echo,
    )

    output_dir = processed_dir(output, "factor")
    paths = results.save(output_dir)
    typer.echo(f"Saved {len(paths)} files to {output_dir}")


if __name__ == "__main__":
    typer.run(main)
