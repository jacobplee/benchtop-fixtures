"""Web-size renders and the contact sheet: renders/<name>.jpg and renders/overview.jpg.

    python render/overview.py

Reads the full-size Blender masters from renders/_work/ (not committed) and writes the JPEGs
that the README shows. Needs Pillow. Captions come from exports/report.json, so the sizes
shown are measured.
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
REN = ROOT / "renders"
WORK = REN / "_work"
WEB_W, WEB_H, QUALITY = 1200, 900, 85
TILES = [
    ("breadboard_adapter", "Breadboard adapter", "1/4-20 slots on a 1 in grid, M4 device pattern"),
    ("gridfinity_bin", "Gridfinity bin", "2 x 1 cells, 3 units, stacking lip"),
    ("tube_cradle", "Tube cradle", "three barrels, saddles at 0.2232 L"),
    ("cable_clip_screw", "Cable clip", "10 mm OD, snap opening, M3 screw tab"),
    ("instrument_riser", "Instrument riser", "four pad recesses, M4 centre screw"),
    ("gridfinity_bin_cylinder_pocket", "Gridfinity bin, pocket", "1 x 1 cell, 30 mm cylinder pocket"),
]
TILE_W, TILE_H, CAP_H, PAD = 800, 600, 92, 0
BG = (236, 236, 237)
INK, SUB = (34, 38, 44), (98, 104, 112)


def font(size, bold=False):
    for path, idx in (("/System/Library/Fonts/Helvetica.ttc", 1 if bold else 0),
                      ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
                       "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0)):
        try:
            return ImageFont.truetype(path, size, index=idx)
        except OSError:
            continue
    return ImageFont.load_default()


def save_jpeg(im, out):
    im.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    print(f"wrote {out} {im.size}")


def web_renders():
    for src in sorted(WORK.glob("*.png")):
        if src.stem.endswith("_preview"):
            continue
        im = Image.open(src).convert("RGB").resize((WEB_W, WEB_H), Image.LANCZOS)
        save_jpeg(im, REN / f"{src.stem}.jpg")


def main():
    web_renders()
    rep = json.loads((ROOT / "exports" / "report.json").read_text())["presets"]
    cols, rows = 3, 2
    sheet = Image.new("RGB", (cols * TILE_W, rows * (TILE_H + CAP_H)), BG)
    d = ImageDraw.Draw(sheet)
    f1, f2 = font(30, bold=True), font(23)
    for i, (name, title, sub) in enumerate(TILES):
        im = Image.open(WORK / f"{name}.png").convert("RGB")
        w, h = im.size
        cw, ch = int(w * 0.82), int(h * 0.82)                    # trim the empty sweep around the part
        im = im.crop(((w - cw) // 2, (h - ch) // 2, (w + cw) // 2, (h + ch) // 2)).resize((TILE_W, TILE_H), Image.LANCZOS)
        x, y = (i % cols) * TILE_W, (i // cols) * (TILE_H + CAP_H)
        sheet.paste(im, (x, y))
        sx, sy, sz = rep[name]["info"]["size_mm"]
        d.text((x + 28, y + TILE_H + 14), title, font=f1, fill=INK)
        d.text((x + 28, y + TILE_H + 52), f"{sub}  |  {sx:.0f} x {sy:.0f} x {sz:.0f} mm", font=f2, fill=SUB)
    save_jpeg(sheet, REN / "overview.jpg")


if __name__ == "__main__":
    main()
