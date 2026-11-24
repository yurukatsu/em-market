"""社内 DB・ITAAP から factor performance 用のデータを取得し、data/raw に保存する (社内環境のみ)。

手順と銘柄の決め方は get_data.ipynb と同じ。

1. calendar.csv: 営業日と月末営業日 (毎回取り直す)
2. ai/, bd/: 各日の AI・Bigdata スコア。AI スコアが取れない日は Bigdata スコアも取らない
3. common/: 各日の AI スコアの銘柄について、前月末 (last_month_end) の月の月次ファクター
4. rtn/, srtn/: 各日のリターン。銘柄は直近の月末営業日から当日までの AI スコアの銘柄
5. bm/, port/: 各日の BM とファンドのウェイト

直近の月末営業日のスコアも使うので、from_ymd を含む月の前月末から取得する。
ファイルがある日は取り直さない (overwrite=True で取り直す)。取得できない日は飛ばし、
最後にまとめて返す。
"""

from collections.abc import Callable
from functools import cache
from pathlib import Path

import pandas as pd


@cache
def _bids(path: Path) -> list[str]:
    return pd.read_csv(path)["bid"].dropna().unique().tolist()


def update_raw(
    raw_dir: Path,
    from_ymd: int,
    to_ymd: int,
    *,
    overwrite: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, list[int]]:
    """from_ymd から to_ymd の営業日のデータを取得する。取得できなかった日を種類ごとに返す。"""
    # 社内パッケージ (namdb, itaap) が必要なので、呼び出したときに読み込む
    from em_market.dataloader.ai import get_ai_score, get_bigdata_score
    from em_market.dataloader.bm import get_rga_weight
    from em_market.dataloader.calendar import get_calendar
    from em_market.dataloader.common import get_common_factors
    from em_market.dataloader.port import get_port
    from em_market.dataloader.rtn import get_rtn_usd_daily, get_strn_daily

    raw_dir = Path(raw_dir)
    failures: dict[str, list[int]] = {}
    _bids.cache_clear()  # overwrite で取り直したスコアを読み直せるように

    def save(kind: str, ymd: int, fetch: Callable[[], pd.DataFrame]) -> bool:
        """取得して保存する。保存済み・保存できたら True、取得できなければ False。"""
        path = raw_dir / kind / f"{ymd}.csv"
        if path.exists() and not overwrite:
            return True
        try:
            df = fetch()
        except Exception as exc:  # noqa: BLE001 社内 DB・ITAAP の欠損は日ごとに飛ばす
            failures.setdefault(kind, []).append(ymd)
            log(f"[{kind}] {ymd} 取得・保存失敗: {exc}")
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        return True

    log("calendar")
    calendar = get_calendar()
    raw_dir.mkdir(parents=True, exist_ok=True)
    calendar.to_csv(raw_dir / "calendar.csv", index=False)
    calendar = calendar.set_index("dateymd")

    in_range = calendar.index[(calendar.index >= from_ymd) & (calendar.index <= to_ymd)]
    if in_range.empty:
        raise ValueError(f"営業日がありません: {from_ymd}-{to_ymd}")
    start = calendar.at[in_range[0], "latest_month_end"]
    start = int(start) if pd.notna(start) else int(in_range[0])
    ymds = [int(d) for d in calendar.index if start <= d <= to_ymd]

    log(f"ai, bd ({ymds[0]} ～ {ymds[-1]}, {len(ymds)} 日)")
    for ymd in ymds:
        if save("ai", ymd, lambda ymd=ymd: get_ai_score(ymd)):
            save("bd", ymd, lambda ymd=ymd: get_bigdata_score(ymd))

    log("common")
    for ymd in ymds:
        ai_path = raw_dir / "ai" / f"{ymd}.csv"
        last_month_end = calendar.at[ymd, "last_month_end"]
        if not ai_path.exists() or pd.isna(last_month_end):
            continue
        save(
            "common",
            ymd,
            lambda ai_path=ai_path, ym=int(last_month_end) // 100: get_common_factors(
                _bids(ai_path), ym, code_type="bid"
            ),
        )

    log("rtn, srtn")
    for ymd in ymds:
        latest_month_end = calendar.at[ymd, "latest_month_end"]
        if pd.isna(latest_month_end):
            continue
        bids = sorted(
            {
                bid
                for d in ymds
                if latest_month_end <= d <= ymd
                and (raw_dir / "ai" / f"{d}.csv").exists()
                for bid in _bids(raw_dir / "ai" / f"{d}.csv")
            }
        )
        save(
            "rtn",
            ymd,
            lambda ymd=ymd, bids=bids: get_rtn_usd_daily(bids, ymd, code_type="bid"),
        )
        save(
            "srtn",
            ymd,
            lambda ymd=ymd, bids=bids: get_strn_daily(bids, ymd, code_type="bid"),
        )

    log("bm, port")
    for ymd in ymds:
        save("bm", ymd, lambda ymd=ymd: get_rga_weight(ymd))
        save("port", ymd, lambda ymd=ymd: get_port(ymd, code_type="bid"))

    return failures
