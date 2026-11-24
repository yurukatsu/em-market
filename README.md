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

## データの更新 (notebook)

`notebooks/` の 4 つの notebook を順に実行する。どれも先頭のパラメータのセルを書き換えてから、すべて実行する。
日付は `20261125` のような YYYYMMDD で指定する。

| notebook | 内容 | 保存先 |
|---|---|---|
| `01_market_data.ipynb` | LSEG から市況データを取得 | `data/processed/<output_ymd>/market/` |
| `02_factor_data.ipynb` | 社内 DB・ITAAP から取得 (社内環境のみ) | `data/raw/` |
| `03_factor_performance.ipynb` | NAM・common ファクターのリターンと IC・TC を計算 | `data/processed/<output_ymd>/factor/` |
| `04_report.ipynb` | 01・03 の結果から図・表・パワポを作り、図を表示 | `data/processed/<report_ymd>/report/` |

- **01**: 指数・株価・利回り・コモディティを `from_ymd` から `to_ymd` まで取得する。コモディティの図に 3 か月分使う。決算日と経済指標は取得した時点の予定を取る。
- **02**: 直近の月末営業日のスコアも使うので、`from_ymd` を含む月の前月末から取得する。保存済みの日は取り直さない (`overwrite = True` で取り直す)。
- **03**: `from_ymd` から `to_ymd` で計算する。図の推移もこの日から描くので、IC の 20 日移動平均のため長めに取る。スコアの種類 (`score_freq`) とリバランス日 (`reb_ymd`) もここで指定する。
- **04**: 強調する期間 (`period_from_ymd`、`period_to_ymd`) は、省略時は `report_ymd` の前日を終点とする 1 週間 (`configs/weekly_report.yaml` の `data_lag_days`・`lookback_days`)。決算・経済指標のカレンダーは `report_ymd` 以降。market と factor の片方しかなければ、ある方だけ作る。市況の図は `configs/weekly_slides.yaml` に従って `templates/example.pptx` に差し込み、`EM週次市況_<日付>.pptx` も作る。

notebook を git に入れるときは、実行結果を消してからコミットする。

## データとファイルの置き場所

```
configs/
  universe.yaml            LSEG の取得対象 (各国指数・セクター・国債・コモディティ)
  econ_indicators.yaml     経済指標カレンダーの対象
  weekly_report.yaml       週次レポートのパラメータ (期間、フィルターなど)
  weekly_slides.yaml       パワポに差し込む図の対応
data/                      (git 管理外)
  raw/                     社内データ (ai, bd, bm, port, rtn, srtn, common, calendar.csv)。
                           週次レポートの BM も bm/ のうちレポートの日付以前で最新の日を使う
  processed/<日付>/
    market/                LSEG から取得した市況データ (CSV) と取得期間 (meta.json)
    factor/                ファクターのリターン、IC・TC (CSV) と計算期間など (meta.json)
    report/                図 (PNG)、表 (CSV)、パワポ
templates/example.pptx     週次レポートのパワポのテンプレート (git 管理外)
notebooks/                 データ更新の notebook (01〜04)
```

## コード構成

```
src/em_market/
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
