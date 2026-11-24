import datetime

import pandas as pd
from namdb import KGXConfig, read_db

from em_market.const import SEDOL_CONVERSION_MAP
from .code_map import CodeConverter


def get_port(
    ymd: int | str,
    *,
    code_type: str = "bid",
    sedol_convert: bool = True,
    batch_size: int = 1000,
) -> pd.DataFrame:

    sql = """
        SELECT
            RTRIM(iss_cd) AS sedol,
            qty AS quantity,
            price AS price,
            mktval AS market_value,
            cntry_cd AS country_code
        FROM
            K_GX.dbo.PosTDView
        WHERE prt_cd = '0065313'
            AND date = :ymd
            AND sec_type = 'S'
            AND qty > 0
    """

    df = read_db(KGXConfig(), sql, params={"ymd": ymd})
    df["weight"] = df["market_value"] / df["market_value"].sum() * 100

    if sedol_convert:
        df["sedol"] = df["sedol"].replace(SEDOL_CONVERSION_MAP)
        df["sedol"] = df["sedol"].str.removesuffix("CHN")
        df["sedol"] = df["sedol"].str.removesuffix("CHE")
        df["sedol"] = df["sedol"].str.removesuffix("LUX")
        df["sedol"] = df["sedol"].str.removesuffix("DGA")

    if code_type != "sedol":
        mapping = CodeConverter.convert("sedol", [code_type], df["sedol"].to_list(), ymd=ymd, batch_size=batch_size)
        df = df.merge(mapping, how="left", on="sedol")

        if len(df) != len(df.dropna(subset=[code_type])):
            print(f"Warning: origin ({len(df)}), filtered ({len(df.dropna(subset=[code_type]))})")
            print(f"Warning: diff ({df[df[code_type].isna()]["sedol"]})")
    return df
