"""CLI の各コマンドで共通の処理。設定は configs/cli/<コマンド>.yaml から読む。"""

from pathlib import Path

import pandas as pd
import typer
import yaml
from pydantic import BaseModel, ConfigDict

from em_market.paths import CONFIG_DIR

CLI_CONFIG_DIR = CONFIG_DIR / "cli"


class CliConfig(BaseModel):
    """configs/cli/*.yaml の共通部分。書き間違えたキーはエラーにする。"""

    model_config = ConfigDict(extra="forbid")


def config_option(name: str):
    """--config / -c の引数。省略時は configs/cli/<name>.yaml。"""
    return typer.Option(
        "--config",
        "-c",
        exists=True,
        dir_okay=False,
        help=f"設定ファイル。省略時は configs/cli/{name}.yaml",
    )


def load_config[ConfigT: BaseModel](model: type[ConfigT], path: Path) -> ConfigT:
    with Path(path).open("r", encoding="utf-8") as f:
        return model.model_validate(yaml.safe_load(f) or {})


def to_date(ymd: int | None, default: pd.Timestamp) -> pd.Timestamp:
    """YYYYMMDD を Timestamp にする。None なら default。"""
    if ymd is None:
        return default.normalize()
    return pd.Timestamp(str(ymd)).normalize()


def to_ymd(day: pd.Timestamp) -> int:
    return int(f"{day:%Y%m%d}")


def today() -> pd.Timestamp:
    return pd.Timestamp.today().normalize()


def start_of_year(day: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(year=day.year, month=1, day=1)


def check_range(start: pd.Timestamp, end: pd.Timestamp) -> None:
    if start > end:
        raise typer.BadParameter(
            f"from_ymd が to_ymd より後です: {start:%Y%m%d} > {end:%Y%m%d}"
        )


def echo(message: str) -> None:
    typer.echo(f"- {message}")
