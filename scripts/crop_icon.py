#!/usr/bin/env python3
"""Remove black borders from RaceOricalIcon.png and scale the logo up to fill the square."""
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent.parent
ICON_PATH = BASE / "Photos" / "RaceOricalIcon.png"
OUT_PATH = BASE / "Photos" / "RaceOricalIcon.png"  # overwrite in place

# Trim this fraction from each edge to remove black border; then scale center up to fill square
TRIM = 0.18

def main():
    if not ICON_PATH.exists():
        print(f"Not found: {ICON_PATH}")
        return
    im = Image.open(ICON_PATH).convert("RGBA")
    w, h = im.size

    # Remove black borders: keep center only
    dx = int(w * TRIM)
    dy = int(h * TRIM)
    left, top = dx, dy
    right, bottom = w - dx, h - dy
    cropped = im.crop((left, top, right, bottom))
    cw, ch = cropped.size

    # Scale the logo UP to fill 512x512 (bigger image, no borders)
    target = 512
    scale = max(target / cw, target / ch)
    new_w = int(cw * scale)
    new_h = int(ch * scale)
    resized = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)
    x0 = max(0, (new_w - target) // 2)
    y0 = max(0, (new_h - target) // 2)
    out = resized.crop((x0, y0, x0 + target, y0 + target))
    out.save(OUT_PATH, "PNG")
    print(f"Trimmed {TRIM*100:.0f}% border, scaled up to fill {target}x{target}. Saved to {OUT_PATH}")

if __name__ == "__main__":
    main()
