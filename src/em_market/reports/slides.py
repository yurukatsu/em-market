"""パワポのテンプレートに図（PNG）を差し込む。

テンプレート上の既存の図を、位置・大きさを保ったまま新しい PNG に置き換える。
どのスライドのどの図にどの PNG を入れるかは configs/weekly_slides.yaml で指定する。
"""

import copy
from collections.abc import Callable
from pathlib import Path

import yaml
from PIL import Image
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.presentation import Presentation as PresentationType
from pptx.shapes.picture import Picture
from pptx.slide import Slide
from pydantic import BaseModel, model_validator

from em_market.paths import CONFIG_DIR, PROJECT_ROOT

R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


# ---- 設定 --------------------------------------------------------------------


class SlideSpec(BaseModel):
    """1枚のスライドに固定の図を入れる（slide + images）か、
    複数ページの図をスライドの範囲に入れる（slides + pages）。"""

    slide: int | None = None
    images: list[str] = []
    slides: tuple[int, int] | None = None
    pages: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "SlideSpec":
        if (
            self.slide is not None
            and self.images
            and self.slides is None
            and not self.pages
        ):
            return self
        if (
            self.slides is not None
            and self.pages
            and self.slide is None
            and not self.images
        ):
            if self.slides[0] > self.slides[1]:
                raise ValueError(
                    f"slides は [最初, 最後] の順で指定してください: {self.slides}"
                )
            return self
        raise ValueError(
            "slide + images か slides + pages のどちらかを指定してください"
        )

    @property
    def first(self) -> int:
        return self.slide if self.slide is not None else self.slides[0]

    @property
    def last(self) -> int:
        return self.slide if self.slide is not None else self.slides[1]


class SlidesConfig(BaseModel):
    template: Path
    output_name: str = "weekly_{date:%Y%m%d}.pptx"
    slides: list[SlideSpec]

    @model_validator(mode="after")
    def _no_overlap(self) -> "SlidesConfig":
        specs = sorted(self.slides, key=lambda s: s.first)
        for a, b in zip(specs, specs[1:], strict=False):
            if b.first <= a.last:
                raise ValueError(
                    f"スライド番号が重複しています: {a.first}-{a.last} と {b.first}"
                )
        return self

    @classmethod
    def load(cls, path: Path = CONFIG_DIR / "weekly_slides.yaml") -> "SlidesConfig":
        with path.open("r", encoding="utf-8") as f:
            cfg = cls.model_validate(yaml.safe_load(f))
        if not cfg.template.is_absolute():
            cfg.template = PROJECT_ROOT / cfg.template
        return cfg


# ---- スライド操作 --------------------------------------------------------------


def pictures(slide: Slide) -> list[Picture]:
    """スライド上の図を、左上から読む順（上の行から、行内は左から）で返す。"""
    pics = sorted(
        (s for s in slide.shapes if isinstance(s, Picture)), key=lambda p: p.top
    )
    # 上端の差が図の高さの半分未満なら同じ行とみなす
    rows: list[list[Picture]] = []
    for p in pics:
        if rows and p.top - rows[-1][0].top < rows[-1][0].height / 2:
            rows[-1].append(p)
        else:
            rows.append([p])
    return [p for row in rows for p in sorted(row, key=lambda p: p.left)]


def replace_picture(slide: Slide, pic: Picture, image_path: Path) -> None:
    """図の画像を差し替える。縦横比が同じなら枠はそのまま、違えば枠の中に収めて中央に置く。"""
    _, new_rid = slide.part.get_or_add_image_part(str(image_path))
    blip = pic._element.blipFill.find(qn("a:blip"))
    old_rid = blip.get(qn("r:embed"))
    blip.set(qn("r:embed"), new_rid)
    if old_rid != new_rid:
        slide.part.drop_rel(old_rid)  # どこからも参照されなければ古い画像は保存されない
    if any((pic.crop_left, pic.crop_right, pic.crop_top, pic.crop_bottom)):
        pic.crop_left = pic.crop_right = pic.crop_top = pic.crop_bottom = 0.0

    with Image.open(image_path) as im:
        img_ratio = im.width / im.height
    box_ratio = pic.width / pic.height
    if abs(img_ratio / box_ratio - 1) < 0.01:
        return
    left, top, width, height = pic.left, pic.top, pic.width, pic.height
    if img_ratio > box_ratio:  # 横長 → 幅に合わせる
        new_w, new_h = width, round(width / img_ratio)
    else:
        new_w, new_h = round(height * img_ratio), height
    pic.left, pic.top = left + (width - new_w) // 2, top + (height - new_h) // 2
    pic.width, pic.height = new_w, new_h


def duplicate_slide(prs: PresentationType, index: int) -> Slide:
    """index（0始まり）のスライドを複製し、その直後に挿入する。ノートは複製しない。"""
    src = prs.slides[index]
    new = prs.slides.add_slide(src.slide_layout)

    rid_map = {}
    for rid, rel in src.part.rels.items():
        if rel.reltype in (RT.SLIDE_LAYOUT, RT.NOTES_SLIDE):
            continue
        if rel.is_external:
            rid_map[rid] = new.part.relate_to(
                rel.target_ref, rel.reltype, is_external=True
            )
        else:
            rid_map[rid] = new.part.relate_to(rel.target_part, rel.reltype)

    # 図形ツリーは要素ごと差し替えず中身を入れ替える（python-pptx が new.shapes を保持しているため）
    src_cSld, new_cSld = src._element.cSld, new._element.cSld
    if src_cSld.bg is not None:
        new_cSld.insert(0, copy.deepcopy(src_cSld.bg))
    sp_tree = new_cSld.spTree
    for child in list(sp_tree):
        sp_tree.remove(child)
    for child in src_cSld.spTree:
        sp_tree.append(copy.deepcopy(child))
    for el in sp_tree.iter():
        for attr, value in el.attrib.items():
            if attr.startswith(R_NS) and value in rid_map:
                el.set(attr, rid_map[value])

    sld_ids = prs.slides._sldIdLst
    new_id = sld_ids[-1]
    sld_ids.remove(new_id)
    sld_ids.insert(index + 1, new_id)
    return prs.slides[index + 1]


def delete_slide(prs: PresentationType, index: int) -> None:
    """index（0始まり）のスライドを削除する。"""
    sld_ids = prs.slides._sldIdLst
    sld_id = sld_ids[index]
    prs.part.drop_rel(sld_id.rId)
    sld_ids.remove(sld_id)


# ---- テンプレートへの差し込み ------------------------------------------------------


def _fill(slide: Slide, number: int, images: list[Path]) -> None:
    pics = pictures(slide)
    if len(pics) != len(images):
        raise ValueError(
            f"スライド {number}: 図が {len(pics)} 個ありますが、差し込む画像は {len(images)} 枚です"
        )
    for pic, path in zip(pics, images, strict=True):
        replace_picture(slide, pic, path)


def build_slides(
    image_dir: Path,
    output_path: Path,
    config: SlidesConfig,
    log: Callable[[str], None] = print,
) -> Path:
    """image_dir の PNG をテンプレートに差し込んで output_path に保存する。

    スライド番号はテンプレート上の番号（1始まり）。複数ページの図はページ数に合わせて
    範囲内の最後のスライドを複製するか、余ったスライドを削除する。
    """
    prs = Presentation(str(config.template))
    n_slides = len(prs.slides)
    for spec in config.slides:
        if spec.last > n_slides:
            raise ValueError(
                f"テンプレートのスライドは {n_slides} 枚です（指定: {spec.last}）"
            )

    # 後ろのスライドから処理すれば、複製・削除しても前のスライド番号はずれない
    for spec in sorted(config.slides, key=lambda s: s.first, reverse=True):
        if spec.slide is not None:
            paths = [image_dir / name for name in spec.images]
            missing = [p.name for p in paths if not p.exists()]
            if missing:
                raise FileNotFoundError(
                    f"スライド {spec.slide}: 画像がありません: {missing}"
                )
            _fill(prs.slides[spec.slide - 1], spec.slide, paths)
            continue

        pages = sorted(image_dir.glob(spec.pages))
        first, last = spec.slides
        n_template = last - first + 1
        if not pages:
            log(f"スライド {first}-{last}: {spec.pages} がないのでスライドを削除します")
        for _ in range(len(pages) - n_template):
            duplicate_slide(prs, last - 1)
        for _ in range(n_template - len(pages)):
            delete_slide(prs, first - 1 + len(pages))
        for k, path in enumerate(pages):
            _fill(prs.slides[first - 1 + k], first + k, [path])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_path))
    return output_path
