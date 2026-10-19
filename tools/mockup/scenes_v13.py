"""Iteration 13: SNCB identity on train rows (variants) + blue airport pictogram."""
import os
from PIL import Image, ImageDraw, ImageFont
from render import Canvas, BLACK, WHITE
from scenes import WARM, SEC, CATCH, LEAVE, HERE, fit_words, pager
from scenes_v11 import status_slim
import scenes_v12
from scenes_v12 import row

SNCB = (0x01, 0x6A, 0xB3)
S9 = (0x64, 0xBE, 0x3C)
PLANE = ["..#..", "..#..", ".###.", "#####", "..#..", "..#..", ".###."]
BOVAL = ["..#####..", ".#.....#.", "#..###..#", "#..#..#.#", "#..###..#", "#..#..#.#", "#..###..#", ".#.....#.", "..#####.."]


def glyph(c, x, y, rows, col):
    for j, r in enumerate(rows):
        for i, ch in enumerate(r):
            if ch == "#":
                c.pixel(x + i, y + j, col)


def train_row(c, y, variant):
    # base like iteration 12 (STIB-style row), then the SNCB mark
    scenes_v12.LINES["S9"] = (S9, False, True)
    row(c, y, "S9", "Brussels Airport", 13, 12, True, delay=2, plan="15:58")
    x, yy, w, h = 1, y + 1, 22, 10
    if variant == "A":   # blue frame around the S-line pill
        for i in range(w):
            c.pixel(x + i, yy, SNCB); c.pixel(x + i, yy + h - 1, SNCB)
        for j in range(h):
            c.pixel(x, yy + j, SNCB); c.pixel(x + w - 1, yy + j, SNCB)
    elif variant == "B":  # the cut-off pill corners in SNCB blue
        for px, py in ((0, 0), (1, 0), (0, 1), (w - 1, 0), (w - 2, 0), (w - 1, 1),
                       (0, h - 1), (1, h - 1), (0, h - 2), (w - 1, h - 1), (w - 2, h - 1), (w - 1, h - 2)):
            c.pixel(x + px, yy + py, SNCB)
    elif variant == "C":  # SNCB "B" oval after the badge (white on blue)
        pass
    # destination + blue plane (re-draw over the row text area)
    c.rect(27, y + 1, 96, 10, BLACK)
    dx = 27
    if variant == "C":
        c.rect(27, y + 1, 9, 9, SNCB)
        glyph(c, 27, y + 1, BOVAL, WHITE)
        dx = 39
    d = "Airport"
    c.text(dx, y + 3, d, WARM, font="mid")
    px = dx + c.width(d, "mid") + 3
    glyph(c, px, y + 3, PLANE, (0x41, 0x9B, 0xF5))
    c.text(px + 8, y + 4, "15:58", SEC)


def scene(variant):
    def f(c):
        status_slim(c)
        row(c, 9, "92", "Schaerbeek", 5, 1, True, second=15)
        row(c, 20, "92", "Fort-Jaco", 8, 1, True, second=17)
        row(c, 31, "60", "Ambiorix", 11, 4, True, second=25)
        train_row(c, 42, variant)
        pager(c, "news", "VRT: Nieuwe tramlijn in Brussel")
    return f


if __name__ == "__main__":
    tiles = []
    for v, label in (("A", "A  Blauer SNCB-Rahmen um das Liniensymbol"),
                     ("B", "B  Abgeschnittene Ecken in SNCB-Blau"),
                     ("C", "C  SNCB-Oval-B vor dem Ziel")):
        c = Canvas(); scene(v)(c); p = os.path.join(HERE, "out", f"v13_{v}.png"); c.save_led(p, pitch=5, dot=4)
        tiles.append((label, Image.open(p)))
    w, h = tiles[0][1].size
    out = Image.new("RGB", (w, len(tiles) * (h + 34)), (20, 20, 22))
    d = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("segoeui.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    for i, (label, im) in enumerate(tiles):
        d.text((8, i * (h + 34) + 4), label, fill=(225, 225, 225), font=font)
        out.paste(im, (0, i * (h + 34) + 32))
    out.save(os.path.join(HERE, "out", "v13_sheet.png"))
    print("v13")
