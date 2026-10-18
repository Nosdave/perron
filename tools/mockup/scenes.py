"""Layout iterations for the 192x64 board.

  python scenes.py              -> all variants into out/sheet.png
  python scenes.py A3 B3        -> selected variants

Sample data is generic (line termini only, no home stop) so it can live in the public repo.
Iteration history: v1 (Silkscreen/Tiny5: digits ambiguous at 5 px) -> v2 -> v3 (5x7 matrix font).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

from PIL import Image

from render import AMBER, BLACK, DIM, WHITE, Canvas

HERE = os.path.dirname(os.path.abspath(__file__))
RED = (255, 60, 60)
SEP = (40, 40, 46)

# (bg, fg, shape) per line. Placeholders until verified against STIB GTFS routes.txt.
LINES = {
    "81": ((0xE6, 0x00, 0x7E), WHITE, "rect"),
    "71": ((0x00, 0x8B, 0xCC), WHITE, "round"),
    "S5": ((0x8D, 0xC6, 0x3F), BLACK, "pill"),
}


@dataclass
class Dep:
    line: str
    dest: str
    mins: list = field(default_factory=list)


SAMPLE = [
    Dep("81", "Montgomery", [2, 11]),
    Dep("81", "Marius Renard", [0, 13]),
    Dep("71", "Gare du Nord", [4, 24]),
    Dep("S5", "Mechelen", [9]),
]


def mins_txt(m: int) -> str:
    return "now" if m <= 0 else f"{m}'"


def line_badge(c: Canvas, x, y, line, w=17):
    bg, fg, shape = LINES.get(line, ((90, 90, 90), WHITE, "round"))
    return c.badge(x, y, line, bg, fg, shape=shape, w=w)


def dep_row(c: Canvas, x0, x1, y, d: Dep, second=True):
    """badge(10px) | destination | first (amber) + second (dim) departure, right aligned."""
    bw = line_badge(c, x0, y, d.line)
    right = x1
    if second and len(d.mins) > 1:
        right -= c.text(right, y + 2, mins_txt(d.mins[1]), DIM, align="right") + 4
    if d.mins:
        m = d.mins[0]
        right -= c.text(right, y + 2, mins_txt(m), RED if m <= 0 else AMBER, align="right") + 5
    nx = x0 + bw + 3
    c.text(nx, y + 2, d.dest, WHITE, max_w=right - nx)


def ticker(c: Canvas, y, text, color, icon=None):
    c.rect(0, y, 192, 10, (16, 16, 20))
    x = 2
    if icon:
        c.icon(1, y + 1, icon)
        x = 10
    c.text(x, y + 2, text, color, max_w=190 - x)


# ---------------- A3: info panel left | departures right | ticker ----------------
def A3(c: Canvas):
    c.text(32, 2, "14:07", WHITE, font="clock", align="center")
    c.text(32, 19, "Sa 18. Okt", DIM, align="center")
    c.icon(1, 29, "partlycloudy")
    c.text(19, 31, "12°", WHITE, font="mid")
    c.text(19, 41, "8/15", DIM)
    c.rect(64, 0, 1, 53, SEP)
    y = 0
    for d in SAMPLE:
        dep_row(c, 67, 191, y, d)
        y += 13
    ticker(c, 54, "T92 travaux Marius Renard jusqu'au 30/08", (255, 190, 120), icon="warn")


# ---------------- B3: slim top bar | 3 full-width rows | ticker ----------------
def B3(c: Canvas):
    c.text(1, 1, "14:07", WHITE, font="mid")
    c.text(34, 2, "Sa 18. Okt", DIM)
    c.text(191, 1, "12°", WHITE, font="mid", align="right")
    c.text(166, 2, "8/15", DIM, align="right")
    c.hline(0, 10, 192, SEP)
    y = 12
    for d in SAMPLE[:3]:
        dep_row(c, 1, 191, y, d)
        y += 13
    ticker(c, 54, "15:30 Zahnarzt  ·  Arbeit 23 min  ·  Regen ab 17h", (170, 200, 255))


# ---------------- C3: big next departure per direction (glanceable) ----------------
def C3(c: Canvas):
    for i, d in enumerate(SAMPLE[:2]):
        x = i * 64
        line_badge(c, x + 2, 1, d.line)
        c.text(x + 22, 3, d.dest, WHITE, max_w=40)
        m = d.mins[0]
        c.text(x + 32, 16, mins_txt(m) if m > 0 else "jetzt", RED if m <= 0 else AMBER,
               font="big", align="center")
        if len(d.mins) > 1:
            c.text(x + 32, 32, "dann " + mins_txt(d.mins[1]), DIM, align="center")
        c.rect(x + 63, 0, 1, 43, SEP)
    c.text(160, 2, "14:07", WHITE, font="clock", align="center")
    c.icon(130, 21, "partlycloudy")
    c.text(149, 23, "12°", WHITE, font="mid")
    c.text(149, 33, "8/15", DIM)
    c.hline(0, 43, 192, SEP)
    line_badge(c, 1, 46, "71")
    c.text(21, 48, "Nord", WHITE)
    c.text(62, 48, "4'", AMBER, align="right")
    line_badge(c, 66, 46, "S5")
    c.text(86, 48, "Mechelen", WHITE)
    c.text(140, 48, "9'", AMBER, align="right")
    c.text(190, 48, "Arbeit 23'", (170, 200, 255), align="right")


VARIANTS = {"A3": A3, "B3": B3, "C3": C3}


def render_one(name, fn, path):
    c = Canvas()
    fn(c)
    c.save_led(path)
    return Image.open(path)


def sheet(names, path):
    ims = [render_one(n, VARIANTS[n], os.path.join(HERE, "out", f"{n}.png")) for n in names]
    out = Image.new("RGB", (ims[0].width, sum(i.height + 12 for i in ims)), (255, 255, 255))
    y = 0
    for i in ims:
        out.paste(i, (0, y))
        y += i.height + 12
    out.save(path)




# ======================= Iteration 4 (after multi-agent review) =======================
# Changes: warm white, big minutes in a fixed column, walk-time colouring (amber = catchable,
# red = leave now), real GTFS colours, rounded-square STIB badges / round S-train plaques,
# alias-shortened destinations (never cut mid-word), status bar with 9x9 weather, pager with
# category tag instead of a ticker, P0 takeover, amber-only night mode. One UI language (de).
WARM = (0xFF, 0xE9, 0xCC)
SEC = (0x7A, 0x74, 0x6C)
CATCH = (0xFF, 0xA0, 0x00)
LEAVE = (0xFF, 0x3B, 0x1F)
TAGS = {"cal": (0x5A, 0xA0, 0xFF), "commute": (0x4F, 0xD1, 0xC5), "wx": (0xB4, 0x8C, 0xFF),
        "disr": (0xFF, 0x6A, 0x00), "alert": (0xFF, 0x3B, 0x1F), "news": (0x9A, 0x94, 0x8C),
        "ha": (0x41, 0xBD, 0xF5)}

GTFS = {  # route_short_name -> (route_color, route_text_color, mode)   [STIB/SNCB GTFS 2026-10]
    "81": ((0xE4, 0x3C, 0x2E), WHITE, "tram"),
    "71": ((0xF2, 0x9D, 0xC3), BLACK, "bus"),
    "4": ((0xEA, 0x4F, 0x80), BLACK, "tram"),
    "1": ((0xB5, 0x37, 0x8C), WHITE, "metro"),
    "S5": ((0xFF, 0xCD, 0x00), BLACK, "train"),
    "S19": ((0x01, 0x6A, 0xB3), WHITE, "train"),
    "IC": ((0x01, 0x6A, 0xB3), WHITE, "train"),
}

STRIP = ("Gare de ", "Gare du ", "Gare ", "Station ", "Place ", "Porte de ", "Porte du ")


def short_dest(name: str, aliases=None) -> str:
    """Alias map first, then drop generic words. Never cut mid-word."""
    if aliases and name in aliases:
        return aliases[name]
    for w in STRIP:
        if name.startswith(w) and len(name) > len(w) + 2:
            name = name[len(w):]
    for suf in (" Gare", " Station", " G.", " St."):
        if name.endswith(suf):
            name = name[: -len(suf)]
    return name


def fit_words(c: Canvas, s: str, max_w: int, font: str) -> str | None:
    """Drop trailing words until it fits; None if even the first word does not fit."""
    words = s.split(" ")
    while words:
        t = " ".join(words)
        if c.width(t, font) <= max_w:
            return t
        words.pop()
    return None


def badge4(c: Canvas, x, y, line, h=12, w=22, font="mid"):
    """Brand badge. White-text lines: filled rounded square. Black-text (light) lines: on LEDs
    dark text blooms away, so draw a 1px frame + text in the line colour instead (iteration 5).
    SNCB lines use the same geometry (pill corners)."""
    bg, fg, mode = GTFS.get(line, ((90, 90, 90), WHITE, "bus"))
    cap = 6 if font == "small" else 7
    if fg == BLACK:
        c.rect(x, y, w, h, bg)
        c.rect(x + 1, y + 1, w - 2, h - 2, BLACK)
        for cx, cy in ((x, y), (x + w - 1, y), (x, y + h - 1), (x + w - 1, y + h - 1)):
            c.pixel(cx, cy, BLACK)
        c.text(x + (w - c.width(line, font) + 1) // 2, y + (h - cap) // 2, line, bg, font=font)
    else:
        c.badge(x, y, line, bg, fg, shape="pill" if mode == "train" else "round", w=w, h=h, font=font)
    return w


def arrows_now(c: Canvas, x_right, y, color, phase=0):
    """STIB-style 'arriving' signal: two down-arrows (animated by 1 px bounce in firmware)."""
    for k in range(2):
        ax = x_right - 15 + k * 8
        ay = y + 1 + phase
        for i, row in enumerate(["#####", ".###.", "..#.."]):
            for j, ch in enumerate(row):
                if ch == "#":
                    c.pixel(ax + j, ay + i * 2, color)
                    c.pixel(ax + j, ay + i * 2 + 1, color)


def walk_tag(c: Canvas, x_right, y, walk):
    """Iteration 6: walking time = pedestrian glyph + minutes (dim), right-aligned at x_right."""
    t = str(walk)
    tw = c.width(t)
    c.text(x_right, y + 4, t, SEC, align="right")
    c.icon(x_right - tw - 6, y + 3, "walk", size=7, tint=SEC)
    return tw + 6


def dep_row4(c: Canvas, y, line, dest, mins, walk=3, second=True, delay=0, big=True):
    """Row = 14 px. badge x1 | dest x23..143 (6x10) | first dep right edge 168 (9x15B) | second 191."""
    badge4(c, 1, y + 1, line)
    m0 = mins[0] if mins else None
    if m0 is not None:
        if m0 < walk - 1:
            pass  # missed -> firmware drops it; mockup shows next
        col = LEAVE if m0 <= walk else CATCH
        if m0 <= 0:
            arrows_now(c, 168, y + 1, col)
        else:
            c.text(168, y + 2, f"{m0}", col, font="big", align="right")
            c.text(169, y + 2, "'", col, font="small")
    if delay:
        c.text(191, y + 4, f"+{delay}", LEAVE, align="right")
    elif second and len(mins) > 1:
        c.text(191, y + 4, f"{mins[1]}'", SEC, align="right")
    mw = c.width(str(m0), "big") if (m0 is not None and m0 > 0) else 16
    wt = walk_tag(c, 168 - mw - 5, y, walk)
    dw = 168 - mw - 5 - wt - 4 - 27
    name = fit_words(c, short_dest(dest), dw, "mid") or fit_words(c, short_dest(dest), dw, "small")
    font = "mid" if fit_words(c, short_dest(dest), dw, "mid") else "small"
    c.text(27, y + 4 if font == "mid" else y + 5, name or "", WARM, font=font)


def status_bar(c: Canvas, cond="partlycloudy", temp=12, tmin=8, tmax=15, alert_dot=False):
    c.text(1, 2, "14:07", WARM, font="mid")
    c.text(36, 3, "Sa 18.10.", SEC)
    if alert_dot:
        c.rect(95, 3, 3, 3, LEAVE)
    c.text(140, 3, f"{tmin}-{tmax}°", SEC, align="right")
    c.icon(150, 1, cond, size=9)
    c.text(191, 2, f"{temp}°", WARM, font="mid", align="right")


def pager(c: Canvas, tag, text):
    c.rect(1, 55, 4, 7, TAGS[tag])
    c.text(8, 56, fit_words(c, text, 182, "small") or "", (0xD8, 0xD2, 0xC8))


def D1(c: Canvas):
    status_bar(c)
    dep_row4(c, 11, "81", "Montgomery", [6, 15], walk=1)
    dep_row4(c, 25, "71", "Delta", [7, 19], walk=5)
    dep_row4(c, 39, "S5", "Mechelen", [14], walk=12, delay=3)
    pager(c, "cal", "15:30 Zahnarzt Dr. Peeters")


def D1b(c: Canvas):  # same page a few seconds later: tram arriving, bus row, other pager item
    status_bar(c, cond="rainy", temp=11, tmin=8, tmax=13)
    dep_row4(c, 11, "81", "Montgomery", [0, 9])
    dep_row4(c, 25, "81", "Marius Renard", [7, 19])
    dep_row4(c, 39, "71", "Delta", [4, 24])
    pager(c, "wx", "Regen ab 17 Uhr (80 %)")


def D2(c: Canvas):  # hero: one stop, two directions
    status_bar(c)
    for i, (dest, mins) in enumerate([("Montgomery", [6, 15]), ("Marius Renard", [2, 13])]):
        y = 12 + i * 21
        badge4(c, 1, y + 2, "81", h=14, w=24, font="mid")
        c.text(27, y + 6, short_dest(dest), WARM, font="mid")
        col = LEAVE if mins[0] <= 3 else CATCH
        c.text(166, y + 3, f"{mins[0]}", col, font="clock", align="right")
        c.text(167, y + 3, "'", col, font="mid")
        c.text(191, y + 8, f"{mins[1]}'", SEC, align="right")
    pager(c, "commute", "Arbeit: 23 min mit dem Auto (+4)")


def P0(c: Canvas):  # alert takeover
    c.rect(0, 0, 192, 14, (0xB0, 0, 0))
    c.icon(2, 3, "warn", size=7, tint=WHITE)
    c.text(14, 3, "BE-ALERT", WHITE, font="mid")
    c.text(190, 4, "14:07", (255, 200, 200), align="right")
    c.text(2, 19, "Brand in Brussels: Fenster und", WARM, font="mid")
    c.text(2, 31, "Türen schließen, drinnen", WARM, font="mid")
    c.text(2, 43, "bleiben.", WARM, font="mid")
    c.text(190, 56, "1/2", SEC, align="right")


def NIGHT(c: Canvas):  # amber only, minimal
    A, A2 = (0xFF, 0x8A, 0x00), (0x80, 0x45, 0x00)
    c.text(96, 6, "02:41", A, font="clock", align="center")
    c.icon(60, 30, "clear-night", size=9, tint=A2)
    c.text(72, 31, "6°", A2, font="mid")
    c.rect(100, 31, 10, 9, BLACK)
    c.badge(100, 30, "N10", BLACK, A, shape="round", w=21)
    c.rect(100, 30, 21, 1, A); c.rect(100, 39, 21, 1, A); c.rect(100, 30, 1, 10, A); c.rect(120, 30, 1, 10, A)
    c.text(140, 32, "23'", A, font="mid", align="right")


VARIANTS.update({"D1": D1, "D1b": D1b, "D2": D2, "P0": P0, "NIGHT": NIGHT})


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    names = sys.argv[1:] or list(VARIANTS)
    sheet(names, os.path.join(HERE, "out", "sheet.png"))
    print("rendered", names)
