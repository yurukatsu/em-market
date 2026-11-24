"""補助: universe.yaml のグループの時系列を LSEG から取得し、data/lseg/<group>.csv に保存する。

uv run em-market lseg-history countries --start 2025-10-01 --end 2026-10-01
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

import typer

from em_market.paths import CONFIG_DIR, LSEG_DIR


def main(
    group: Annotated[
        str,
        typer.Argument(help="universe.yaml のグループ名（countries, sectors など）"),
    ],
    field: Annotated[
        str, typer.Option("--field", "-f", help="取得フィールド")
    ] = "TR.PriceClose(Curn=USD)",
    start: Annotated[str, typer.Option(help="開始日 (YYYY-MM-DD)。省略時は1年前")] = "",
    end: Annotated[str, typer.Option(help="終了日 (YYYY-MM-DD)。省略時は今日")] = "",
    config_path: Annotated[
        Path,
        typer.Option(
            "--config", "-c", help="ユニバース設定ファイル", exists=True, dir_okay=False
        ),
    ] = CONFIG_DIR / "universe.yaml",
    output_path: Annotated[
        Path | None,
        typer.Option(
            "--output", "-o", help="CSV出力先。省略時は data/lseg/<group>.csv"
        ),
    ] = None,
) -> None:
    """universe.yaml のグループの時系列を LSEG から取得して CSV に出力します。"""
    from em_market.market.client import LSEGClient
    from em_market.market.universe import alias_map, load_universe

    universe = load_universe(config_path)
    if group not in universe:
        raise typer.BadParameter(
            f"{group} は {config_path} にありません: {list(universe)}"
        )
    instruments = universe[group]

    end = end or date.today().isoformat()
    start = start or (date.fromisoformat(end) - timedelta(days=365)).isoformat()

    with LSEGClient() as client:
        df = client.get_history(
            universe=[i.ticker for i in instruments],
            fields=[field],
            start=start,
            end=end,
        )
    df = df.rename(columns=alias_map(instruments))
    df.index.name = "date"

    output_path = output_path or LSEG_DIR / f"{group}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path)
    typer.echo(f"Saved: {output_path} ({len(df)} rows)")


if __name__ == "__main__":
    typer.run(main)
