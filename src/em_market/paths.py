"""プロジェクト内のディレクトリ。configs/, data/, templates/ は git 管理外。"""

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "configs"  # 設定。git 管理外で、雛形は configs.sample/
SAMPLE_CONFIG_DIR = PROJECT_ROOT / "configs.sample"
TEMPLATE_DIR = PROJECT_ROOT / "templates"

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"  # 社内 DB・ITAAP から取得したデータ (em-market factor-data)
PROCESSED_DIR = DATA_DIR / "processed"  # 基準日ごとの加工データとレポート


def ensure_configs(log: Callable[[str], None] = print) -> list[Path]:
    """configs/ にない設定ファイルを configs.sample/ からコピーし、コピーしたファイルを返す。

    configs/ にあるファイルは上書きしない。
    """
    copied = []
    for sample in sorted(SAMPLE_CONFIG_DIR.rglob("*")):
        target = CONFIG_DIR / sample.relative_to(SAMPLE_CONFIG_DIR)
        if sample.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sample, target)
            copied.append(target)
            log(
                f"{target.relative_to(PROJECT_ROOT)} がないので configs.sample/ からコピーしました"
            )
    return copied


ProcessedKind = Literal["market", "factor", "report"]
ProcessedSub = Literal["data", "figures"]


def processed_dir(
    base_date: str | pd.Timestamp,
    kind: ProcessedKind,
    sub: ProcessedSub | None = None,
) -> Path:
    """基準日の加工データの置き場所 (data/processed/{YYYYMMDD}/{kind}/{sub}/)。

    market と factor は data/ (取得・計算したデータ) と figures/ (図と表) に分ける。
    """
    path = PROCESSED_DIR / f"{pd.Timestamp(base_date):%Y%m%d}" / kind
    return path / sub if sub else path
