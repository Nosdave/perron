"""Renders the README/docs images with neutral sample data (city-centre lines, no personal stops).

  python tools/mockup/readme_images.py   -> docs/img/layouts.png
"""
import os
from PIL import Image
from render import Canvas, WHITE
import scenes
import scenes_v8 as v8

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# neutral sample lines (official STIB/SNCB GTFS colours)
scenes.GTFS.update({
    "1": ((0xB5, 0x37, 0x8C), WHITE, "metro"),
    "5": ((0xF6, 0xA9, 0x0B), WHITE, "metro"),
    "81": ((0x4C, 0x8B, 0x33), WHITE, "tram"),
    "71": ((0x4C, 0x8B, 0x33), WHITE, "bus"),
    "IC": ((0x01, 0x6A, 0xB3), WHITE, "train"),
})


def premium(c):
    v8.status(c)
    for i, (ln, d, m) in enumerate([("1", "Stockel", [2, 7]), ("5", "Erasme", [4, 11])]):
        y = 11 + i * 14
        v8.badge(c, 1, y + 1, ln)
        c.text(29, y + 1, d, scenes.WARM, font="dest")
        v8.mins(c, 166, y + 1, m[0], 2)
        c.text(191, y + 4, f"{m[1]}'", scenes.SEC, align="right")
    y = 41
    v8.badge(c, 1, y + 1, "81")
    v8.walk(c, 29, y + 3, 4)
    v8.mins(c, 68, y + 1, 9, 4)
    c.text(88, y + 4, "21'", scenes.SEC, align="right")
    v8.badge(c, 98, y + 1, "IC")
    v8.walk(c, 126, y + 3, 8)
    v8.mins(c, 166, y + 1, 17, 8)
    c.text(191, y + 4, "+2", scenes.SEC, align="right")
    v8.pager(c, 56, "wx", "Rain 17:40-18:20, light")


def four(c):
    c.text(1, 1, "17:12", scenes.WARM)
    c.text(34, 1, "Mo 19.10.", scenes.SEC)
    c.icon(130, 0, "rainy", size=9)
    c.text(191, 1, "11°  8/13°", scenes.WARM, align="right")
    rows = [("1", "Stockel", [2, 7], 2), ("5", "Erasme", [4, 11], 2), ("81", "Montgomery", [9, 21], 4),
            ("IC", "Antwerpen", [17], 8)]
    for i, (ln, d, m, w) in enumerate(rows):
        y = 8 + i * 12
        v8.badge(c, 1, y + 1, ln, w=22, h=10)
        c.text(27, y + 3, scenes.fit_words(c, d, 94, "mid") or d[:15], scenes.WARM, font="mid")
        if w > 1:
            v8.walk(c, 124, y + 2, w)
        v8.mins(c, 166, y + 1, m[0], w)
        if len(m) > 1:
            c.text(191, y + 3, f"{m[1]}'", scenes.SEC, align="right")
    v8.pager(c, 56, "cal", "18:30 Team dinner")


def alert(c):
    scenes.P0(c)


if __name__ == "__main__":
    ims = []
    out_dir = os.path.join(ROOT, "docs", "img")
    os.makedirs(out_dir, exist_ok=True)
    for fn in (premium, four, alert):
        c = Canvas(); fn(c)
        p = os.path.join(out_dir, f"_{fn.__name__}.png"); c.save_led(p, pitch=5, dot=3); ims.append(Image.open(p))
    W = ims[0].width
    sheet = Image.new("RGB", (W, sum(i.height for i in ims) + 2 * 10), (16, 16, 18))
    y = 0
    for i in ims:
        sheet.paste(i, (0, y)); y += i.height + 10
    sheet.save(os.path.join(out_dir, "layouts.png"))
    for fn in (premium, four, alert):
        os.remove(os.path.join(out_dir, f"_{fn.__name__}.png"))
    print("docs/img/layouts.png")
