"""CLI の各コマンドで共通の引数と補助関数。

日付は YYYY-MM-DD でも YYYYMMDD でも指定できる。
"""

from typing import Annotated

import pandas as pd
import typer

BaseDateOption = Annotated[
    str,
    typer.Option(
        "--date",
        "-d",
        help="レポートの日付 (YYYY-MM-DD または YYYYMMDD)。省略時は今日。"
        "data/processed/<日付>/ のデータを使い、同じ場所に保存する",
    ),
]
OutputDateOption = Annotated[
    str,
    typer.Option(
        "--output-date",
        help="保存先の日付。data/processed/<日付>/ に保存する。省略時は今日",
    ),
]


def parse_date(value: str, default: pd.Timestamp | None = None) -> pd.Timestamp:
    """日付の文字列を Timestamp にする。空なら default (省略時は今日)。"""
    if not value:
        return (default if default is not None else pd.Timestamp.today()).normalize()
    return pd.Timestamp(value).normalize()


def parse_range(
    from_date: str, to_date: str, output_date: pd.Timestamp, default_from
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """--from-date と --to-date を解釈する。

    --to-date の省略時は保存先の日付の前日。--from-date の省略時は default_from(to) とする。
    """
    to = parse_date(to_date, output_date - pd.Timedelta(days=1))
    start = parse_date(from_date, default_from(to))
    if start > to:
        raise typer.BadParameter(
            f"--from-date が --to-date より後です: {start:%Y-%m-%d} > {to:%Y-%m-%d}"
        )
    return start, to


def start_of_year(day: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(year=day.year, month=1, day=1)


def to_ymd(day: pd.Timestamp) -> int:
    return int(f"{day:%Y%m%d}")


def echo(message: str) -> None:
    typer.echo(f"- {message}")
