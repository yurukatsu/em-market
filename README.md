# em-market

新興国株式の分析ツール。次の 2 つを 1 つのパッケージ (`em_market`) で扱う。

- **ファクター分析**: 社内データから NAM / common ファクターのリターン、IC・TC を計算して図にする
- **週次レポート**: LSEG Data Library (`lseg-data`) から市況データを取得し、図表とパワポを作る

## セットアップ

```bash
uv sync
cp .env.example .env   # LSEG_APP_KEY / LSEG_USERNAME / LSEG_PASSWORD を記入 (市況データを取得する場合)
```

`lseg-data` が pandas 3 に未対応のため、pandas は 2.x に固定している。

## CLI

4 つのコマンドは別ファイル (`src/em_market/cli/`) で、それぞれ単独で実行できる。
日付は `2026-11-25` でも `20261125` でも指定できる。

```bash
# 1. LSEG から市況データを取得 → data/processed/20261125/market/
uv run em-market market --from-date 2026-08-01 --to-date 2026-11-24 --output-date 2026-11-25
# 2. 社内 DB・ITAAP からデータを取得 → data/raw/ (社内環境のみ)
uv run em-market factor-data --from-date 2026-01-01 --to-date 2026-11-24
# 3. ファクターのリターンと IC・TC を計算 → data/processed/20261125/factor/
uv run em-market factor --from-date 2026-01-01 --to-date 2026-11-24 --output-date 2026-11-25
# 4. 図とパワポ → data/processed/20261125/report/
uv run em-market report --date 2026-11-25
```

`uv run python -m em_market.cli.factor --output-date 2026-11-25` のように、モジュールとしても実行できる。

- **省略時の日付**: `--output-date` は今日、`--to-date` はその前日 (factor-data は昨日)。`--from-date` は、market が `--to-date` の 3 か月 (`commodity_months`) と 2 週間前、factor と factor-data が `--to-date` の年の 1 月 1 日。
- **market**: 指数・株価・利回り・コモディティを `--from-date` から `--to-date` まで取得する。決算日と経済指標は取得した時点の予定を取る。
- **factor-data**: 直近の月末営業日のスコアも使うので、`--from-date` を含む月の前月末から取得する。保存済みの日は取り直さない (`--overwrite` で取り直す)。
- **report**: `--date` のフォルダの market と factor から作る。強調する週 (リターンの期間) は `--date` の前日を終点とする 1 週間 (`configs/weekly_report.yaml` の `data_lag_days`・`lookback_days`)、決算・経済指標のカレンダーは `--date` 以降。片方しかなければ、ある方だけ作る。市況の図は `configs/weekly_slides.yaml` に従って `templates/example.pptx` に差し込み、`EM週次市況_<日付>.pptx` も作る (`--no-slides` で省略)。

補助コマンド: `uv run em-market lseg-history countries --start 2025-10-01` (universe.yaml のグループの時系列を `data/lseg/` に保存)

## データとファイルの置き場所

```
configs/
  universe.yaml            LSEG の取得対象 (各国指数・セクター・国債・コモディティ)
  econ_indicators.yaml     経済指標カレンダーの対象
  weekly_report.yaml       週次レポートのパラメータ (期間、フィルターなど)
  weekly_slides.yaml       パワポに差し込む図の対応
  factor_performance.yaml  ファクターのスコアの種類、リバランス日
data/                      (git 管理外)
  raw/                     社内データ (ai, bd, bm, port, rtn, srtn, common, calendar.csv)
  processed/<日付>/
    market/                LSEG から取得した市況データ (CSV)
    factor/                ファクターのリターン、IC・TC (CSV) と期間など (meta.json)
    report/                図 (PNG)、表 (CSV)、パワポ
  reference/bm.csv         週次レポート用のベンチマーク構成銘柄 (sedol, isin, name, cap, weight)
  lseg/                    lseg-history で取得した時系列
templates/example.pptx     週次レポートのパワポのテンプレート (git 管理外)
notebooks/                 factor_performance.ipynb (ファクター分析)、weekly_report_sample.ipynb (週次レポート)
```

## コード構成

```
src/em_market/
  cli/            CLI。app.py がコマンドの一覧、各コマンドは market / factor_data / factor / report.py
  paths.py        configs/, data/, templates/ の場所
  const.py        ファクター・国などの定数
  dates.py        日付の共通定義 (週次の期間など)
  raw.py          data/raw の CSV の読み込み
  dataloader/     社内 DB・ITAAP からの取得 (社内環境のみ)。sync.py が data/raw への保存
  market/         LSEG からの取得と集計 (client, universe, earnings, economics, rates, labels)
  factor/         ファクターリターン (nam, common) とスコアの指標 (score)。ファイルは読まない
  viz/            図。style.py が配色・大きさ・フォントの共通部分
  reports/        weekly.py (市況)、factor.py (ファクター)、slides.py (パワポへの差し込み)
  fonts/          Noto Sans JP (SIL OFL)
```

notebook を git に入れるときは、実行結果を消してからコミットする。
