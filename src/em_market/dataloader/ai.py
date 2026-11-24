import pandas as pd
from itaap import ItaapSSHClient

ITAAP_AI_SCORE_DIRS: dict[str:str] = {
    20261111: "/home/abe/blf/score/daily",  # ～ 2026/11/11 までは利用できるという意味
    99991231: "/home/abe/blf/score/daily-rri",  # 2026/11/11 ～ 9999/12/31 までは利用できるという意味
}

ITAAP_BD_SCORE_DIRS: dict[str:str] = {
    20261111: "/home/abe/blf/score/daily/bigdata",
    99991231: "/home/abe/blf/score/daily-rri/bigdata",
}


def get_ai_score_dir_path(ymd: int | str) -> str:
    ymd = int(ymd)
    expired_ymds = list(ITAAP_AI_SCORE_DIRS.keys())
    n_dir = len(expired_ymds)

    if len(expired_ymds) == 1:
        return ITAAP_AI_SCORE_DIRS[expired_ymds[0]]

    if ymd <= expired_ymds[0]:
        return ITAAP_AI_SCORE_DIRS[expired_ymds[0]]

    for i in range(n_dir - 1):
        if expired_ymds[i] < ymd <= expired_ymds[i + 1]:
            return ITAAP_AI_SCORE_DIRS[expired_ymds[i + 1]]


def get_bd_score_dir_path(ymd: int | str) -> str:
    ymd = int(ymd)
    expired_ymds = list(ITAAP_BD_SCORE_DIRS.keys())
    n_dir = len(expired_ymds)

    if len(expired_ymds) == 1:
        return ITAAP_BD_SCORE_DIRS[expired_ymds[0]]

    if ymd <= expired_ymds[0]:
        return ITAAP_BD_SCORE_DIRS[expired_ymds[0]]

    for i in range(n_dir - 1):
        if expired_ymds[i] < ymd <= expired_ymds[i + 1]:
            return ITAAP_BD_SCORE_DIRS[expired_ymds[i + 1]]


def get_ai_score(ymd: int | str) -> pd.DataFrame:
    client = ItaapSSHClient()
    return client.read_csv(f"{get_ai_score_dir_path(ymd)}/{ymd}.csv")


def get_bigdata_score(ymd: int | str) -> pd.DataFrame:
    client = ItaapSSHClient()
    return client.read_csv(f"{get_bd_score_dir_path(ymd)}/{ymd}.csv")
