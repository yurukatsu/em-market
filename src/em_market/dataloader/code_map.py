import datetime

import pandas as pd
from namdb import FsTrfacGlbConfig, read_db


class CodeConverter:
    codes: list[str] = ["bid", "sedol", "isin", "cusip", "nam_id"]

    @classmethod
    def convert(
        cls,
        from_code: str,
        to_codes: list[str],
        codes: list[str | int],
        ymd: int | str,
        batch_size: int = 1000,
    ) -> pd.DataFrame:
        valid_codes = ", ".join(cls.codes)

        if from_code not in cls.codes:
            raise ValueError(
                f"from_code が不正です: {from_code!r}。使用可能な値: {valid_codes}"
            )

        if not to_codes:
            raise ValueError("to_codes に変換先のコード種別を1つ以上指定してください。")

        for to_code in to_codes:
            if to_code not in cls.codes:
                raise ValueError(
                    f"to_codes に不正なコード種別が含まれています: {to_code!r}。"
                    f"使用可能な値: {valid_codes}"
                )

        if not codes:
            raise ValueError("codes に変換対象のコードを1つ以上指定してください。")

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

            date = datetime.datetime.strptime(ymd_str, "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(
                f"ymd が不正です: {ymd!r}。"
                "YYYYMMDD 形式の有効な日付を指定してください。"
            ) from exc

        # 入力コードの重複を除去
        unique_codes = list(dict.fromkeys(str(code) for code in codes))

        # 取得列の重複を除去し、各列の末尾の空白を除去
        columns = ", ".join(
            f"RTRIM({c}) AS {c}" for c in dict.fromkeys([from_code, *to_codes])
        )

        frames: list[pd.DataFrame] = []

        for start in range(0, len(unique_codes), batch_size):
            batch = unique_codes[start : start + batch_size]

            params = {"date": date}
            placeholders = []

            for i, code in enumerate(batch):
                key = f"code_{i}"
                placeholders.append(f":{key}")
                params[key] = code

            sql = f"""
                SELECT {columns}
                FROM public.barraid
                WHERE RTRIM({from_code}) IN ({", ".join(placeholders)})
                    AND date = :date
            """

            frames.append(read_db(FsTrfacGlbConfig(), sql, params=params))

        return pd.concat(frames, ignore_index=True)

    @classmethod
    def from_bid_to_namid(
        cls,
        codes: list[str | int],
        ymd: int | str,
        batch_size: int = 1000,
    ) -> dict[str, str]:
        df = cls.convert(
            from_code="bid",
            to_codes=["nam_id"],
            codes=codes,
            ymd=ymd,
            batch_size=batch_size,
        )

        return df.dropna(subset=["bid", "nam_id"]).set_index("bid")["nam_id"].to_dict()

    @classmethod
    def from_sedol_to_bid(
        cls,
        codes: list[str | int],
        ymd: int | str,
        batch_size: int = 1000,
    ) -> dict[str, str]:
        df = cls.convert(
            from_code="sedol",
            to_codes=["bid"],
            codes=codes,
            ymd=ymd,
            batch_size=batch_size,
        )

        return df.dropna(subset=["sedol", "bid"]).set_index("sedol")["bid"].to_dict()
