"""Cards v2 (feedback on the real LEDs): accent colours, info line (pager) keeps running under
every card, panel mode keeps 4 departure rows + pager."""
import os
from PIL import Image, ImageDraw, ImageFont
from render import Canvas, BLACK, WHITE
from scenes import WARM, SEC, CATCH, LEAVE, TAGS, fit_words, HERE, badge4, pager, status_bar
import scenes_v12

ACC = {"y": (0xFF, 0xC4, 0x00), "g": (0x4F, 0xD1, 0x8B), "b": (0x41, 0xBD, 0xF5), "v": (0xB4, 0x8C, 0xFF)}
W4 = (0x40, 0x3A, 0x33)


def dim(c, k=0.45):
    return tuple(int(v * k) for v in c)


def kpi_full(c):
    status_bar(c)
    cells = [("sun", "PV jetzt", "0.2", "kW", None, "y"), ("sun", "Heute", "1.9", "kWh", None, "y"),
             ("battery", "Akku", "11", "%", 11, "g")]
    for k, (ic, lab, val, unit, pct, a) in enumerate(cells):
        x = k * 64 + 3
        col = ACC[a]
        c.icon(x, 13, ic, size=7, tint=col)
        c.text(x + 9, 13, lab, col)
        vw = c.text(x, 24, val, WARM, font="clock")
        c.text(x + vw + 2, 31, unit, dim(col, 0.8))
        c.rect(x, 48, 56, 2, W4)
        if pct is not None:
            c.rect(x, 48, max(2, 56 * pct // 100), 2, col)
    pager(c, "news", "Brussels Times: Metro line 3 works delayed until 2027")


def hero_panel(c):
    rows = [("92", "Schaerbeek", 0, 1), ("92", "Fort-Jaco", 5, 1), ("60", "Ambiorix", None, 4), ("S9", "Landen", 15, 12)]
    c.text(1, 1, "14:56", WARM)
    c.text(34, 1, "Mo 19.10.", SEC)
    for i, (l, d, m, w) in enumerate(rows):
        y = 9 + i * 11
        scenes_v12.badge(c, 1, y + 1, l, True)
        if m is None:
            c.text(126, y + 3, "6'", SEC, font="mid", align="right")
        elif m == 0:
            from scenes import arrows_now
            arrows_now(c, 126, y, LEAVE)
        else:
            col = LEAVE if m <= w else CATCH
            c.text(119, y + 1, str(m), col, font="big", align="right")
            c.text(120, y + 1, "'", col)
        c.text(27, y + 3, fit_words(c, d, 70, "mid") or "", WARM, font="mid")
    c.rect(127, 0, 1, 64, BLACK)
    a = ACC["b"]
    c.rect(130, 1, 2, 7, a)
    c.text(134, 1, "Büro David", a)
    c.icon(130, 14, "car", size=16, tint=a)
    c.text(189, 14, "15", WARM, font="clock", align="right")
    c.text(189, 30, "min", dim(a, 0.8), align="right")
    c.text(130, 40, "via Avenue", SEC, font="tiny")
    c.text(130, 47, "Louise", SEC, font="tiny")
    # pager continues under the departures
    c.rect(1, 56, 2, 6, TAGS["news"])
    c.text(6, 56, "Brussels Times: Metro", (0xB0, 0xA9, 0x9E))


def washer_full(c):
    status_bar(c)
    a = ACC["v"]
    c.icon(4, 13, "washer", 16, tint=a)
    c.text(26, 14, "Waschen", WARM, font="dest")
    c.text(185, 13, "42", WARM, font="big", align="right")
    c.text(186, 13, "'", WARM)
    n = (190 - 26 + 2) // 4
    for k in range(n):
        c.rect(26 + k * 4, 32, 3, 4, a if k < n * 63 // 100 else W4)
    c.text(26, 41, "Spülen", dim(a, 0.9))
    c.text(190, 41, "fertig 14:49", WARM, align="right")
    pager(c, "wx", "Regen ab 17:40 (leicht), bis ca. 18:20")


if __name__ == "__main__":
    tiles = []
    for n, label, fn in (("c2_kpi", "KPI-Karte: Farbe je Feld, Infozeile läuft weiter", kpi_full),
                         ("c2_panel", "Panel-Karte: Abfahrten bleiben (4 Zeilen) + Infozeile", hero_panel),
                         ("c2_washer", "Fortschritt mit Akzentfarbe", washer_full)):
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
    out.save(os.path.join(HERE, "out", "cards_v2_sheet.png"))
    print("ok")
