"""Iteration 11: 4-row layout really shows 4 rows (11 px pitch), trains formatted exactly like
STIB rows - only the line badge follows the SNCB style (pill, S-line colour / SNCB blue)."""
import os
from PIL import Image
from render import Canvas, BLACK, WHITE
import scenes
from scenes import GTFS, WARM, SEC, CATCH, LEAVE, HERE, fit_words, badge4, pager
import scenes_v8

GTFS.update({"92": ((0xE4, 0x3C, 0x2E), WHITE, "tram"), "60": ((0xF2, 0x9D, 0xC3), BLACK, "bus"),
             "S9": ((0x64, 0xBE, 0x3C), WHITE, "train")})
DELAY_BG = (0xC8, 0x1E, 0x14)
WALK = (0x9A, 0x94, 0x8C)


def status_slim(c):
    c.text(1, 1, "13:42", WARM)
    c.text(34, 1, "Mo 19.10.", SEC)
    c.icon(130, 0, "partlycloudy", size=9)
    c.text(191, 1, "12°  8/15°", WARM, align="right")


def row4(c, y, line, dest, mins, walk, second=None, delay=0):
    badge4(c, 1, y + 1, line, h=10)
    if walk > 1:
        c.icon(124, y + 2, "walk", size=7, tint=WALK)
        c.text(131, y + 3, str(walk), SEC)
    if mins is None:
        c.text(191, y + 3, "14:05", SEC, font="mid", align="right")
        col = SEC
    else:
        col = LEAVE if mins <= walk else CATCH
        c.text(166, y + 1, str(mins), col, font="big", align="right")
        c.text(167, y + 1, "'", col)
        if delay:
            w = c.width(f"+{delay}", "tiny") + 3
            c.rect(191 - w + 1, y + 3, w, 7, DELAY_BG)
            c.text(190, y + 4, f"+{delay}", WHITE, font="tiny", align="right")
        elif second:
            c.text(191, y + 4, f"{second}'", SEC, align="right")
    c.text(27, y + 3, fit_words(c, dest, 124 - 30, "mid") or "", WARM if mins is not None else SEC, font="mid")


def FOUR(c):
    status_slim(c)
    rows = [("92", "Schaerbeek", 5, 1, 15, 0), ("92", "Fort-Jaco", 8, 1, 17, 0),
            ("60", "Ambiorix", None, 4, None, 0), ("S9", "Landen", 19, 12, None, 3)]
    for i, (l, d, m, w, s2, dl) in enumerate(rows):
        row4(c, 9 + i * 11, l, d, m, w, s2, dl)
    pager(c, "wx", "Regen ab 17:40 (leicht), bis ca. 18:20")


def PREMIUM(c):
    scenes_v8.status(c)
    for i, (d, m, s2) in enumerate([("Schaerbeek", 5, 15), ("Fort-Jaco", 8, 17)]):
        y = 11 + i * 14
        scenes_v8.badge(c, 1, y + 1, "92")
        c.text(29, y + 1, d, WARM, font="dest")
        scenes_v8.mins(c, 166, y + 1, m, 1)
        c.text(191, y + 4, f"{s2}'", SEC, align="right")
    scenes_v8.split_cell(c, 1, 82, 41, "60", "Ambiorix", 11, 4)
    scenes_v8.split_cell(c, 88, 191, 41, "S9", "Landen", 19, 12, delay=0, sncb=False)
    pager(c, "wx", "Regen ab 17:40 (leicht), bis ca. 18:20")


if __name__ == "__main__":
    ims = []
    for n, fn in (("v11_four", FOUR), ("v11_premium", PREMIUM)):
        c = Canvas(); fn(c); p = os.path.join(HERE, "out", f"{n}.png"); c.save_led(p, pitch=5, dot=4); ims.append(Image.open(p))
    out = Image.new("RGB", (ims[0].width, sum(i.height + 16 for i in ims)), (20, 20, 22))
    y = 0
    for i in ims:
        out.paste(i, (0, y)); y += i.height + 16
    out.save(os.path.join(HERE, "out", "v11_sheet.png"))
    print("v11")
