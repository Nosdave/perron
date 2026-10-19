"""Iteration 8 after the 2nd multi-agent design review: no rotating rows; fixed grid.

  A  four equal rows (usability review)   B  two hero rows for the home tram + split row (design review)
"""
import os
from PIL import Image
from render import Canvas, BLACK, WHITE
import scenes
from scenes import GTFS, WARM, SEC, CATCH, LEAVE, TAGS, fit_words, HERE

RED_PROBLEM = (0xFF, 0x3B, 0x1F)


def badge(c, x, y, line, w=24, h=12, font="mid"):
    bg, fg, mode = GTFS[line]
    cap = 6 if font == "small" else 7
    if fg == BLACK:
        c.rect(x, y, w, h, bg); c.rect(x + 1, y + 1, w - 2, h - 2, BLACK)
        for cx, cy in ((x, y), (x + w - 1, y), (x, y + h - 1), (x + w - 1, y + h - 1)): c.pixel(cx, cy, BLACK)
        c.text(x + (w - c.width(line, font) + 1) // 2, y + (h - cap) // 2, line, bg, font=font)
    else:
        c.badge(x, y, line, bg, fg, shape="pill" if mode == "train" else "round", w=w, h=h, font=font)


def walk(c, x, y, n):  # fixed column, glyph + minutes (only for stops further than 1 min)
    c.icon(x, y, "walk", size=7, tint=(0x9A, 0x94, 0x8C))
    c.text(x + 7, y + 1, str(n), SEC)


def mins(c, x_right, y, m, walk_min, font="big"):
    col = LEAVE if m <= walk_min else CATCH
    c.text(x_right, y, str(m), col, font=font, align="right")
    c.text(x_right + 1, y, "'", col)


def status(c, small=False):
    if small:
        c.text(1, 1, "22:07", WARM)
        c.icon(150, 0, "cloudy", size=7 if False else 9) if False else None
        c.text(191, 1, "11°  8-13", SEC, align="right")
        c.text(40, 1, "Sa 18.10.", SEC)
        return
    c.text(1, 2, "22:07", WARM, font="mid")
    c.text(36, 3, "Sa 18.10.", (0x9A, 0x94, 0x8C))
    c.icon(140, 1, "rainy", size=9)
    c.text(168, 2, "11°", WARM, font="mid", align="right")
    c.text(191, 3, "8-13", SEC, align="right")


def pager(c, y, tag, text):
    c.rect(1, y + 1, 2, 6, TAGS[tag])
    c.text(6, y + 1, text, (0xB0, 0xA9, 0x9E))


def A(c):  # 4 equal rows, 8 px status, 8 px footer
    c.text(1, 1, "22:07", WARM)
    c.text(34, 1, "Sa 18.10.", SEC)
    c.icon(150, 0, "rainy", size=9) if False else None
    c.text(191, 1, "11°  8-13°", SEC, align="right")
    rows = [("81", "Montgomery", [3, 16], 1), ("81", "Marius Renard", [22, 26], 1),
            ("4", "Gare du Nord", [7, 19], 5), ("S5", "Mechelen", [14], 12)]
    for i, (ln, d, m, w) in enumerate(rows):
        y = 8 + i * 12
        badge(c, 1, y + 1, ln, w=22, h=10)
        c.text(27, y + 3, d, WARM, font="mid")
        if w > 1:
            walk(c, 124, y + 2, w)
        mins(c, 166, y + 1, m[0], w)
        if ln == "S5":
            c.text(191, y + 3, "+3", RED_PROBLEM, align="right")
        elif len(m) > 1:
            c.text(191, y + 3, f"{m[1]}'", SEC, align="right")
    pager(c, 56, "wx", "Regen 22:40-23:30, leicht")


def B(c):  # hero 92 rows (big destinations) + split row 60 | S5
    status(c)
    for i, (d, m) in enumerate([("Montgomery", [3, 16]), ("Marius Renard", [22, 26])]):
        y = 11 + i * 14
        badge(c, 1, y + 1, "81")
        c.text(29, y + 1, d, WARM, font="dest")
        mins(c, 166, y + 1, m[0], 1)
        c.text(191, y + 4, f"{m[1]}'", SEC, align="right")
    y = 41
    badge(c, 1, y + 1, "4")
    walk(c, 29, y + 3, 5)
    mins(c, 68, y + 1, 7, 5)
    c.text(88, y + 4, "19'", SEC, align="right")
    badge(c, 98, y + 1, "S5")
    walk(c, 126, y + 3, 12)
    mins(c, 166, y + 1, 14, 12)
    c.text(191, y + 4, "+3", SEC, align="right")
    pager(c, 56, "wx", "Regen 22:40-23:30, leicht")


def B_night(c):  # same layout late evening: 60 has no service within the preview
    status(c)
    for i, (d, m) in enumerate([("Montgomery", [12, 33]), ("Marius Renard", [22, 51])]):
        y = 11 + i * 14
        badge(c, 1, y + 1, "81")
        c.text(29, y + 1, d, WARM, font="dest")
        mins(c, 166, y + 1, m[0], 1)
        c.text(191, y + 4, f"{m[1]}'", SEC, align="right")
    y = 41
    badge(c, 1, y + 1, "4")
    walk(c, 29, y + 3, 5)
    c.text(88, y + 3, "05:42", SEC, font="mid", align="right")
    badge(c, 98, y + 1, "S5")
    walk(c, 126, y + 3, 12)
    c.text(191, y + 3, "06:12", SEC, font="mid", align="right")
    pager(c, 56, "cal", "Mo 08:30 Standup")


if __name__ == "__main__":
    ims = []
    for n, fn in (("v8_A", A), ("v8_B", B), ("v8_B_night", B_night)):
        c = Canvas(); fn(c); p = os.path.join(HERE, "out", f"{n}.png"); c.save_led(p); ims.append(Image.open(p))
    out = Image.new("RGB", (ims[0].width, sum(i.height + 14 for i in ims)), (255, 255, 255))
    y = 0
    for i in ims:
        out.paste(i, (0, y)); y += i.height + 14
    out.save(os.path.join(HERE, "out", "v8_sheet.png"))
    print("ok")


# ---- iteration 9: split cells with destinations (4x6), train cell in SNCB board style ----
SNCB_BG = (0x0A, 0x1E, 0x46)      # SNCB departure-board navy
SNCB_YEL = (0xFF, 0xD2, 0x00)     # SNCB yellow for changes/delays


def split_cell(c, x0, x1, y, line, dest, m, walk_min, delay=0, sncb=False):
    """Compact cell: badge 18 | destination (4x6) | walk (glyph + 4x6) | minutes 9x15B | [delay]."""
    if sncb:
        c.rect(x0 - 2, y, x1 - x0 + 3, 14, SNCB_BG)
    badge(c, x0, y + 1, line, w=18)
    right = x1
    if delay:
        right -= c.text(x1, y + 5, f"+{delay}", SNCB_YEL, font="tiny", align="right") + 2
    mr = right - 3                                # minutes right edge, apostrophe after
    mins(c, mr, y + 1, m, walk_min)
    mw = c.width(str(m), "big")
    wt = str(walk_min)
    wx = mr - mw - 3 - (6 + c.width(wt, "tiny"))
    c.icon(wx, y + 3, "walk", size=7, tint=(0x9A, 0x94, 0x8C))
    c.text(wx + 6, y + 4, wt, SEC, font="tiny")
    dest_w = wx - (x0 + 21) - 1
    d = scenes.fit_words(c, dest, dest_w, "tiny") or dest[: dest_w // 4]
    c.text(x0 + 21, y + 4, d, WHITE if sncb else scenes.WARM, font="tiny")


def B9(c):
    status(c)
    for i, (d, m) in enumerate([("Montgomery", [3, 16]), ("Marius Renard", [22, 26])]):
        y = 11 + i * 14
        badge(c, 1, y + 1, "81")
        c.text(29, y + 1, scenes.fit_words(c, d, 105, "dest") or d, scenes.WARM, font="dest")
        mins(c, 166, y + 1, m[0], 1)
        c.text(191, y + 4, f"{m[1]}'", scenes.SEC, align="right")
    split_cell(c, 1, 82, 41, "4", "Nord", 7, 5)
    split_cell(c, 88, 191, 41, "S5", "Mechelen", 14, 12, delay=3, sncb=True)
    pager(c, 56, "wx", "Rain 17:40-18:20, light")


if __name__ == "__main__":
    c = Canvas(); B9(c); c.save_led(os.path.join(HERE, "out", "v9_B.png"))
    print("v9")
