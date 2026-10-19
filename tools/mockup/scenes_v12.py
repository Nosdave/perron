"""Iteration 12: light lines filled (original) vs outline; train delay as red +N' and scheduled
time after the destination; rows without a catchable vehicle show its minutes in grey."""
import os
from PIL import Image, ImageDraw, ImageFont
from render import Canvas, BLACK, WHITE
from scenes import WARM, SEC, CATCH, LEAVE, HERE, fit_words, pager
from scenes_v11 import status_slim

LINES = {"92": ((0xE4, 0x3C, 0x2E), False, False), "60": ((0xF2, 0x9D, 0xC3), True, False),
         "S5": ((0xFF, 0xCD, 0x00), True, True), "S9": ((0x64, 0xBE, 0x3C), False, True)}
WALK = (0x9A, 0x94, 0x8C)


def badge(c, x, y, line, filled, w=22, h=10):
    bg, dark, train = LINES[line]
    c.rect(x, y, w, h, bg)
    outline = dark and not filled
    if outline:
        c.rect(x + 1, y + 1, w - 2, h - 2, BLACK)
    pts = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    if train:
        pts += [(1, 0), (w - 2, 0), (1, h - 1), (w - 2, h - 1), (0, 1), (w - 1, 1), (0, h - 2), (w - 1, h - 2)]
    for px, py in pts:
        c.pixel(x + px, y + py, BLACK)
    if outline and train:
        for px, py in ((1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)):
            c.pixel(x + px, y + py, bg)
    col = bg if outline else (BLACK if dark else WHITE)
    c.text(x + (w - c.width(line, "mid") + 1) // 2, y + 1, line, col, font="mid")


def row(c, y, line, dest, m, walk, filled, second=None, delay=0, plan=None, missed=None):
    badge(c, 1, y + 1, line, filled)
    if walk > 1:
        c.icon(124, y + 2, "walk", size=7, tint=WALK)
        c.text(131, y + 3, str(walk), SEC)
    if m is None:
        c.text(191, y + 3, f"{missed}'" if missed is not None else "-", SEC, font="mid", align="right")
    else:
        col = LEAVE if m <= walk else CATCH
        c.text(166, y + 1, str(m), col, font="big", align="right")
        c.text(167, y + 1, "'", col)
        if delay:
            c.text(191, y + 3, f"+{delay}'", LEAVE, align="right")
        elif second:
            c.text(191, y + 3, f"{second}'", SEC, align="right")
    d = fit_words(c, dest, 90 - (30 if plan else 0), "mid") or ""
    c.text(27, y + 3, d, WARM, font="mid")
    if plan:
        c.text(27 + c.width(d, "mid") + 4, y + 4, plan, SEC)


def scene(filled):
    def f(c):
        status_slim(c)
        rows = [("92", "Schaerbeek", 5, 1, dict(second=15)), ("92", "Fort-Jaco", 8, 1, dict(second=17)),
                ("60", "Ambiorix", None, 4, dict(missed=2)), ("S5", "Mechelen", 19, 12, dict(delay=3, plan="13:58"))]
        for i, (l, d, m, w, kw) in enumerate(rows):
            row(c, 9 + i * 11, l, d, m, w, filled, **kw)
        pager(c, "wx", "Regen ab 17:40 (leicht), bis ca. 18:20")
    return f


if __name__ == "__main__":
    tiles = []
    for name, label, fn in (("v12_filled", "A  Helle Linien gefüllt (wie Original, schwarze Schrift)", scene(True)),
                            ("v12_outline", "B  Helle Linien nur Kontur (bisher)", scene(False))):
        c = Canvas(); fn(c); p = os.path.join(HERE, "out", f"{name}.png"); c.save_led(p, pitch=5, dot=4)
        tiles.append((label, Image.open(p)))
    w, h = tiles[0][1].size
    out = Image.new("RGB", (w, 2 * (h + 34)), (20, 20, 22))
    d = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("segoeui.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    for i, (label, im) in enumerate(tiles):
        d.text((8, i * (h + 34) + 4), label, fill=(225, 225, 225), font=font)
        out.paste(im, (0, i * (h + 34) + 32))
    out.save(os.path.join(HERE, "out", "v12_sheet.png"))
    print("v12")
