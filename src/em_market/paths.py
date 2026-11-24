"""プロジェクト内のディレクトリ。data/ と templates/ は git 管理外。"""

from pathlib import Path
from typing import Literal

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "configs"
TEMPLATE_DIR = PROJECT_ROOT / "templates"

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"  # 社内 DB・ITAAP から取得したデータ (em-market factor-data)
LSEG_DIR = DATA_DIR / "lseg"  # LSEG から取得した時系列 (em-market lseg-history)
REFERENCE_DIR = DATA_DIR / "reference"  # 週次レポート用の BM 構成銘柄 (bm.csv)
PROCESSED_DIR = DATA_DIR / "processed"  # 基準日ごとの加工データとレポート

ProcessedKind = Literal["market", "factor", "report"]


def processed_dir(base_date: str | pd.Timestamp, kind: ProcessedKind) -> Path:
    """基準日の加工データの置き場所 (data/processed/{YYYYMMDD}/{kind}/)。"""
    return PROCESSED_DIR / f"{pd.Timestamp(base_date):%Y%m%d}" / kind
