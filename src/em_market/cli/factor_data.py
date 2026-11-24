"""2. factor performance 用のデータの作成: 社内 DB・ITAAP から取得し、data/raw/ に保存する (社内環境のみ)。

uv run em-market factor-data --from-date 2026-01-01 --to-date 2026-11-24
uv run python -m em_market.cli.factor_data --from-date 2026-01-01 --to-date 2026-11-24
"""

from typing import Annotated

import typer

from em_market.cli._common import echo, parse_date, parse_range, start_of_year, to_ymd
from em_market.paths import RAW_DIR


def main(
    from_date: Annotated[
        str,
        typer.Option(
            "--from-date",
            help="取得開始日。直近の月末営業日のスコアも使うので、その前月末から取得する。"
            "省略時は --to-date の年の 1 月 1 日",
        ),
    ] = "",
    to_date: Annotated[
        str, typer.Option("--to-date", help="取得終了日。省略時は昨日")
    ] = "",
    overwrite: Annotated[bool, typer.Option(help="保存済みの日も取り直す")] = False,
) -> None:
    """社内 DB・ITAAP から factor performance 用のデータを取得し、data/raw/ に保存します。"""
    from em_market.dataloader.sync import update_raw

    start, end = parse_range(from_date, to_date, parse_date(""), start_of_year)
    echo(f"{start:%Y-%m-%d} ～ {end:%Y-%m-%d} を {RAW_DIR} に保存")
    failures = update_raw(
        RAW_DIR, to_ymd(start), to_ymd(end), overwrite=overwrite, log=echo
    )
    typer.echo("Done" + (f" (取得できなかった日: {failures})" if failures else ""))


if __name__ == "__main__":
    typer.run(main)
