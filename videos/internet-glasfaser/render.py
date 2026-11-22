"""Rendert das TikTok-Video "Wie funktioniert dein Internet?" (63 s, 1080x1920, 30 fps).

Ablauf:
  1. python synth.py <thorsten-vits-modellordner> 0.93   (erzeugt _clips.npy / _clips.json)
  2. python render.py                                    (erzeugt internet-glasfaser.mp4)
"""
import json
import math
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synth import SCRIPT  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "internet-glasfaser.mp4")
W, H, FPS = 1080, 1920, 30
TOTAL = 63.0
FONT_DIR = "/usr/share/fonts/opentype/inter"

RED = (255, 69, 58)
ORANGE = (255, 149, 0)
YEL = (255, 214, 10)
GRN = (48, 209, 88)
CYAN = (90, 220, 255)
BLUE = (52, 150, 255)
WHITE = (255, 255, 255)
MUTED = (165, 172, 196)
PANEL = (32, 36, 56)
DARK = (14, 16, 30)


def font(weight, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, f"Inter-{weight}.otf"), size)


F_TITLE = font("ExtraBold", 80)
F_SUB = font("ExtraBold", 66)
F_BODY = font("SemiBold", 46)
F_LABEL = font("Bold", 42)
F_SMALL = font("SemiBold", 34)
F_CHIP = font("Bold", 38)
F_HUGE = font("ExtraBold", 150)


# ---------------------------------------------------------------- Timing

def build_timeline():
    meta = json.load(open(os.path.join(HERE, "_clips.json")))
    lens = meta["lens"]
    speech = sum(lens)
    lead, tail = 0.25, 0.9
    n_scene_breaks = sum(1 for i in range(1, len(SCRIPT)) if SCRIPT[i][0] != SCRIPT[i - 1][0])
    n_inner = len(SCRIPT) - 1 - n_scene_breaks
    free = TOTAL - speech - lead - tail
    # Szenenwechsel bekommen 2.2x so viel Pause wie Satzpausen
    unit = free / (n_inner + 2.2 * n_scene_breaks)
    if unit < 0.08:
        raise SystemExit(f"Sprache zu lang ({speech:.1f}s) – length_scale verkleinern")
    starts, t = [], lead
    for i, L in enumerate(lens):
        starts.append(t)
        t += L
        if i + 1 < len(SCRIPT):
            t += unit * (2.2 if SCRIPT[i + 1][0] != SCRIPT[i][0] else 1.0)
    sents = [dict(scene=s[0], sub=s[2], start=st, end=st + L)
             for s, st, L in zip(SCRIPT, starts, lens)]
    return sents, meta["sr"]


SENTS, VOICE_SR = build_timeline()


def scene_spans():
    spans = []
    for i, s in enumerate(SENTS):
        if not spans or spans[-1][0] != s["scene"]:
            spans.append([s["scene"], s["start"] - 0.15 if spans else 0.0, None, i])
    for i in range(len(spans)):
        spans[i][2] = spans[i + 1][1] if i + 1 < len(spans) else TOTAL
    return spans


SPANS = scene_spans()


def sent_t(i):
    """Startzeit von Satz i relativ zum Beginn seiner Szene."""
    for sc, a, b, first in SPANS:
        if sc == SENTS[i]["scene"] and a <= SENTS[i]["start"] < b:
            return SENTS[i]["start"] - a
    return 0


def sent_d(i):
    return SENTS[i]["end"] - SENTS[i]["start"]


# ---------------------------------------------------------------- Helpers

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return 3 * x * x - 2 * x * x * x


def appear(t, start, dur=0.4):
    return ease_out((t - start) / dur)


def lerp(a, b, k):
    return a + (b - a) * k


def rgba(c, a):
    return tuple(c[:3]) + (int(clamp(a) * 255),)


def make_bg():
    y = np.linspace(0, 1, H)[:, None]
    top, bot = np.array([10, 14, 32]), np.array([20, 16, 44])
    g = (top + (bot - top) * y)[:, None, :].repeat(W, axis=1)
    xx = np.linspace(-1, 1, W)[None, :]
    yy = np.linspace(-1, 1, H)[:, None]
    g = g * (1 - 0.28 * np.clip(xx ** 2 + (yy * 0.8) ** 2, 0, 1))[:, :, None]
    # feines Punktraster
    g[::48, ::48] += 18
    return Image.fromarray(np.clip(g, 0, 255).astype(np.uint8)).convert("RGB")


BG = make_bg()


def text(d, xy, s, f, col, a=1.0, anchor="mm", shadow=True):
    if a <= 0:
        return
    if shadow:
        d.text((xy[0] + 3, xy[1] + 5), s, font=f, fill=(0, 0, 0, int(110 * a)), anchor=anchor)
    d.text(xy, s, font=f, fill=rgba(col, a), anchor=anchor)


def text_in(d, xy, s, f, col, t, start, anchor="mm", dy=40):
    p = appear(t, start)
    if p > 0:
        text(d, (xy[0], xy[1] + (1 - p) * dy), s, f, col, p, anchor)


def chip(d, label, t, color=YEL, cy=210):
    p = appear(t, 0.0, 0.35)
    if p <= 0:
        return
    tw = F_CHIP.getlength(label)
    pw, ph = tw + 60, 70
    x0, y0 = (W - pw) / 2, cy - ph / 2 + (1 - p) * 25
    d.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], radius=35, fill=rgba(color, p))
    d.text((W / 2, y0 + ph / 2), label, font=F_CHIP, fill=(12, 12, 22, int(255 * p)), anchor="mm")


def title(d, s, t, start=0.08, cy=320, col=WHITE, f=F_TITLE):
    text_in(d, (W / 2, cy), s, f, col, t, start)


def glow_dot(img, x, y, r, col, a=1.0):
    pad = int(r * 3)
    size = 2 * pad
    lay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    ld.ellipse([pad - r * 2.2, pad - r * 2.2, pad + r * 2.2, pad + r * 2.2], fill=rgba(col, 0.55 * a))
    lay = lay.filter(ImageFilter.GaussianBlur(r * 0.9))
    ld = ImageDraw.Draw(lay)
    ld.ellipse([pad - r, pad - r, pad + r, pad + r], fill=rgba((255, 255, 255), a))
    img.paste(lay, (int(x - pad), int(y - pad)), lay)


# ---------------------------------------------------------------- Tacho

def gauge(img, cx, cy, R, value, vmax=100, alpha=1.0, label="Mbit/s", col=None):
    if alpha <= 0:
        return
    ss = 2
    size = int((R + 30) * 2 * ss)
    lay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    c = size / 2
    r = R * ss
    box = [c - r, c - r, c + r, c + r]
    a0, sweep = 135, 270
    d.arc(box, a0, a0 + sweep, fill=rgba(PANEL, 1), width=int(34 * ss))
    frac = clamp(value / vmax)
    if col is None:
        col = GRN if frac >= 0.85 else (YEL if frac >= 0.65 else RED)
    if frac > 0.005:
        d.arc(box, a0, a0 + sweep * frac, fill=rgba(col, 1), width=int(34 * ss))
    for k in range(11):
        ang = math.radians(a0 + sweep * k / 10)
        r1, r2 = r - 50 * ss, r - (70 if k % 5 == 0 else 62) * ss
        d.line([c + r1 * math.cos(ang), c + r1 * math.sin(ang),
                c + r2 * math.cos(ang), c + r2 * math.sin(ang)], fill=rgba(MUTED, 0.8), width=4 * ss)
    ang = math.radians(a0 + sweep * frac)
    rn = r - 85 * ss
    d.line([c, c, c + rn * math.cos(ang), c + rn * math.sin(ang)], fill=rgba(WHITE, 1), width=9 * ss)
    d.ellipse([c - 18 * ss, c - 18 * ss, c + 18 * ss, c + 18 * ss], fill=rgba(WHITE, 1))
    lay = lay.resize((size // ss, size // ss), Image.LANCZOS)
    if alpha < 1:
        a = np.array(lay)
        a[..., 3] = (a[..., 3] * alpha).astype(np.uint8)
        lay = Image.fromarray(a)
    img.paste(lay, (int(cx - lay.width / 2), int(cy - lay.height / 2)), lay)
    d = ImageDraw.Draw(img, "RGBA")
    text(d, (cx, cy + R * 0.55), f"{int(round(value))}", F_HUGE, WHITE, alpha)
    text(d, (cx, cy + R * 0.55 + 105), label, F_LABEL, MUTED, alpha)


# ---------------------------------------------------------------- Szenen

def sc_hook(img, d, t):
    chip(d, "DEIN INTERNET", t, CYAN)
    title(d, "100 Mbit gebucht …", t, 0.1)
    p_up = ease_io((t - 0.5) / 1.3)
    p_dn = ease_io((t - 2.1) / 1.0)
    v = 100 * p_up - 40 * p_dn
    gauge(img, W / 2, 800, 300, v, alpha=appear(t, 0.2, 0.5))
    if t > 2.3:
        text_in(d, (W / 2, 1220), "… aber nur 60 kommen an?!", F_SUB, RED, t, 2.3)


ROUTE = [("Rechenzentrum", "server"), ("Unterseekabel", "wave"), ("Glasfasernetz", "fiber"),
         ("Verteilerkasten", "box"), ("Deine Wohnung", "house")]


def icon(d, kind, x, y, s, a):
    c = rgba(WHITE, a)
    if kind == "server":
        for k in range(3):
            yy = y - s * 0.55 + k * s * 0.38
            d.rounded_rectangle([x - s * 0.55, yy, x + s * 0.55, yy + s * 0.3], radius=5, outline=c, width=5)
            d.ellipse([x + s * 0.3, yy + s * 0.1, x + s * 0.4, yy + s * 0.2], fill=rgba(GRN, a))
    elif kind == "wave":
        pts = [(x - s * 0.6 + i * s * 1.2 / 30, y + math.sin(i / 30 * 2 * math.pi * 1.5) * s * 0.22)
               for i in range(31)]
        d.line(pts, fill=c, width=6)
        d.line([(px, py + s * 0.3) for px, py in pts], fill=rgba(WHITE, a * 0.5), width=4)
    elif kind == "fiber":
        for k in range(3):
            d.line([x - s * 0.6, y - s * 0.3 + k * s * 0.3, x + s * 0.6, y - s * 0.3 + k * s * 0.3],
                   fill=rgba(CYAN, a), width=6)
    elif kind == "box":
        d.rounded_rectangle([x - s * 0.4, y - s * 0.55, x + s * 0.4, y + s * 0.55], radius=6,
                            outline=c, width=5)
        d.line([x, y - s * 0.55, x, y + s * 0.55], fill=c, width=4)
    elif kind == "house":
        d.polygon([(x - s * 0.6, y - s * 0.05), (x, y - s * 0.62), (x + s * 0.6, y - s * 0.05)], fill=c)
        d.rectangle([x - s * 0.45, y - s * 0.08, x + s * 0.45, y + s * 0.55], fill=c)
        d.rectangle([x - s * 0.12, y + s * 0.15, x + s * 0.12, y + s * 0.55], fill=rgba(DARK, a))


def sc_weg(img, d, t):
    chip(d, "DER WEG ZU DIR", t, CYAN)
    i0 = [i for i, s in enumerate(SENTS) if s["scene"] == "weg"][0]
    t2, t3, t4 = sent_t(i0), sent_t(i0 + 1), sent_t(i0 + 2)
    d3, d4 = sent_d(i0 + 1), sent_d(i0 + 2)
    show = [t2, t3 + 0.05, t3 + d3 * 0.35, t3 + d3 * 0.7, t4 + d4 * 0.55]
    xs, ys = 250, [400, 590, 780, 970, 1160]
    # Verbindungen
    for k in range(4):
        p = ease_io((t - show[k + 1] + 0.35) / 0.4)
        if p <= 0:
            continue
        col = ORANGE if k == 3 else CYAN
        y0, y1 = ys[k] + 62, ys[k + 1] - 62
        d.line([xs, y0, xs, lerp(y0, y1, p)], fill=rgba(col, 0.9), width=10)
        if k == 3 and p > 0.6:
            text(d, (xs + 40, (y0 + y1) / 2), "Kupfer", F_SMALL, ORANGE, appear(t, show[4] - 0.1),
                 anchor="lm", shadow=False)
    # Datenpakete
    for k in range(4):
        if t < show[k + 1] + 0.1:
            continue
        y0, y1 = ys[k] + 62, ys[k + 1] - 62
        speed = 0.35 if k == 3 else 2.2
        for j in range(2 if k == 3 else 3):
            ph = (t * speed + j / (2 if k == 3 else 3)) % 1
            glow_dot(img, xs, lerp(y0, y1, ph), 9, ORANGE if k == 3 else CYAN)
    d = ImageDraw.Draw(img, "RGBA")
    for k, ((name, kind), y) in enumerate(zip(ROUTE, ys)):
        p = appear(t, show[k], 0.45)
        if p <= 0:
            continue
        r = 58 * (0.7 + 0.3 * p)
        ring = ORANGE if k == 4 else CYAN
        d.ellipse([xs - r, y - r, xs + r, y + r], fill=rgba(PANEL, p), outline=rgba(ring, p), width=5)
        icon(d, kind, xs, y, 50, p)
        text(d, (xs + 100 + (1 - p) * 30, y), name, F_LABEL, WHITE, p, anchor="lm")
    if t > show[4]:
        text_in(d, (W / 2 + 90, 1270), "Die letzte Strecke bremst!", F_BODY, ORANGE, t, show[4] + 0.6)


def fiber_path(x0, x1, ytop, ybot, n=7):
    pts = [(x0, (ytop + ybot) / 2)]
    step = (x1 - x0) / n
    for k in range(n):
        pts.append((x0 + step * (k + 0.5), ytop if k % 2 == 0 else ybot))
    pts.append((x1, (ytop + ybot) / 2 + (ytop - ybot) / 2 * (1 if n % 2 else -1) * 0))
    # Gesamtlänge
    seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    return pts, seg


FIBER = fiber_path(170, 1010, 640, 760)
BITS = [1, 0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 0, 1,
        1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1, 1]


def point_on(path, s):
    pts, seg = path
    for i, L in enumerate(seg):
        if s <= L:
            k = s / L
            return lerp(pts[i][0], pts[i + 1][0], k), lerp(pts[i][1], pts[i + 1][1], k)
        s -= L
    return pts[-1]


def sc_glas(img, d, t):
    chip(d, "GLASFASER", t, CYAN)
    title(d, "Daten aus Licht", t)
    idx = [i for i, s in enumerate(SENTS) if s["scene"] == "glas"]
    t_laser, t_bits, t_refl, t_km = (sent_t(i) for i in idx[1:5])
    p = appear(t, 0.3, 0.5)
    # Faser: Mantel + Kern
    d.rounded_rectangle([150, 590, 1040, 810], radius=110, fill=rgba((40, 60, 90), p))
    d.rounded_rectangle([150, 625, 1040, 775], radius=75, fill=rgba((60, 110, 150), p * 0.8))
    text(d, (595, 860), "Glasfaser – dünner als ein Haar", F_SMALL, MUTED, p, shadow=False)
    # Laser
    period = 0.22
    t_emit0 = t_laser
    k_now = int((t - t_emit0) / period) if t >= t_emit0 else -1
    laser_on = k_now >= 0 and BITS[k_now % len(BITS)] == 1 and ((t - t_emit0) % period) < period * 0.75
    lp = appear(t, t_laser - 0.2, 0.4)
    d.rounded_rectangle([40, 640, 150, 760], radius=14, fill=rgba((70, 74, 96), lp),
                        outline=rgba(WHITE, lp * 0.6), width=3)
    text(d, (95, 590 - 20), "Laser", F_SMALL, WHITE, lp, shadow=False)
    if laser_on:
        glow_dot(img, 150, 700, 16, (255, 60, 60), lp)
    # Lichtpulse entlang der Zickzack-Bahn
    pts, seg = FIBER
    total = sum(seg)
    refl_vis = appear(t, t_refl - 0.3, 0.6)
    if refl_vis > 0:
        d.line(pts, fill=rgba((255, 120, 120), 0.35 * refl_vis), width=4)
    if t >= t_emit0:
        speed = 900
        kmax = int((t - t_emit0) / period)
        for k in range(max(0, kmax - 8), kmax + 1):
            if BITS[k % len(BITS)] != 1:
                continue
            s = (t - (t_emit0 + k * period)) * speed
            if 0 <= s <= total:
                x, y = point_on(FIBER, s) if refl_vis > 0.5 else (170 + s * (840 / total), 700)
                glow_dot(img, x, y, 12, (255, 70, 70))
    d = ImageDraw.Draw(img, "RGBA")
    # Bitstrom
    if t >= t_bits - 0.2:
        a = appear(t, t_bits - 0.2)
        shown = max(0, k_now + 1)
        seq = [BITS[k % len(BITS)] for k in range(max(0, shown - 12), shown)]
        for j, b in enumerate(reversed(seq)):
            x = 170 + j * 70
            text(d, (x, 500), str(b), F_SUB, RED if b else MUTED, a * (1 - j / 14), shadow=False)
        text(d, (W / 2, 960), "Licht an = 1  ·  Licht aus = 0", F_LABEL, WHITE, a)
    if t >= t_refl - 0.2:
        text_in(d, (W / 2, 1040), "Das Licht wird an der Wand gespiegelt", F_SMALL, CYAN, t, t_refl)
    if t >= t_km - 0.2:
        a = appear(t, t_km - 0.2)
        text(d, (W / 2, 1125), "→ fast ohne Verlust über viele Kilometer", F_BODY, GRN, a)


def sc_kupfer(img, d, t):
    chip(d, "KUPFER (DSL)", t, ORANGE)
    title(d, "Je weiter weg, desto langsamer", t, f=F_SUB)
    x0, x1, y0, y1 = 170, 980, 470, 1040
    p = appear(t, 0.3, 0.5)
    d.line([x0, y1, x1, y1], fill=rgba(MUTED, p), width=4)
    d.line([x0, y0, x0, y1], fill=rgba(MUTED, p), width=4)
    text(d, (x1, y1 + 45), "Entfernung zum Verteiler →", F_SMALL, MUTED, p, anchor="rm", shadow=False)
    text(d, (x0 - 20, y0 - 30), "Tempo", F_SMALL, MUTED, p, anchor="lm", shadow=False)
    for k, lab in enumerate(["0 m", "500 m", "1 km"]):
        text(d, (x0 + k * (x1 - x0) / 2, y1 + 95), lab, F_SMALL, MUTED, p, shadow=False)

    def speed(xn):  # 0..1 = 0..1 km, VDSL-Faustwert
        return 250 * math.exp(-2.3 * xn)

    def ypos(v):
        return y1 - (v / 260) * (y1 - y0)
    draw_p = ease_io((t - 0.6) / 1.6)
    # Glasfaser-Vergleich
    d.line([x0, ypos(250), lerp(x0, x1, draw_p), ypos(250)], fill=rgba(CYAN, 0.9), width=7)
    if draw_p > 0.9:
        text(d, (x1, ypos(250) - 35), "Glasfaser", F_SMALL, CYAN, 1, anchor="rm", shadow=False)
    pts = [(lerp(x0, x1, k / 60), ypos(speed(k / 60))) for k in range(int(60 * draw_p) + 1)]
    if len(pts) > 1:
        d.line(pts, fill=rgba(ORANGE, 1), width=8)
    if draw_p > 0.95:
        text(d, (x1 - 10, ypos(speed(1)) - 40), "Kupfer", F_SMALL, ORANGE, 1, anchor="rm", shadow=False)
    # Haus wandert nach rechts
    i1 = [i for i, s in enumerate(SENTS) if s["scene"] == "kupfer"][1]
    mv = ease_io((t - sent_t(i1)) / max(1.0, sent_d(i1) - 0.3))
    xn = lerp(0.12, 0.9, mv)
    if t > sent_t(i1) - 0.3:
        hx, hy = lerp(x0, x1, xn), ypos(speed(xn))
        glow_dot(img, hx, hy, 12, ORANGE)
        d = ImageDraw.Draw(img, "RGBA")
        icon(d, "house", hx, hy - 75, 50, 1)
        text(d, (hx, hy - 150), f"~{int(round(speed(xn) / 5) * 5)} Mbit", F_LABEL, WHITE, 1)


def sc_gruende(img, d, t):
    chip(d, "ABER WARUM?", t, RED)
    title(d, "Wo bleibt mein Tempo?", t)
    gauge(img, W / 2, 780, 280, 100, alpha=appear(t, 0.3, 0.5))


REASONS = [("„bis zu“ im Vertrag", 10), ("Abends: Nachbarn teilen", 15),
           ("WLAN durch Wände", 13), ("Steuerdaten (Overhead)", 2)]


def sc_reason(img, d, t, n):
    """n = 0..3; Szenen g1..g4 teilen sich ein Layout."""
    chip(d, f"GRUND {n + 1} VON 4", t, RED)
    before = 100 - sum(v for _, v in REASONS[:n])
    after = before - REASONS[n][1]
    v = lerp(before, after, ease_io((t - 0.6) / 1.0))
    gauge(img, W / 2, 560, 230, v)
    d = ImageDraw.Draw(img, "RGBA")
    y0 = 930
    for k, (name, minus) in enumerate(REASONS):
        if k > n:
            break
        y = y0 + k * 82
        active = k == n
        a = appear(t, 0.15, 0.4) if active else 1.0
        x_off = (1 - a) * 60
        d.rounded_rectangle([90 + x_off, y - 34, 990 + x_off, y + 34], radius=20,
                            fill=rgba((60, 30, 40) if active else PANEL, a),
                            outline=rgba(RED, a) if active else None, width=3)
        text(d, (125 + x_off, y), f"{k + 1}. {name}", F_SMALL, WHITE if active else MUTED, a,
             anchor="lm", shadow=False)
        text(d, (960 + x_off, y), f"−{minus}", F_LABEL, RED, a, anchor="rm", shadow=False)
    text(d, (W / 2, y0 + 4 * 82 - 10), "Beispielwerte", F_SMALL, MUTED, 0.6, shadow=False)


def sc_tipp(img, d, t):
    chip(d, "MEIN TIPP", t, GRN)
    title(d, "Immer per Kabel testen!", t, f=F_SUB)
    idx = [i for i, s in enumerate(SENTS) if s["scene"] == "tipp"]
    # Balken WLAN vs. Kabel
    for k, (lab, val, col) in enumerate([("WLAN", 60, YEL), ("LAN-Kabel", 95, GRN)]):
        y = 520 + k * 170
        p = ease_out((t - 0.4 - k * 0.3) / 0.9)
        if p <= 0:
            continue
        text(d, (110, y - 50), lab, F_LABEL, WHITE, 1, anchor="lm")
        d.rounded_rectangle([110, y, 970, y + 70], radius=35, fill=rgba(PANEL, 1))
        d.rounded_rectangle([110, y, 110 + max(70, 860 * val / 100 * p), y + 70], radius=35,
                            fill=rgba(col, 1))
        text(d, (130 + 860 * val / 100 * p - 40, y + 35), f"{int(val * p)}", F_LABEL, DARK, 1,
             anchor="rm", shadow=False)
    t2 = sent_t(idx[1])
    p = appear(t, t2 - 0.1, 0.5)
    if p > 0:
        y = 920 + (1 - p) * 40
        d.rounded_rectangle([90, y, 990, y + 290], radius=30, fill=rgba(PANEL, p),
                            outline=rgba(GRN, p), width=4)
        text(d, (W / 2, y + 62), "Dauerhaft zu langsam?", F_LABEL, WHITE, p)
        text(d, (W / 2, y + 135), "Messen: breitbandmessung.de", F_SMALL, CYAN, p, shadow=False)
        text(d, (W / 2, y + 195), "→ Recht auf Minderung", F_SMALL, GRN, p, shadow=False)
        text(d, (W / 2, y + 245), "(§ 57 TKG)", F_SMALL, MUTED, p, shadow=False)


def sc_outro(img, d, t):
    p = appear(t, 0.0, 0.4)
    text(d, (W / 2, 640 + (1 - p) * 40), "Folg mir", F_HUGE, WHITE, p)
    text(d, (W / 2, 810 + (1 - p) * 40), "für mehr!", F_TITLE, CYAN, p)
    for j in range(5):
        ph = (t * 0.8 + j / 5) % 1
        glow_dot(img, lerp(100, 980, ph), 990, 10, CYAN, 1 - abs(ph - 0.5) * 1.6)


SCENE_FN = {
    "hook": sc_hook, "weg": sc_weg, "glas": sc_glas, "kupfer": sc_kupfer, "gruende": sc_gruende,
    "g1": lambda i, d, t: sc_reason(i, d, t, 0), "g2": lambda i, d, t: sc_reason(i, d, t, 1),
    "g3": lambda i, d, t: sc_reason(i, d, t, 2), "g4": lambda i, d, t: sc_reason(i, d, t, 3),
    "tipp": sc_tipp, "outro": sc_outro,
}


# ---------------------------------------------------------------- Untertitel

F_CAP = font("ExtraBold", 62)
CAP_Y = 1400


def build_captions():
    chunks = []
    for s in SENTS:
        words = s["sub"].split()
        weights = [len(w) + 2 for w in words]
        tot = sum(weights)
        dur = s["end"] - s["start"]
        times, acc = [], s["start"]
        for wgt in weights:
            times.append(acc)
            acc += dur * wgt / tot
        cur = []
        for w_, st in zip(words, times):
            cur.append((w_, st))
            line = " ".join(x for x, _ in cur)
            if F_CAP.getlength(line) > 760 or w_.endswith((",", ".", "?", "!", ":")):
                chunks.append(cur)
                cur = []
        if cur:
            chunks.append(cur)
    out = []
    for i, ch in enumerate(chunks):
        end = chunks[i + 1][0][1] if i + 1 < len(chunks) else TOTAL
        out.append((ch, ch[0][1], min(end, ch[-1][1] + 2.0)))
    return out


CAPS = build_captions()


def draw_caption(img, t):
    d = ImageDraw.Draw(img, "RGBA")
    for ch, a, b in CAPS:
        if a <= t < b:
            words = [w for w, _ in ch]
            full = " ".join(words)
            # bei Bedarf zweizeilig
            lines = [words]
            if F_CAP.getlength(full) > 940:
                mid = len(words) // 2
                lines = [words[:mid], words[mid:]]
            pop = 0.85 + 0.15 * ease_out((t - a) / 0.15)
            f = F_CAP if pop >= 0.999 else font("ExtraBold", int(62 * pop))
            lh = 78
            y0 = CAP_Y - lh * (len(lines) - 1) / 2
            wi = 0
            for li, ln in enumerate(lines):
                lw = f.getlength(" ".join(ln))
                x = (W - lw) / 2
                for w_ in ln:
                    st = ch[wi][1]
                    col = YEL if st <= t else WHITE
                    d.text((x, y0 + li * lh), w_, font=f, fill=col, anchor="lm",
                           stroke_width=7, stroke_fill=(0, 0, 0))
                    x += f.getlength(w_ + " ")
                    wi += 1
            break


# ---------------------------------------------------------------- Audio

def build_audio():
    clips = np.load(os.path.join(HERE, "_clips.npy"), allow_pickle=True)
    sr = VOICE_SR
    voice = np.zeros(int(TOTAL * sr) + sr)
    for s, c in zip(SENTS, clips):
        i = int(s["start"] * sr)
        voice[i:i + len(c)] += c
    voice = voice[: int(TOTAL * sr)]
    vpath = os.path.join(HERE, "_voice.wav")
    write_wav(vpath, voice / (np.max(np.abs(voice)) + 1e-9) * 0.9, sr)

    msr = 44100
    n = int(TOTAL * msr)
    m = np.zeros(n)
    rng = np.random.default_rng(3)
    bpm = 96
    beat = 60 / bpm

    def add(sig, at, g):
        i = int(at * msr)
        if i < n:
            e = min(n, i + len(sig))
            m[i:e] += sig[: e - i] * g
    kt = np.arange(int(0.3 * msr)) / msr
    kick = np.sin(2 * np.pi * (48 + 80 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 10)
    hl = int(0.04 * msr)
    hat = np.diff(rng.standard_normal(hl + 1)) * np.exp(-np.arange(hl) / msr * 100)
    b = 0
    while b * beat < TOTAL:
        add(kick, b * beat, 0.7)
        add(hat, b * beat + beat / 2, 0.08)
        b += 1
    # Pad: Dm - Bb - F - C
    chords = [[146.83, 174.61, 220.0], [116.54, 146.83, 174.61],
              [174.61, 220.0, 261.63], [130.81, 164.81, 196.0]]
    bar = 4 * beat
    i = 0
    while i * 2 * bar < TOTAL:
        ch = chords[i % 4]
        L = int(2 * bar * msr)
        tt = np.arange(L) / msr
        env = np.minimum(1, tt / 0.6) * np.minimum(1, (2 * bar - tt) / 0.6)
        sig = sum(np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * 2.003 * f * tt) for f in ch)
        add(sig * env, i * 2 * bar, 0.05)
        add(np.sin(2 * np.pi * ch[0] / 2 * tt) * env, i * 2 * bar, 0.18)
        # Arpeggio
        for k in range(16):
            f = ch[k % 3] * 2
            al = int(0.18 * msr)
            at_ = np.arange(al) / msr
            add(np.sin(2 * np.pi * f * at_) * np.exp(-at_ * 14), i * 2 * bar + k * beat / 2, 0.035)
        i += 1
    # Whoosh bei Szenenwechseln
    wl = int(0.5 * msr)
    wt = np.arange(wl) / msr
    noise = rng.standard_normal(wl)
    for sc, a, _, _ in SPANS[1:]:
        env = np.sin(np.pi * wt / 0.5) ** 2
        sig = np.convolve(noise, np.ones(12) / 12, mode="same") * env
        add(sig, a - 0.2, 0.35)
    fo = np.clip((TOTAL - np.arange(n) / msr) / 1.2, 0, 1)
    m *= fo
    m = m / (np.max(np.abs(m)) + 1e-9) * 0.8
    mpath = os.path.join(HERE, "_music.wav")
    write_wav(mpath, m, msr)

    apath = os.path.join(HERE, "_mix.wav")
    fc = ("[0:a]aresample=44100,highpass=f=70,"
          "equalizer=f=180:t=q:w=1:g=2,equalizer=f=3200:t=q:w=1.2:g=2.5,"
          "equalizer=f=7500:t=q:w=1:g=-2,"
          "acompressor=threshold=-20dB:ratio=3:attack=8:release=120:makeup=4,"
          "aecho=0.8:0.85:28:0.06,asplit=2[v][vs];"
          "[1:a]volume=0.22[m];"
          "[m][vs]sidechaincompress=threshold=0.03:ratio=6:attack=30:release=350[md];"
          "[v][md]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[out]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", vpath, "-i", mpath,
                    "-filter_complex", fc, "-map", "[out]", "-ar", "44100", "-t", str(TOTAL), apath],
                   check=True)
    os.remove(vpath)
    os.remove(mpath)
    return apath


def write_wav(path, x, sr):
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- Render

def frame(gt):
    for sc, a, b, _ in SPANS:
        if a <= gt < b:
            break
    lt = gt - a
    img = BG.copy()
    d = ImageDraw.Draw(img, "RGBA")
    SCENE_FN[sc](img, d, lt)
    # weiche Szenenübergänge
    k = min(clamp(lt / 0.18), clamp((b - gt) / 0.18)) if sc != "hook" else clamp((b - gt) / 0.18)
    if k < 1:
        img = Image.blend(BG, img, k)
    draw_caption(img, gt)
    return img


def render():
    apath = build_audio()
    proc = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", apath, "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-t", str(TOTAL), "-movflags", "+faststart", OUT,
    ], stdin=subprocess.PIPE)
    nf = int(TOTAL * FPS)
    for fi in range(nf):
        proc.stdin.write(frame(fi / FPS).tobytes())
        if fi % 300 == 0:
            print(f"frame {fi}/{nf}", flush=True)
    proc.stdin.close()
    proc.wait()
    os.remove(apath)
    print("fertig:", OUT)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "preview":
        for sc, a, b, _ in SPANS:
            tt = min(b - 0.3, a + (b - a) * 0.8)
            frame(tt).save(os.path.join(sys.argv[2], f"{sc}.png"))
        print([(s[0], round(s[1], 2), round(s[2], 2)) for s in SPANS])
    else:
        render()
