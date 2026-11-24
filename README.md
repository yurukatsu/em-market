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

## データの更新 (CLI)

4 つのコマンドを順に実行する。設定は `configs/cli/<コマンド>.yaml` に書く (`--config` で別のファイルも指定できる)。
日付は YYYYMMDD で書き、`null` なら既定値 (保存先は今日、終了日はその前日など。各 yaml のコメントを参照) を使う。

```bash
uv run em-market market        # 1. LSEG から市況データを取得          → data/processed/<output_ymd>/market/
uv run em-market factor-data   # 2. 社内 DB・ITAAP からデータを取得     → data/raw/ (社内環境のみ)
uv run em-market factor        # 3. ファクターのリターンと IC・TC を計算 → data/processed/<output_ymd>/factor/
uv run em-market report        # 4. 図・表・パワポを作成                 → data/processed/<report_ymd>/report/
```

各コマンドは別ファイル (`src/em_market/cli/`) で、`uv run python -m em_market.cli.factor` のようにモジュールとしても実行できる。

| 設定ファイル | 主な項目 |
|---|---|
| `configs/cli/market.yaml` | `output_ymd`、`from_ymd`、`to_ymd` (時系列の取得期間。コモディティの図に 3 か月分使う) |
| `configs/cli/factor_data.yaml` | `from_ymd`、`to_ymd`、`overwrite` |
| `configs/cli/factor.yaml` | `output_ymd`、`from_ymd`、`to_ymd` (計算期間。図の推移もこの日から)、`score_freq`、`reb_ymd` |
| `configs/cli/report.yaml` | `report_ymd`、`period_from_ymd`、`period_to_ymd` (強調する期間)、`make_slides` |

- **market**: 指数・株価・利回り・コモディティを `from_ymd` から `to_ymd` まで取得する。決算日と経済指標は取得した時点の予定を取る。
- **factor-data**: 直近の月末営業日のスコアも使うので、`from_ymd` を含む月の前月末から取得する。保存済みの日は取り直さない (`overwrite: true` で取り直す)。
- **report**: 強調する期間は、省略時は `report_ymd` の前日を終点とする 1 週間 (`configs/weekly_report.yaml` の `data_lag_days`・`lookback_days`)。決算・経済指標のカレンダーは `report_ymd` 以降。market と factor の片方しかなければ、ある方だけ作る。市況の図は `configs/weekly_slides.yaml` に従って `templates/example.pptx` に差し込み、`EM週次市況_<日付>.pptx` も作る。

## データとファイルの置き場所

```
configs/
  cli/                     CLI の各コマンドの設定 (market, factor_data, factor, report)
  universe.yaml            LSEG の取得対象 (各国指数・セクター・国債・コモディティ)
  econ_indicators.yaml     経済指標カレンダーの対象
  weekly_report.yaml       週次レポートのパラメータ (期間、フィルター、コモディティの表示月数など)
  weekly_slides.yaml       パワポに差し込む図の対応
data/                      (git 管理外)
  raw/                     社内データ (ai, bd, bm, port, rtn, srtn, common, calendar.csv)。
                           週次レポートの BM も bm/ のうちレポートの日付以前で最新の日を使う
  processed/<日付>/
    market/                LSEG から取得した市況データ (CSV) と取得期間 (meta.json)
    factor/                ファクターのリターン、IC・TC (CSV) と計算期間など (meta.json)
    report/                図 (PNG)、表 (CSV)、パワポ
templates/example.pptx     週次レポートのパワポのテンプレート (git 管理外)
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
