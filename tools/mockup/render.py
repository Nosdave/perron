"""Pixel-exact mockup renderer for the 192x64 Perron board.

Draws into a 192x64 RGB framebuffer with the SAME bitmap fonts (X11 misc-fixed BDF, public
domain) and the SAME icon bitmaps as the firmware, then upscales to an "LED dot" PNG.

Coordinate convention (mirrored in firmware): text y = top row of the CAPITALS.
"""
from __future__ import annotations

import os

from PIL import BdfFontFile, Image, ImageDraw, ImageFont

from icons import ICONS7, ICONS9, ICONS16, PALETTE

W, H = 192, 64
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
DIM = (120, 120, 120)
AMBER = (255, 150, 0)


def _load_bdf(name: str) -> ImageFont.ImageFont:
    pil = os.path.join(FONT_DIR, f"{name}.pil")
    if not os.path.exists(pil):
        with open(os.path.join(FONT_DIR, f"{name}.bdf"), "rb") as fp:
            BdfFontFile.BdfFontFile(fp).save(os.path.join(FONT_DIR, name))
    return ImageFont.load(pil)


# name -> (font, cap_top) ; cap_top = first ink row of capitals inside the glyph cell (measured)
FONTS = {
    "small": (_load_bdf("5x7"), 0),     # caps 6 px, 5 px advance  -> names, labels, minutes
    "mid": (_load_bdf("6x10"), 1),      # caps 7 px, 6 px advance  -> emphasis
    "big": (_load_bdf("9x15B"), 2),     # caps 10 px, 9 px advance -> big minutes / temp
    "dest": (_load_bdf("9x15"), 2),     # caps 10 px regular -> large destinations (iteration 8)
    "clock": (_load_bdf("10x20"), 3),   # caps 13 px, 10 px advance -> clock
}


class Canvas:
    def __init__(self) -> None:
        self.img = Image.new("RGB", (W, H), BLACK)
        self.d = ImageDraw.Draw(self.img)
        self.d.fontmode = "1"

    def rect(self, x, y, w, h, color):
        if w > 0 and h > 0:
            self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=color)

    def hline(self, x, y, w, color):
        self.rect(x, y, w, 1, color)

    def pixel(self, x, y, color):
        if 0 <= x < W and 0 <= y < H:
            self.img.putpixel((x, y), color)

    def width(self, s: str, font="small") -> int:
        return int(self.d.textlength(s, font=FONTS[font][0]))

    def fit(self, s: str, max_w: int, font="small") -> str:
        """Truncate to max_w pixels (firmware does the same, char by char)."""
        if self.width(s, font) <= max_w:
            return s
        while s and self.width(s + ".", font) > max_w:
            s = s[:-1]
        return s.rstrip() + "."

    def text(self, x, y, s, color=WHITE, font="small", align="left", max_w=None):
        f, top = FONTS[font]
        if max_w is not None:
            s = self.fit(s, max_w, font)
        tw = self.width(s, font)
        if align == "right":
            x -= tw
        elif align == "center":
            x -= tw // 2
        self.d.text((x, y - top), s, font=f, fill=color)
        return tw

    def icon(self, x, y, name, size=16, tint=None):
        """size 16 | 9 (weather) | 7 (glyphs). tint: draw every lit pixel in one colour (night)."""
        table = {16: ICONS16, 9: ICONS9, 7: ICONS7}[size]
        for j, r in enumerate(table[name]):
            for i, ch in enumerate(r):
                if ch != ".":
                    self.pixel(x + i, y + j, tint or PALETTE[ch])

    def badge(self, x, y, label, bg, fg, shape="round", w=None, h=10, font="small"):
        """Line badge, caps vertically centred. shape: rect | round | circle-ish(pill)."""
        tw = self.width(label, font)
        w = w or max(tw + 4, h)
        self.rect(x, y, w, h, bg)
        if shape in ("round", "pill"):
            for cx, cy in ((x, y), (x + w - 1, y), (x, y + h - 1), (x + w - 1, y + h - 1)):
                self.pixel(cx, cy, BLACK)
        if shape == "pill":
            for cx, cy in ((x + 1, y), (x + w - 2, y), (x + 1, y + h - 1), (x + w - 2, y + h - 1),
                           (x, y + 1), (x + w - 1, y + 1), (x, y + h - 2), (x + w - 1, y + h - 2)):
                self.pixel(cx, cy, BLACK)
        cap = 6 if font == "small" else 7
        self.text(x + (w - tw + 1) // 2, y + (h - cap) // 2, label, fg, font=font)
        return w

    def save_led(self, path, pitch=6, dot=4):
        out = Image.new("RGB", (W * pitch, H * pitch), (12, 12, 14))
        dr = ImageDraw.Draw(out)
        px = self.img.load()
        r = dot // 2
        for y in range(H):
            for x in range(W):
                c = px[x, y]
                if c == BLACK:
                    c = (28, 28, 30)
                cx, cy = x * pitch + pitch // 2, y * pitch + pitch // 2
                dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
        for sx in (64, 128):
            dr.line([sx * pitch, 0, sx * pitch, H * pitch], fill=(0, 0, 0), width=1)
        out.save(path)
