"""em-market の CLI。

コマンドごとに別ファイルで、それぞれ単独でも実行できる (python -m em_market.cli.market など)。
設定は configs/cli/<コマンド>.yaml に書き、--config で別のファイルも指定できる。

1. market       LSEG から市況データを取得           → data/processed/<output_ymd>/market/
2. factor-data  社内 DB・ITAAP からデータを取得     → data/raw/
3. factor       ファクターのリターンと IC・TC を計算 → data/processed/<output_ymd>/factor/
4. report       図・表・パワポを作成                 → data/processed/<report_ymd>/report/
"""
