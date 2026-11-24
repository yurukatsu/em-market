"""em-market の CLI。

コマンドごとに別ファイルで、それぞれ単独でも実行できる (python -m em_market.cli.market など)。
設定は configs/cli/<コマンド>.yaml に書き、--config で別のファイルも指定できる。

1. market       市況データを取得し、図と表を作成       → data/processed/<output_ymd>/market/{data,figures}/
2. factor-data  社内 DB・ITAAP からデータを取得        → data/raw/
3. factor       ファクターを計算し、図を作成           → data/processed/<output_ymd>/factor/{data,figures}/
4. report       1 と 3 の図をパワポに貼る (図は作らない) → data/processed/<report_ymd>/report/
"""
