import datetime

import pandas as pd
from namdb import (
    EquityConfig,
    read_db
)
def get_calendar(
    from_ymd: int | str = 20201231,
    to_ymd: int | str = 20501231,
    index_code: int ="MSEM"
) -> pd.DataFrame:
    sql = """
        SELECT DISTINCT dateymd
        FROM index_global
        WHERE dateymd >= :from_ymd
            AND dateymd <= :to_ymd
            AND index_code = :index_code
        ORDER BY dateymd
    """

    params = {
        "from_ymd": from_ymd,
        "to_ymd": to_ymd,
        "index_code": index_code,
    }

    df = read_db(EquityConfig(), sql, params=params)

    dates = pd.to_datetime(df["dateymd"].astype(str), format="%Y%m%d")
    months = dates.dt.to_period("M")

    # 各月の最終営業日
    month_ends = dates.groupby(months).max()

    # 最後の月は月末までデータが揃っていない可能性があるため除外
    month_ends = month_ends[month_ends.index < months.max()]

    # 当月の月末最終営業日
    current_month_ends = months.map(month_ends)

    # 前月の最終営業日
    last_month_ends = (months - 1).map(month_ends)

    # その日以前で直近の月末最終営業日
    latest_month_ends = last_month_ends.mask(
        dates.eq(current_month_ends),
        dates,
    )

    df["month_end"] = (
        current_month_ends.dt.strftime("%Y%m%d").astype("Int64")
    )
    df["last_month_end"] = (
        last_month_ends.dt.strftime("%Y%m%d").astype("Int64")
    )
    df["latest_month_end"] = (
        latest_month_ends.dt.strftime("%Y%m%d").astype("Int64")
    )
    return df
