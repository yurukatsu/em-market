"""em-market の CLI。

コマンドごとに別ファイルで、それぞれ単独でも実行できる (python -m em_market.cli.market など)。
日付は YYYY-MM-DD でも YYYYMMDD でも指定できる。

1. market       --from-date --to-date --output-date  LSEG から市況データを取得   → data/processed/<output-date>/market/
2. factor-data  --from-date --to-date                社内 DB・ITAAP から取得     → data/raw/
3. factor       --from-date --to-date --output-date  ファクターと IC・TC を計算 → data/processed/<output-date>/factor/
4. report       --date                               図とパワポを作成           → data/processed/<date>/report/
"""
