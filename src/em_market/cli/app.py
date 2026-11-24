"""em-market コマンド。各コマンドの本体は同じフォルダの別ファイルにある。"""

import typer

from em_market.cli import factor, factor_data, market, report

app = typer.Typer(
    help="新興国株式のファクター分析と、LSEG の市況データによる週次レポートのツール。"
    "設定は configs/cli/<コマンド>.yaml に書く。",
    no_args_is_help=True,
)
app.command("market")(market.main)
app.command("factor-data")(factor_data.main)
app.command("factor")(factor.main)
app.command("report")(report.main)
