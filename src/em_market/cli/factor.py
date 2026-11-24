"""3. factor performance: data/raw/ からファクターのリターンと IC・TC を計算して図を作り、
data/processed/<output_ymd>/factor/ に保存する。

    data/     計算結果 (CSV) と計算期間など (meta.json)
    figures/  図 (PNG)

設定: configs/cli/factor.yaml
    uv run em-market factor
    uv run python -m em_market.cli.factor
"""

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
    start_of_year,
    to_date,
    to_ymd,
    today,
)
from em_market.dates import ScoreFreq
from em_market.paths import processed_dir


class FactorConfig(CliConfig):
    """configs/cli/factor.yaml の内容 (説明は yaml 側のコメントを参照)。"""

    output_ymd: int | None = None
    from_ymd: int | None = None
    to_ymd: int | None = None
    score_freq: ScoreFreq = "monthly"
    reb_ymd: int | None = None
    period_from_ymd: int | None = None
    period_to_ymd: int | None = None


def main(
    config: Annotated[Path, config_option("factor")] = CLI_CONFIG_DIR / "factor.yaml",
) -> None:
    """NAM・common ファクターのリターンと IC・TC を計算して図を作り、data/processed/<output_ymd>/factor/ に保存します。"""
    import matplotlib

    matplotlib.use("Agg")  # 画面のない環境 (EC2 など) でも描画できるように

    from em_market.reports.factor import build_factor_results, draw_factor_figures

    cfg = load_config(FactorConfig, config)
    output_date = to_date(cfg.output_ymd, today())
    end = to_date(cfg.to_ymd, output_date - pd.Timedelta(days=1))
    start = to_date(cfg.from_ymd, start_of_year(end))
    check_range(start, end)
    period_from, period_to = highlight_period(
        output_date, cfg.period_from_ymd, cfg.period_to_ymd
    )
    echo(
        f"計算期間 {start:%Y%m%d} ～ {end:%Y%m%d}｜score_freq {cfg.score_freq}｜"
        f"reb_ymd {cfg.reb_ymd}｜保存先の日付 {output_date:%Y%m%d}"
    )
    results = build_factor_results(
        to_ymd(start),
        to_ymd(end),
        score_freq=cfg.score_freq,
        reb_ymd=cfg.reb_ymd,
        log=echo,
    )
    data_dir = processed_dir(output_date, "factor", "data")
    paths = results.save(data_dir)
    typer.echo(f"Saved {len(paths)} files to {data_dir}")

    echo(f"強調する期間 {period_from:%Y%m%d} ～ {period_to:%Y%m%d}")
    figure_dir = processed_dir(output_date, "factor", "figures")
    clear_files(figure_dir)
    outputs = draw_factor_figures(
        results, to_ymd(period_from), to_ymd(period_to), figure_dir, log=echo
    )
    typer.echo(f"Saved {len(outputs)} files to {figure_dir}")


if __name__ == "__main__":
    typer.run(main)
