from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(r"D:\SmartOpsAgent\docs\competition")
HTML = ROOT / "technical-document.html"
PDF = ROOT / "technical-document.pdf"


def validate_html() -> None:
    text = HTML.read_text(encoding="utf-8")
    page_count = len(re.findall(r'<section class="page(?:\s|\")', text))
    image_paths = re.findall(r'<img\s+[^>]*src="([^"]+)"', text)
    footers = re.findall(r'<span>(\d{2}) / 18</span>', text)
    tables = re.findall(r"<table\b.*?</table>", text, flags=re.S)
    assert page_count == 18, f"HTML page sections: {page_count}"
    assert len(image_paths) == 12, f"image references: {len(image_paths)}"
    assert footers == [f"{i:02d}" for i in range(1, 19)], footers
    assert all("<colgroup>" in table for table in tables), "table without colgroup"
    assert not re.search(r"BATCH_|TODO|undefined", text), "unfinished placeholder"
    for relative in image_paths:
        assert not relative.startswith(("http:", "https:", "/")), relative
        target = HTML.parent / relative
        assert target.is_file() and target.stat().st_size > 0, f"missing image: {target}"
    for required in (
        "3589.6 ms", "4522.5 ms", "0.4762", "0.7619", "0.5000", "0.4286",
        "733", "774", "622", "38,998", "36,863", "22,048", "M05 真人盲评",
        "NOT_RUN", "DRAFT", "AES-256-GCM", "approval_required=true",
    ):
        assert required in text, f"missing fact: {required}"
    for stale in ("48 模块", "3590ms", "4523ms", "敢把生产环境", "兼顾可演示与可生产"):
        assert stale not in text, f"stale or overclaiming phrase: {stale}"
    print(f"HTML OK: {page_count} pages, {len(image_paths)} images, {len(tables)} tables")
    print(f"HTML bytes: {HTML.stat().st_size}")


def validate_pdf(render: bool) -> None:
    import pymupdf

    with pymupdf.open(PDF) as document:
        print(f"PDF pages: {document.page_count}; bytes: {PDF.stat().st_size}")
        assert document.page_count == 18, f"unexpected PDF pages: {document.page_count}"
        for index, page in enumerate(document, start=1):
            text = page.get_text("text", sort=True).strip()
            images = len(page.get_images(full=True))
            width, height = page.rect.width, page.rect.height
            print(f"p{index:02d}: chars={len(text):4d}, images={images}, size={width:.1f}x{height:.1f}")
            assert len(text) > 100, f"possible blank page: {index}"
            assert 590 < width < 600 and 838 < height < 845, f"non-A4 page: {index}"
            assert f"{index:02d} / 18" in text, f"missing footer: {index}"
        if render:
            from PIL import Image, ImageDraw

            output = ROOT / "_techdoc_review"
            output.mkdir(exist_ok=True)
            rendered = []
            for index, page in enumerate(document, start=1):
                target = output / f"page-{index:02d}.png"
                page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).save(target)
                rendered.append(target)
            for group in range(3):
                sheet = Image.new("RGB", (900, 1932), "#cbd5df")
                draw = ImageDraw.Draw(sheet)
                for slot, path in enumerate(rendered[group * 6:(group + 1) * 6]):
                    image = Image.open(path).convert("RGB")
                    image.thumbnail((438, 620), Image.Resampling.LANCZOS)
                    x = 8 + (slot % 2) * 450
                    y = 8 + (slot // 2) * 640
                    sheet.paste(image, (x, y))
                    draw.text((x, y + 622), path.stem, fill="#173042")
                sheet.save(output / f"contact-{group + 1}.jpg", quality=92)
            print(f"Rendered review files: {output}")
    print("PDF OK: 18 A4 pages, no low-text blank pages, all footers present")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", action="store_true")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    if args.pdf:
        validate_pdf(args.render)
    else:
        validate_html()
