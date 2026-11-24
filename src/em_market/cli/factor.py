"""3. factor performance の計算: data/raw/ から計算し、data/processed/<output_ymd>/factor/ に保存する。

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
    config_option,
    echo,
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


def main(
    config: Annotated[Path, config_option("factor")] = CLI_CONFIG_DIR / "factor.yaml",
) -> None:
    """NAM・common ファクターのリターンと IC・TC を計算し、data/processed/<output_ymd>/factor/ に保存します。"""
    from em_market.reports.factor import build_factor_results

    cfg = load_config(FactorConfig, config)
    output_date = to_date(cfg.output_ymd, today())
    end = to_date(cfg.to_ymd, output_date - pd.Timedelta(days=1))
    start = to_date(cfg.from_ymd, start_of_year(end))
    check_range(start, end)
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

    output_dir = processed_dir(output_date, "factor")
    paths = results.save(output_dir)
    typer.echo(f"Saved {len(paths)} files to {output_dir}")


if __name__ == "__main__":
    typer.run(main)
