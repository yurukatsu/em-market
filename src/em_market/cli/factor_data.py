"""2. factor performance 用のデータの取得: 社内 DB・ITAAP から取得し、data/raw/ に保存する (社内環境のみ)。

設定: configs/cli/factor_data.yaml
    uv run em-market factor-data
    uv run python -m em_market.cli.factor_data
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
from em_market.paths import RAW_DIR


class FactorDataConfig(CliConfig):
    """configs/cli/factor_data.yaml の内容 (説明は yaml 側のコメントを参照)。"""

    from_ymd: int | None = None
    to_ymd: int | None = None
    overwrite: bool = False


def main(
    config: Annotated[Path, config_option("factor_data")] = CLI_CONFIG_DIR
    / "factor_data.yaml",
) -> None:
    """社内 DB・ITAAP から factor performance 用のデータを取得し、data/raw/ に保存します。"""
    from em_market.dataloader.sync import update_raw

    cfg = load_config(FactorDataConfig, config)
    end = to_date(cfg.to_ymd, today() - pd.Timedelta(days=1))
    start = to_date(cfg.from_ymd, start_of_year(end))
    check_range(start, end)
    echo(f"{start:%Y%m%d} ～ {end:%Y%m%d} を {RAW_DIR} に保存")
    failures = update_raw(
        RAW_DIR, to_ymd(start), to_ymd(end), overwrite=cfg.overwrite, log=echo
    )
    typer.echo("Done" + (f" (取得できなかった日: {failures})" if failures else ""))


if __name__ == "__main__":
    typer.run(main)
