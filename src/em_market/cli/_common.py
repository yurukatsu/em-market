"""CLI の各コマンドで共通の処理。設定は configs/cli/<コマンド>.yaml から読む。"""

from pathlib import Path

import pandas as pd
import typer
import yaml
from pydantic import BaseModel, ConfigDict

from em_market.paths import CONFIG_DIR, ensure_configs

CLI_CONFIG_DIR = CONFIG_DIR / "cli"

# configs/ は git 管理外。初回 (や configs.sample/ に設定が増えたとき) は雛形からコピーする。
# --config の存在チェックより前に済ませるため、読み込んだ時点で実行する
ensure_configs(log=lambda message: typer.echo(f"- {message}", err=True))


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


def highlight_period(
    base_date: pd.Timestamp, from_ymd: int | None, to_ymd: int | None
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """図で強調する期間 (最初の日, 最後の日)。

    省略した方は週次レポートと同じ週 (base_date の data_lag_days 日前を終点とする
    lookback_days 日間。configs/weekly_report.yaml) から決める。
    """
    from em_market.dates import weekly_period
    from em_market.reports.weekly import WeeklyReportConfig

    weekly = WeeklyReportConfig.load()
    start, end = weekly_period(base_date, weekly.lookback_days, weekly.data_lag_days)
    first = to_date(from_ymd, start + pd.Timedelta(days=1))
    last = to_date(to_ymd, end)
    if first > last:
        raise typer.BadParameter(
            f"period_from_ymd が period_to_ymd より後です: {first:%Y%m%d} > {last:%Y%m%d}"
        )
    return first, last


def clear_files(directory: Path) -> None:
    """図の置き場所を作り直す。前回の図 (ページ数が減ったときの余りなど) を残さない。"""
    if directory.exists():
        for path in directory.iterdir():
            if path.is_file():
                path.unlink()


def echo(message: str) -> None:
    typer.echo(f"- {message}")
