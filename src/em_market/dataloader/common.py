import pandas as pd
from namdb import GlobalConfig, read_db

from .code_map import CodeConverter


def get_common_factors(
    codes: list[str | int],
    ym: int | str,
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
        ym_str = str(ym)
        if len(ym_str) != 6 or not ym_str.isascii() or not ym_str.isdigit():
            raise ValueError("日付は6桁の数字で指定してください。")

    except ValueError as exc:
        raise ValueError(
            f"ym が不正です: {ym!r}。YYYYMM 形式の有効な日付を指定してください。"
        ) from exc
    id_columns = ["bid"] if code_type == "bid" else [code_type, "bid"]
    unique_codes = list(dict.fromkeys(str(code) for code in codes))

    if code_type == "bid":
        mapping = pd.DataFrame({"bid": unique_codes})
    else:
        # 指定されたコード種別 → BID
        mapping = CodeConverter.convert(
            from_code=code_type,
            to_codes=["bid"],
            codes=unique_codes,
            ym=ym,
            batch_size=batch_size,
        )

        mapping = mapping[id_columns].dropna(subset=id_columns).drop_duplicates()

    bids = mapping["bid"].unique().tolist()

    frames: list[pd.DataFrame] = []

    for start in range(0, len(bids), batch_size):
        batch = bids[start : start + batch_size]

        params = {"date": ym}
        placeholders = []

        for i, bid in enumerate(batch):
            key = f"bid_{i}"
            placeholders.append(f":{key}")
            params[key] = bid

        sql = f"""
            SELECT * FROM [GLOBAL].quants.FACTOR a
            WHERE a.BID IN ({", ".join(placeholders)})
                AND a.[DATE] = :date
        """

        frames.append(read_db(GlobalConfig(), sql, params=params))

    returns = pd.concat(frames, ignore_index=True)

    result = mapping.merge(returns, left_on="bid", right_on="BID", how="inner")
    result["ym"] = int(ym_str)

    return result
