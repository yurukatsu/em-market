import datetime

import pandas as pd
from namdb import FsTrfacGlbConfig, RiskModelsConfig, read_db

from .code_map import CodeConverter


def get_rtn_usd_daily(
    codes: list[str | int],
    ymd: int | str,
    *,
    code_type: str = "bid",
    batch_size: int = 1000,
) -> pd.DataFrame:
    if code_type not in CodeConverter.codes:
        raise ValueError(
            f"code_type が不正です: {code_type!r}。"
            f"使用可能な値: {', '.join(CodeConverter.codes)}"
        )

    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or batch_size <= 0
    ):
        raise ValueError(f"batch_size は正の整数を指定してください: {batch_size!r}")

    try:
        ymd_str = str(ymd)
        if len(ymd_str) != 8 or not ymd_str.isascii() or not ymd_str.isdigit():
            raise ValueError("日付は8桁の数字で指定してください。")

        date = datetime.datetime.strptime(ymd_str, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(
            f"ymd が不正です: {ymd!r}。YYYYMMDD 形式の有効な日付を指定してください。"
        ) from exc

    # nam_id 指定時は識別子の列を重複させない
    id_columns = ["nam_id"] if code_type == "nam_id" else [code_type, "nam_id"]
    columns = ["ymd", *id_columns, "rtn"]

    if not codes:
        return pd.DataFrame(columns=columns).astype({"ymd": "int64"})

    unique_codes = list(dict.fromkeys(str(code) for code in codes))

    if code_type == "nam_id":
        mapping = pd.DataFrame({"nam_id": unique_codes})
    else:
        # 指定されたコード種別 → NAMID
        mapping = CodeConverter.convert(
            from_code=code_type,
            to_codes=["nam_id"],
            codes=unique_codes,
            ymd=ymd,
            batch_size=batch_size,
        )

        mapping = mapping[id_columns].dropna(subset=id_columns).drop_duplicates()

    if mapping.empty:
        return pd.DataFrame(columns=columns).astype({"ymd": "int64"})

    nam_ids = mapping["nam_id"].unique().tolist()
    params_date = date.strftime("%Y-%m-%d")

    frames: list[pd.DataFrame] = []

    for start in range(0, len(nam_ids), batch_size):
        batch = nam_ids[start : start + batch_size]

        params = {"date": params_date}
        placeholders = []

        for i, nam_id in enumerate(batch):
            key = f"nam_id_{i}"
            placeholders.append(f":{key}")
            params[key] = nam_id

        sql = f"""
            SELECT
                RTRIM(a.nam_id) AS nam_id,
                a.drtnp AS rtn
            FROM public.exshare AS a
            WHERE a.nam_id IN ({", ".join(placeholders)})
                AND a.date = :date
        """

        frames.append(read_db(FsTrfacGlbConfig(), sql, params=params))

    returns = pd.concat(frames, ignore_index=True)

    result = mapping.merge(returns, on="nam_id", how="inner")
    result["ymd"] = int(ymd_str)

    return result[columns]


def get_strn_daily(
    codes: list[str | int],
    ymd: int | str,
    *,
    code_type: str = "bid",
    batch_size: int = 1000,
):
    if code_type not in CodeConverter.codes:
        raise ValueError(
            f"code_type が不正です: {code_type!r}。"
            f"使用可能な値: {', '.join(CodeConverter.codes)}"
        )

    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or batch_size <= 0
    ):
        raise ValueError(f"batch_size は正の整数を指定してください: {batch_size!r}")

    try:
        ymd_str = str(ymd)
        if len(ymd_str) != 8 or not ymd_str.isascii() or not ymd_str.isdigit():
            raise ValueError("日付は8桁の数字で指定してください。")

    except ValueError as exc:
        raise ValueError(
            f"ymd が不正です: {ymd!r}。YYYYMMDD 形式の有効な日付を指定してください。"
        ) from exc

    # bid 指定時は識別子の列を重複させない
    id_columns = ["bid"] if code_type == "bid" else [code_type, "bid"]
    columns = ["ymd", *id_columns, "rtn"]

    if not codes:
        return pd.DataFrame(columns=columns).astype({"ymd": "int64"})

    unique_codes = list(dict.fromkeys(str(code) for code in codes))

    if code_type == "bid":
        mapping = pd.DataFrame({"bid": unique_codes})
    else:
        # 指定されたコード種別 → BID
        mapping = CodeConverter.convert(
            from_code=code_type,
            to_codes=["bid"],
            codes=unique_codes,
            ymd=ymd,
            batch_size=batch_size,
        )

        mapping = mapping[id_columns].dropna(subset=id_columns).drop_duplicates()

    if mapping.empty:
        return pd.DataFrame(columns=columns).astype({"ymd": "int64"})

    bids = mapping["bid"].unique().tolist()

    frames: list[pd.DataFrame] = []

    for start in range(0, len(bids), batch_size):
        batch = bids[start : start + batch_size]

        params = {"date": ymd}
        placeholders = []

        for i, bid in enumerate(batch):
            key = f"bid_{i}"
            placeholders.append(f":{key}")
            params[key] = bid

        sql = f"""
            SELECT
                RTRIM(a.BID) AS bid, a.SRTN AS rtn
            FROM GEMLT_D_SRTN AS a
            WHERE a.BID IN ({", ".join(placeholders)})
                AND a.[DATE] = :date
        """

        frames.append(read_db(RiskModelsConfig(), sql, params=params))

    returns = pd.concat(frames, ignore_index=True)

    result = mapping.merge(returns, on="bid", how="inner")
    result["ymd"] = int(ymd_str)

    return result[columns]
