"""Commute by public transport (2 slots): info-line text + panel card with the route as line badges."""
import os
from PIL import Image, ImageDraw, ImageFont
from render import Canvas, BLACK, WHITE
from scenes import WARM, SEC, CATCH, LEAVE, TAGS, HERE, pager
import scenes_v12
from scenes_cards_v2 import hero_panel, ACC, dim

LINES = {"81": (0xE4, 0x3C, 0x2E), "2": (0xED, 0x6C, 0x23), "1": (0xB5, 0x37, 0x8C), "71": (0xF2, 0x9D, 0xC3), "S9": (0x64, 0xBE, 0x3C)}


def mini(c, x, y, line, dark=False):
    w = max(9, c.width(line, "tiny") + 3)
    c.rect(x, y, w, 7, LINES[line])
    for px, py in ((0, 0), (w - 1, 0), (0, 6), (w - 1, 6)):
        c.pixel(x + px, y + py, BLACK)
    c.text(x + (w - c.width(line, "tiny") + 1) // 2, y + 1, line, BLACK if dark else WHITE, font="tiny")
    return w


def panel(c):
    hero_panel(c)                  # departures left (4 rows) + pager, as on the board
    c.rect(128, 0, 64, 55, BLACK)  # replace the right panel
    a = ACC["b"]
    c.icon(130, 1, "tram", size=7, tint=a) if False else None
    c.rect(130, 1, 2, 7, a)
    c.text(134, 1, "Büro", a)
    c.text(189, 11, "33", WARM, font="clock", align="right")
    c.text(189, 27, "min", dim(a, 0.8), align="right")
    c.text(130, 13, "los", SEC, font="tiny")
    c.text(130, 20, "21:01", CATCH)
    x = 130
    for ln in ("81", "2", "1"):
        x += mini(c, x, 38, ln) + 2
    c.text(130, 48, "an 21:35", SEC, font="tiny")


def pager_scene(c):
    scenes_v12.scene(True)(c)
    c.rect(0, 55, 192, 9, BLACK)
    c.rect(1, 56, 2, 6, TAGS["commute"])
    c.text(6, 56, "Büro 33' · los 21:01 · 92 > M2 > M1", (0xB0, 0xA9, 0x9E))


if __name__ == "__main__":
    tiles = []
    for n, label, fn in (("cm_panel", "Panel-Karte: Pendeln (Bus & Bahn) – Dauer, wann losgehen, Linien als Mini-Badges", panel),
                         ("cm_pager", "Oder nur als Infozeile", pager_scene)):
        c = Canvas(); fn(c); p = os.path.join(HERE, "out", f"{n}.png"); c.save_led(p, pitch=5, dot=4)
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
    out.save(os.path.join(HERE, "out", "commute_sheet.png"))
    print("ok")
