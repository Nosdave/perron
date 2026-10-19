"""Card system v1 mockups: Home Assistant cards (templates, canvas, image) on the 192x64 board.

Spec: templates hero / prog / list / msg / kpi / ring / img, full-screen frame (status bar stays,
footer replaces the pager) or panel frame (x128-191, departures reflow to x0-126).
Colour tokens only: w s a r rc nv + tag stripe. One hero number per 64 px column.
"""
import os
import random
from PIL import Image, ImageDraw
from render import Canvas, BLACK, WHITE
import icons
import scenes
from scenes import WARM, SEC, CATCH, LEAVE, TAGS, fit_words, HERE, badge4, status_bar

FOOT = (0xB0, 0xA9, 0x9E)
DELAY_BG = (0xC8, 0x1E, 0x14)
W2 = (0x80, 0x74, 0x66)          # w:2  (50 %)
W4 = (0x40, 0x3A, 0x33)          # w:4  (25 %)




# ----------------------------------------------------------------------------- frames
def footer(c, tag, text, meta=""):
    """Full-screen card footer (replaces the pager): tag stripe, caption, right meta."""
    c.rect(1, 57, 2, 6, TAGS[tag])
    c.text(6, 57, fit_words(c, text, 150, "small") or "", FOOT)
    if meta:
        c.text(191, 57, meta, SEC, align="right")


def panel_header(c, tag, title):
    c.rect(130, 1, 2, 7, TAGS[tag])
    c.text(134, 1, title, WARM)


def seg_bar(c, x0, x1, y, h, pct, seg=3, gap=1, fill=WARM, track=W4):
    n = (x1 - x0 + 1 + gap) // (seg + gap)
    lit = round(n * pct / 100)
    for k in range(n):
        c.rect(x0 + k * (seg + gap), y, seg, h, fill if k < lit else track)


def departures_left(c):
    """Panel mode: departures reflow to x0-126, status bar shrinks to clock + date."""
    c.text(1, 2, "14:07", WARM, font="mid")
    c.text(36, 3, "Sa 18.10.", SEC)
    rows = [("81", "Montgomery", 3, False), ("81", "Marius Renard", 22, False),
            ("4", "Nord", 7, False), ("S5", "Mechelen", 14, True)]
    for i, (line, dest, m, train) in enumerate(rows):
        y = 12 + i * 13
        if train:
            c.rect(0, y - 1, 127, 13, scenes_v8.SNCB_BG)
        badge4(c, 1, y, line)
        col = LEAVE if m <= 3 else CATCH
        c.text(119, y + 1, str(m), col, font="big", align="right")
        c.text(120, y + 1, "'", col)
        d = fit_words(c, dest, 119 - c.width(str(m), "big") - 30, "mid") or ""
        c.text(27, y + 3, d, WHITE if train else WARM, font="mid")


# ----------------------------------------------------------------------------- templates
def C_prog(c):
    status_bar(c)
    c.icon(4, 13, "washer", 16, tint=WARM)
    c.text(26, 14, "Waschen", WARM, font="dest")
    c.text(185, 13, "42", WARM, font="big", align="right")
    c.text(186, 13, "'", WARM)
    seg_bar(c, 26, 190, 32, 4, 63)
    c.text(26, 41, "Spülen", SEC)
    c.text(190, 41, "fertig 14:49", WARM, align="right")
    footer(c, "ha", "Waschmaschine · Bad")


def C_kpi(c):
    status_bar(c)
    data = [("PV jetzt", "3.4", "kW", None, "Spitze 4.1"), ("Heute", "18.2", "kWh", None, "gestern 15.9"),
            ("Akku", "78", "%", 78, "voll 16:20")]
    for k, (lab, val, unit, pct, sub) in enumerate(data):
        x = k * 64 + 3
        c.text(x, 13, lab, SEC)
        vw = c.text(x, 23, val, WARM, font="clock")
        c.text(x + vw + 2, 30, unit, SEC)
        c.text(x, 42, fit_words(c, sub, 58, "tiny") or "", SEC, font="tiny")
        if pct is not None:
            c.rect(x, 50, 56, 2, W4)
            c.rect(x, 50, 56 * pct // 100, 2, WARM)
    footer(c, "ha", "Energie · Dach Süd", "1/1")


def dither_portrait(w, h, seed=3):
    """Stand-in for a doorbell snapshot: grey image -> 4x4 ordered dither -> one token colour."""
    g = Image.new("L", (w, h), 40)
    d = ImageDraw.Draw(g)
    d.rectangle([0, 0, w, h * 2 // 3], fill=70)                   # door frame / background
    d.rectangle([w // 2 + 8, 0, w, h], fill=25)
    d.ellipse([w // 2 - 11, 6, w // 2 + 9, 28], fill=190)         # head
    d.ellipse([w // 2 - 24, 27, w // 2 + 22, h + 25], fill=150)   # shoulders
    d.rectangle([w // 2 - 18, 33, w // 2 - 2, 44], fill=230)      # parcel
    rnd = random.Random(seed)
    px = g.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = max(0, min(255, px[x, y] + rnd.randint(-18, 18)))
    bayer = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
    out = []
    for y in range(h):
        out.append([px[x, y] / 255 * 16 > bayer[y % 4][x % 4] + 0.5 for x in range(w)])
    return out


def C_ring(c):
    status_bar(c)
    bits = dither_portrait(60, 45)
    for y, row in enumerate(bits):
        for x, on in enumerate(row):
            if on:
                c.pixel(1 + x, 11 + y, (0xC8, 0xBC, 0xA8))
    c.text(66, 13, "Haustür", CATCH, font="dest")
    c.text(66, 31, "Paket · DHL", WARM, font="mid")
    c.text(66, 45, "vor 0' · 14:07", SEC)
    footer(c, "ha", "Türklingel", "20s")


def C_panel(c):
    departures_left(c)
    c.rect(127, 0, 1, 64, BLACK)
    panel_header(c, "ha", "Waschen")
    c.text(189, 14, "42'", WARM, font="clock", align="right")
    seg_bar(c, 130, 189, 35, 4, 63)
    c.text(130, 44, "Spülen", SEC, font="tiny")
    c.text(130, 54, "fertig 14:49", WARM, font="tiny")


def C_list(c):
    status_bar(c)
    rows = [("door", "Terrassentür offen", "12'", CATCH),
            ("car", "Auto lädt", "64%", WARM),
            ("bell", "Post eingeworfen", "09:12", SEC)]
    for i, (ic, lab, val, col) in enumerate(rows):
        y = 11 + i * 14
        c.icon(3, y + 4, ic, 7, tint=col if col != SEC else WARM)
        c.text(14, y + 4, fit_words(c, lab, 125, "mid") or "", WARM, font="mid")
        c.text(191, y + 2 if val[0].isdigit() and len(val) <= 3 else y + 4, val, col,
               font="big" if len(val) <= 3 else "mid", align="right")
    footer(c, "ha", "Haus", "3")


def C_msg(c):
    status_bar(c)
    c.text(4, 13, "Müll morgen früh", WARM, font="dest")
    c.text(4, 31, "Gelber Sack und Papier raus-", W2 if False else (0xD8, 0xD2, 0xC8), font="mid")
    c.text(4, 43, "stellen, Abholung ab 06:00.", (0xD8, 0xD2, 0xC8), font="mid")
    footer(c, "cal", "Erinnerung · Kalender Haus", "1/1")


def pv_chart_png():
    """What HA (or any renderer) would send as an image card: 192x45 RGB, flat UI graphic."""
    im = Image.new("RGB", (192, 45), BLACK)
    d = ImageDraw.Draw(im)
    vals = [0, 0, 0.1, 0.4, 1.1, 1.9, 2.7, 3.3, 3.8, 4.1, 3.9, 3.4, 2.6, 1.7, 0.9, 0.3, 0]
    for i, v in enumerate(vals):
        x = 4 + i * 11
        h = int(v / 4.2 * 36)
        col = (0x6A, 0x5A, 0x1A) if i > 10 else (0xC8, 0x96, 0x10)    # past bright, forecast dim
        d.rectangle([x, 40 - h, x + 7, 40], fill=col)
    d.line([0, 41, 191, 41], fill=(0x30, 0x30, 0x34))
    d.line([4 + 10 * 11 + 9, 2, 4 + 10 * 11 + 9, 41], fill=(0x7A, 0x74, 0x6C))   # now
    return im


def C_img(c):
    status_bar(c)
    im = pv_chart_png()
    c.img.paste(im, (0, 11))
    c.text(6, 13, "PV heute", WARM)
    c.text(191, 13, "18.2 kWh", SEC, align="right")
    footer(c, "ha", "Ertrag · Bild aus HA", "PNG")


def C_canvas(c):
    """Free canvas (t:"cv"): HA places up to 8 elements on the grid; validated, never partial."""
    status_bar(c)
    # 1 icon, 2 numbers, 2 texts, 1 bar, 1 badge  (= 7 elements)
    c.icon(4, 14, "car", 16, tint=WARM)
    c.text(26, 14, "Auto", WARM, font="dest")
    c.text(26, 31, "312", WARM, font="clock")
    c.text(58, 38, "km", SEC)
    c.rect(26, 50, 100, 2, W4)
    c.rect(26, 50, 78, 2, WARM)
    c.text(190, 16, "Ladeziel 90%", SEC, align="right")
    w = c.width("+11 kW", "small") + 4
    c.rect(190 - w, 30, w, 9, (0x1E, 0x46, 0x32))
    c.text(188, 31, "+11 kW", (0x9F, 0xE8, 0xC0), align="right")
    footer(c, "ha", "Canvas · 7/8 Elemente", "cv")


def C_alarm(c):
    """Prio 0: red band, status bar gone, stays until HA clears it."""
    c.rect(0, 0, 192, 14, DELAY_BG)
    c.icon(3, 3, "warn", 7, tint=WHITE)
    c.text(14, 3, "RAUCHMELDER", WHITE, font="mid")
    c.text(190, 3, "14:07", WHITE, font="mid", align="right")
    c.icon(4, 22, "smoke", 16, tint=LEAVE)
    c.text(26, 19, "Küche", WARM, font="dest")
    c.text(26, 37, "Alarm seit 14:06", WARM, font="mid")
    c.text(26, 50, "Bestätigen in Home Assistant", SEC)


def radar_png():
    """64x64 colour image for the panel (e.g. KMI radar rendered by HA): blobs on a dark map."""
    im = Image.new("RGB", (64, 64), (8, 10, 14))
    d = ImageDraw.Draw(im)
    for x0, y0, x1, y1 in ((0, 40, 64, 41), (30, 0, 31, 64), (10, 10, 50, 11)):
        d.rectangle([x0, y0, x1, y1], fill=(28, 30, 36))                 # coast/borders
    for (cx, cy, r, col) in ((14, 18, 14, (0x1E, 0x5A, 0xB4)), (18, 20, 8, (0x2E, 0x9E, 0x4A)),
                             (20, 21, 4, (0xE0, 0xC0, 0x20)), (44, 46, 9, (0x1E, 0x5A, 0xB4)),
                             (45, 47, 4, (0x2E, 0x9E, 0x4A))):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    d.rectangle([33, 30, 35, 32], fill=(255, 255, 255))                  # home
    return im


def C_img_panel(c):
    departures_left(c)
    c.rect(127, 0, 1, 64, BLACK)
    c.img.paste(radar_png().crop((0, 0, 64, 55)), (128, 0))
    c.text(130, 57, "Radar +30'", SEC, font="tiny")


import scenes_v8  # noqa: E402  (SNCB navy)

SCENES = [
    ("prog", "Fortschritt (Waschmaschine) - Vollbild, p1 bei Ende / p2 Rotation", C_prog),
    ("panel", "Gleiche Karte im Panel-Modus: Abfahrten bleiben links", C_panel),
    ("kpi", "KPI-Trio (PV / Energie / Akku)", C_kpi),
    ("list", "Liste (Zustände im Haus)", C_list),
    ("ring", "Türklingel mit Kamerabild (gedithert, einfarbig)", C_ring),
    ("msg", "Nachricht", C_msg),
    ("img", "Bild (PNG/RGB565 von HA, 192x45 + Bildzeile)", C_img),
    ("img_panel", "Bild im Panel (64x64, z.B. Regenradar)", C_img_panel),
    ("canvas", "Freie Fläche (Canvas, max. 8 Elemente, Raster)", C_canvas),
    ("alarm", "Prio 0: Vollbild-Alarm (bleibt bis HA löscht)", C_alarm),
]

if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    tiles = []
    for name, label, fn in SCENES:
        c = Canvas(); fn(c)
        p = os.path.join(HERE, "out", f"card_{name}.png"); c.save_led(p, pitch=4, dot=3)
        tiles.append((label, Image.open(p)))
    tw, th = tiles[0][1].size
    cols = 2
    rows = (len(tiles) + 1) // cols
    sheet = Image.new("RGB", (cols * (tw + 24) + 24, rows * (th + 40) + 24), (20, 20, 22))
    d = ImageDraw.Draw(sheet)
    from PIL import ImageFont
    try:
        f = ImageFont.truetype("segoeui.ttf", 18)
    except OSError:
        f = ImageFont.load_default()
    for i, (label, im) in enumerate(tiles):
        x = 24 + (i % cols) * (tw + 24)
        y = 24 + (i // cols) * (th + 40)
        d.text((x, y), label, fill=(220, 220, 220), font=f)
        sheet.paste(im, (x, y + 26))
    sheet.save(os.path.join(HERE, "out", "cards_v1_sheet.png"))
    print("cards ok")
