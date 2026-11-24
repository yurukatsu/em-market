import pandas as pd
from namdb import TRCConfig, read_db

from em_market.const import SEDOL_CONVERSION_MAP

from .code_map import CodeConverter


def get_rga_weight(ymd: int | str, sedol_convert: bool = True) -> pd.DataFrame:
    sql = """
        SELECT calc_date AS dateymd,
            SEDOL_Code AS sedol,
            ISIN_Code AS isin,
            Constituent_Name AS name,
            Index_Weight as weight,
            Region AS region,
            Adjusted_Market_Capitalisation AS cap
        from dbo.SGX_Constituent
        WHERE calc_date = :ymd
        AND Index_Symbol = 'RGAEEMLN'
        AND [SOD/EOD] = 'EOD'
    """

    params = {"ymd": ymd}

    df = read_db(TRCConfig(), sql, params=params)
    sedols = df["sedol"].to_list()
    df["bid"] = df["sedol"].map(
        CodeConverter.from_sedol_to_bid(sedols, ymd)
    )
    if sedol_convert:
        df["sedol"] = df["sedol"].replace(SEDOL_CONVERSION_MAP)
        df["sedol"] = df["sedol"].str.removesuffix("CHN")
        df["sedol"] = df["sedol"].str.removesuffix("CHE")
        df["sedol"] = df["sedol"].str.removesuffix("LUX")
        df["sedol"] = df["sedol"].str.removesuffix("DGA")

    return df
