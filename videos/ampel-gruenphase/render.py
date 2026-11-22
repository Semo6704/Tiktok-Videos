"""Rendert das TikTok-Video "Warum ist Grün länger als Rot?" (1080x1920, 30 fps).

Aufruf:  python3 render.py   ->  ampel-gruenphase.mp4 im selben Ordner
Benötigt: Pillow, numpy, ffmpeg, Inter-Schrift (/usr/share/fonts/opentype/inter).
"""
import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ampel-gruenphase.mp4")
W, H, FPS = 1080, 1920, 30
FONT_DIR = "/usr/share/fonts/opentype/inter"

RED = (255, 69, 58)
YEL = (255, 204, 0)
GRN = (48, 209, 88)
WHITE = (255, 255, 255)
MUTED = (165, 172, 196)
PANEL = (30, 34, 52)


def font(weight, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, f"Inter-{weight}.otf"), size)


F_HEAD = font("ExtraBold", 92)
F_HEAD_S = font("ExtraBold", 76)
F_BODY = font("SemiBold", 50)
F_SMALL = font("SemiBold", 40)
F_CHIP = font("Bold", 40)
F_BIG = font("ExtraBold", 130)

# ---------------------------------------------------------------- helpers

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    x = clamp(x)
    return 3 * x * x - 2 * x * x * x


def appear(t, start, dur=0.45):
    return ease_out((t - start) / dur)


def lerp(a, b, k):
    return a + (b - a) * k


def lerp_col(c1, c2, k):
    return tuple(int(lerp(a, b, k)) for a, b in zip(c1, c2))


def make_bg():
    y = np.linspace(0, 1, H)[:, None]
    top = np.array([14, 16, 30])
    bot = np.array([24, 20, 44])
    grad = (top + (bot - top) * y)[:, None, :].repeat(W, axis=1)
    # leichte Vignette
    xx = np.linspace(-1, 1, W)[None, :]
    yy = np.linspace(-1, 1, H)[:, None]
    vig = 1 - 0.25 * np.clip(xx ** 2 + (yy * 0.8) ** 2, 0, 1)
    grad = grad * vig[:, :, None]
    return Image.fromarray(grad.astype(np.uint8)).convert("RGBA")


BG = make_bg()


def text_w(txt, f):
    return f.getlength(txt)


def wrap(txt, f, maxw):
    words, lines, cur = txt.split(), [], ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if text_w(test, f) <= maxw:
            cur = test
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def draw_rich(img, parts, f, cy, t, start, center=True, x=None, shadow=True):
    """parts: [(text, color)]; animiert mit Fade + Slide-up."""
    p = appear(t, start)
    if p <= 0:
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    total = sum(text_w(s, f) for s, _ in parts)
    cx = (W - total) / 2 if center else x
    yy = cy + (1 - p) * 50
    a = int(255 * p)
    for s, col in parts:
        if shadow:
            d.text((cx + 3, yy + 5), s, font=f, fill=(0, 0, 0, int(a * 0.45)), anchor="lm")
        d.text((cx, yy), s, font=f, fill=col + (a,), anchor="lm")
        cx += text_w(s, f)
    img.alpha_composite(layer)


def draw_par(img, txt, f, cy, t, start, color=WHITE, maxw=900, lh=1.3, stagger=0.12):
    lines = wrap(txt, f, maxw)
    step = f.size * lh
    y0 = cy - step * (len(lines) - 1) / 2
    for i, ln in enumerate(lines):
        draw_rich(img, [(ln, color)], f, y0 + i * step, t, start + i * stagger)
    return y0 + step * len(lines)


def chip(img, label, t, start, color=YEL, cy=250):
    p = appear(t, start, 0.35)
    if p <= 0:
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    tw = text_w(label, F_CHIP)
    pw, ph = tw + 64, 74
    x0 = (W - pw) / 2
    y0 = cy - ph / 2 + (1 - p) * 30
    a = int(255 * p)
    d.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], radius=37, fill=color + (a,))
    d.text((W / 2, y0 + ph / 2), label, font=F_CHIP, fill=(15, 15, 25, a), anchor="mm")
    img.alpha_composite(layer)


# ---------------------------------------------------------------- Ampel

_lamp_cache = {}


def lamp_sprites(color, r):
    key = (color, r)
    if key in _lamp_cache:
        return _lamp_cache[key]
    pad = int(r * 1.6)
    size = 2 * (r + pad)
    ss = 4
    def disc(fill):
        big = Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))
        ImageDraw.Draw(big).ellipse(
            [pad * ss, pad * ss, (pad + 2 * r) * ss, (pad + 2 * r) * ss], fill=fill)
        return big.resize((size, size), Image.LANCZOS)
    off = disc(lerp_col((18, 18, 24), color, 0.16) + (255,))
    on_core = disc(lerp_col(color, WHITE, 0.12) + (255,))
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([pad - r * 0.3, pad - r * 0.3, pad + 2.3 * r, pad + 2.3 * r],
                                 fill=color + (200,))
    glow = glow.filter(ImageFilter.GaussianBlur(r * 0.55))
    on = glow.copy()
    on.alpha_composite(on_core)
    # Glanzpunkt
    hl = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse([pad + r * 0.45, pad + r * 0.3, pad + r * 1.05, pad + r * 0.75],
                               fill=(255, 255, 255, 70))
    hl = hl.filter(ImageFilter.GaussianBlur(r * 0.12))
    on.alpha_composite(hl)
    _lamp_cache[key] = (off, on, pad)
    return _lamp_cache[key]


def draw_traffic_light(img, cx, cy, scale, state, alpha=1.0, horizontal=False):
    """state: (r, y, g) Intensitäten 0..1"""
    if alpha <= 0:
        return
    r = int(62 * scale)
    gap = int(28 * scale)
    n = 3
    if horizontal:
        hw = n * 2 * r + (n + 1) * gap
        hh = 2 * r + 2 * gap
    else:
        hw = 2 * r + 2 * gap
        hh = n * 2 * r + (n + 1) * gap
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0 = cx - hw / 2, cy - hh / 2
    if not horizontal:  # Mast
        d.rectangle([cx - 14 * scale, y0 + hh, cx + 14 * scale, y0 + hh + 140 * scale],
                    fill=(40, 43, 58, 255))
    d.rounded_rectangle([x0 - 4, y0 - 4, x0 + hw + 4, y0 + hh + 4], radius=int(40 * scale),
                        fill=(60, 64, 82, 255))
    d.rounded_rectangle([x0, y0, x0 + hw, y0 + hh], radius=int(36 * scale),
                        fill=(26, 28, 38, 255))
    for i, (col, k) in enumerate(zip((RED, YEL, GRN), state)):
        off, on, pad = lamp_sprites(col, r)
        if horizontal:
            lx, ly = x0 + gap + i * (2 * r + gap), y0 + gap
        else:
            lx, ly = x0 + gap, y0 + gap + i * (2 * r + gap)
        pos = (int(lx - pad), int(ly - pad))
        layer.alpha_composite(off, pos)
        if k > 0.01:
            on_k = on.copy()
            a = np.array(on_k)
            a[..., 3] = (a[..., 3] * clamp(k)).astype(np.uint8)
            layer.alpha_composite(Image.fromarray(a), pos)
    if alpha < 1:
        a = np.array(layer)
        a[..., 3] = (a[..., 3] * alpha).astype(np.uint8)
        layer = Image.fromarray(a)
    img.alpha_composite(layer)


def soft(t, on_at, off_at=None, fade=0.12):
    k = clamp((t - on_at) / fade)
    if off_at is not None:
        k *= 1 - clamp((t - off_at) / fade)
    return k


# ---------------------------------------------------------------- Szenen

def s_hook(img, t):
    draw_rich(img, [("Warum ist ", WHITE), ("Grün", GRN)], F_HEAD, 330, t, 0.0)
    draw_rich(img, [("länger als ", WHITE), ("Rot", RED), ("?", WHITE)], F_HEAD, 440, t, 0.12)
    # Ampel schaltet schnell durch
    cyc = [(1, 0, 0), (1, 1, 0), (0, 0, 1), (0, 1, 0), (1, 0, 0)]
    seg = t / 0.6
    i = int(seg) % len(cyc)
    j = (i + 1) % len(cyc)
    k = ease_in_out((seg % 1) * 3 - 2)
    st = tuple(lerp(a, b, k) for a, b in zip(cyc[i], cyc[j]))
    p = appear(t, 0.1, 0.6)
    draw_traffic_light(img, W / 2, 1000 + (1 - p) * 80, 1.35, st, alpha=p)
    draw_par(img, "Jeder kennt's. Aber stimmt das überhaupt?", F_BODY, 1500, t, 0.9, MUTED)


def s_spoiler(img, t):
    chip(img, "SPOILER", t, 0.0, RED)
    draw_par(img, "Nicht immer! Es kommt drauf an, wo du stehst.", F_HEAD_S, 450, t, 0.15)
    for k, (cx, name, st, col) in enumerate([
        (300, "Hauptstraße", (0, 0, 1), GRN),
        (780, "Nebenstraße", (1, 0, 0), RED),
    ]):
        p = appear(t, 0.5 + k * 0.2, 0.5)
        draw_traffic_light(img, cx, 980 + (1 - p) * 60, 0.95, st, alpha=p)
        draw_rich(img, [(name, col)], F_SMALL, 1320, t, 0.7 + k * 0.2, center=False,
                  x=cx - text_w(name, F_SMALL) / 2)
    draw_par(img, "Gleiche Kreuzung – ganz andere Wartezeit.", F_BODY, 1470, t, 1.4, MUTED)


def bar(img, x, y, w, h, frac_green, p, label, label_col):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=PANEL + (255,))
    gw = w * frac_green * p
    rw = w * (1 - frac_green) * p
    if gw > h:
        d.rounded_rectangle([x, y, x + gw, y + h], radius=h // 2, fill=GRN + (255,))
    if rw > 4:
        d.rounded_rectangle([x + w - rw, y, x + w, y + h], radius=h // 2, fill=RED + (255,))
    if p > 0.6:
        a = int(255 * clamp((p - 0.6) / 0.4))
        if frac_green > 0.15:
            d.text((x + 30, y + h / 2), f"{int(frac_green * 100)} % Grün", font=F_SMALL,
                   fill=(10, 30, 15, a), anchor="lm")
        if frac_green < 0.85:
            d.text((x + w - 30, y + h / 2), f"{int(round((1 - frac_green) * 100))} % Rot",
                   font=F_SMALL, fill=(50, 10, 10, a), anchor="rm")
    img.alpha_composite(layer)
    draw_rich(img, [(label, label_col)], F_BODY, y - 50, 99, 0, center=False, x=x, shadow=False) \
        if p > 0 else None


def s_verkehr(img, t):
    chip(img, "GRUND 1", t, 0.0)
    draw_par(img, "Mehr Autos = mehr Grün", F_HEAD_S, 400, t, 0.1, maxw=1000)
    p1 = ease_out((t - 0.5) / 0.9)
    p2 = ease_out((t - 0.8) / 0.9)
    if t > 0.5:
        bar(img, 110, 700, 860, 100, 0.70, p1, "Hauptstraße", WHITE)
    if t > 0.8:
        bar(img, 110, 960, 860, 100, 0.30, p2, "Nebenstraße", WHITE)
    draw_par(img, "Die Hauptstraße hat viel mehr Verkehr – also bekommt sie den "
                  "Großteil der Grünzeit. Auf der Nebenstraße ist es umgekehrt.",
             F_BODY, 1340, t, 1.4, MUTED)


def s_umlauf(img, t):
    chip(img, "GRUND 2", t, 0.0)
    draw_par(img, "Der Ampel-Umlauf", F_HEAD_S, 400, t, 0.1)
    p = ease_in_out((t - 0.4) / 1.6)
    cx, cy, R, ring = W / 2, 860, 270, 70
    segs = [(0.55, GRN, "Hauptstraße"), (0.10, YEL, "Zwischenzeit"),
            (0.25, (52, 170, 255), "Nebenstraße"), (0.10, YEL, "")]
    ss = 2
    size = int((R + 10) * 2 * ss)
    big = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    box = [10 * ss, 10 * ss, size - 10 * ss, size - 10 * ss]
    d.ellipse(box, fill=PANEL + (255,))
    start = -90.0
    sweep_total = 360 * p
    acc = 0.0
    for frac, col, _ in segs:
        ang = 360 * frac
        vis = clamp(sweep_total - acc, 0, ang)
        if vis > 0.2:
            d.pieslice(box, start + acc, start + acc + vis, fill=col + (255,))
        acc += ang
    inner = (R - ring) * ss
    c = size / 2
    d.ellipse([c - inner, c - inner, c + inner, c + inner], fill=(0, 0, 0, 0))
    big = big.resize((size // ss, size // ss), Image.LANCZOS)
    # Loch ausstanzen
    a = np.array(big)
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    rr = np.hypot(xx - a.shape[1] / 2, yy - a.shape[0] / 2)
    a[..., 3] = np.where(rr < R - ring, 0, a[..., 3])
    big = Image.fromarray(a)
    fade = appear(t, 0.2, 0.4)
    a = np.array(big)
    a[..., 3] = (a[..., 3] * fade).astype(np.uint8)
    img.alpha_composite(Image.fromarray(a), (int(cx - big.width / 2), int(cy - big.height / 2)))
    secs = int(round(90 * p))
    draw_rich(img, [(f"{secs} s", WHITE)], F_BIG, cy - 10, t, 0.2)
    # Legende
    lx = 95
    for i, (col, name) in enumerate([(GRN, "Hauptstraße"), ((52, 170, 255), "Nebenstraße"),
                                     (YEL, "Zwischenzeit")]):
        pp = appear(t, 1.6 + i * 0.12)
        if pp > 0:
            layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            dd = ImageDraw.Draw(layer)
            y = 1215
            x = lx + i * 280
            dd.ellipse([x, y - 16, x + 32, y + 16], fill=col + (int(255 * pp),))
            dd.text((x + 46, y), name.replace("straße", "str."), font=F_SMALL,
                    fill=MUTED + (int(255 * pp),), anchor="lm")
            img.alpha_composite(layer)
    draw_par(img, "Ein Umlauf dauert meist 60–120 Sekunden – verteilt nach Verkehrsmenge.",
             F_BODY, 1430, t, 2.0, MUTED)


def s_sensor(img, t):
    chip(img, "GRUND 3", t, 0.0)
    draw_par(img, "Sensoren im Boden", F_HEAD_S, 400, t, 0.1)
    fade = appear(t, 0.3, 0.4)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = int(255 * fade)
    # Straße
    rx0, rx1 = 340, 740
    d.rectangle([rx0, 560, rx1, 1230], fill=(44, 46, 58, a))
    for y in range(570, 1230, 90):
        d.rectangle([W / 2 - 6, y, W / 2 + 6, y + 50], fill=(200, 200, 210, int(a * 0.6)))
    stop_y = 1060
    d.rectangle([rx0, stop_y, rx1, stop_y + 14], fill=(240, 240, 240, a))
    # Induktionsschleife
    car_y = lerp(520, 905, ease_out((t - 0.6) / 1.3))
    on_loop = t > 1.75
    loop_col = YEL if on_loop else (110, 110, 130)
    pulse = 0.5 + 0.5 * math.sin(t * 12) if on_loop else 0
    d.rounded_rectangle([rx0 + 40, 880, rx1 - 40, 1040], radius=18,
                        outline=loop_col + (int(a * (0.6 + 0.4 * pulse)),), width=8)
    # Auto (von oben)
    cx = (rx0 + W / 2) / 2 + 20
    cw, ch = 130, 210
    d.rounded_rectangle([cx - cw / 2, car_y - ch / 2, cx + cw / 2, car_y + ch / 2], radius=30,
                        fill=(52, 170, 255, a))
    d.rounded_rectangle([cx - cw / 2 + 16, car_y + 10, cx + cw / 2 - 16, car_y + 60], radius=12,
                        fill=(20, 40, 70, a))
    d.rounded_rectangle([cx - cw / 2 + 16, car_y - 80, cx + cw / 2 - 16, car_y - 40], radius=12,
                        fill=(20, 40, 70, a))
    img.alpha_composite(layer)
    if on_loop:
        draw_rich(img, [("Auto erkannt!", YEL)], F_SMALL, 1290, t, 1.8)
    st = (1 - soft(t, 2.4), soft(t, 2.0, 2.6), soft(t, 2.6))
    draw_traffic_light(img, 880, 760, 0.55, st, alpha=fade)
    draw_par(img, "Kommt auf der Nebenstraße niemand, bleibt die Hauptstraße einfach grün.",
             F_BODY, 1450, t, 2.3, MUTED)


def s_welle(img, t):
    chip(img, "GRUND 4", t, 0.0)
    draw_par(img, "Die Grüne Welle", F_HEAD_S, 400, t, 0.1)
    fade = appear(t, 0.3, 0.4)
    xs = [180 + i * 180 for i in range(5)]
    car_x = lerp(60, 1020, clamp((t - 0.6) / 3.0))
    for i, x in enumerate(xs):
        g = soft(t, 0.6 + (x - 60) / 960 * 3.0 - 0.45)
        draw_traffic_light(img, x, 760, 0.42, (1 - g, 0, g), alpha=fade)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = int(255 * fade)
    d.rectangle([0, 1000, W, 1120], fill=(44, 46, 58, a))
    for x in range(0, W, 120):
        d.rectangle([x, 1054, x + 60, 1066], fill=(200, 200, 210, int(a * 0.6)))
    d.rounded_rectangle([car_x - 90, 1020, car_x + 90, 1100], radius=24, fill=(52, 170, 255, a))
    img.alpha_composite(layer)
    draw_rich(img, [("Grün. Grün. Grün. Grün.", GRN)], F_BODY, 1220, t, 1.2)
    draw_par(img, "Ampeln sind so abgestimmt, dass du bei passendem Tempo durchrollst.",
             F_BODY, 1420, t, 1.8, MUTED)


def s_gehirn(img, t):
    chip(img, "GRUND 5", t, 0.0)
    draw_par(img, "Dein Kopf trickst dich aus", F_HEAD_S, 400, t, 0.1, maxw=1000)
    p1 = ease_out((t - 0.6) / 1.4)
    p2 = ease_out((t - 0.9) / 0.6)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, w, h = 110, 860, 90
    for y, frac, col, p in [(760, 1.0, RED, p1), (1080, 0.35, GRN, p2)]:
        if p > 0:
            d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=PANEL + (255,))
            ww = max(h, w * frac * p)
            d.rounded_rectangle([x, y, x + ww, y + h], radius=h // 2, fill=col + (255,))
    img.alpha_composite(layer)
    if t > 0.6:
        draw_rich(img, [("30 s Rot fühlen sich an wie…", WHITE)], F_SMALL, 710, t, 0.6,
                  center=False, x=x)
    if t > 0.9:
        draw_rich(img, [("30 s Grün? Merkst du kaum.", WHITE)], F_SMALL, 1030, t, 0.9,
                  center=False, x=x)
    draw_rich(img, [("…eine Ewigkeit", RED)], F_SMALL, 900, t, 1.8, center=False, x=x)
    draw_par(img, "Warten fühlt sich länger an als Fahren – Rot wird gefühlt überschätzt.",
             F_BODY, 1400, t, 2.0, MUTED)


def s_fazit(img, t):
    chip(img, "FAZIT", t, 0.0, GRN)
    draw_par(img, "Wo mehr Verkehr ist, gibt's mehr Grün.", F_HEAD_S, 450, t, 0.15)
    p = appear(t, 0.4, 0.6)
    draw_traffic_light(img, W / 2, 960, 1.0, (0, 0, soft(t, 0.8)), alpha=p)
    draw_par(img, "Folge für mehr Alltagsfragen!", F_BODY, 1400, t, 1.4, YEL)


SCENES = [
    (s_hook, 3.4),
    (s_spoiler, 3.8),
    (s_verkehr, 5.2),
    (s_umlauf, 5.0),
    (s_sensor, 5.0),
    (s_welle, 4.6),
    (s_gehirn, 4.8),
    (s_fazit, 3.8),
]
TOTAL = sum(d for _, d in SCENES)


# ---------------------------------------------------------------- Audio

def make_audio(path, total, cuts):
    sr = 44100
    n = int(total * sr)
    out = np.zeros(n)
    t = np.arange(n) / sr
    bpm = 100
    beat = 60 / bpm
    rng = np.random.default_rng(7)

    def add(sig, at, gain=1.0):
        i = int(at * sr)
        if i >= n:
            return
        e = min(n, i + len(sig))
        out[i:e] += sig[: e - i] * gain

    # Kick
    kl = int(0.35 * sr)
    kt = np.arange(kl) / sr
    kick = np.sin(2 * np.pi * (45 + 90 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 9)
    # Snare/Clap (gefiltertes Rauschen)
    sl = int(0.2 * sr)
    st = np.arange(sl) / sr
    noise = rng.standard_normal(sl)
    noise = np.convolve(noise, np.ones(6) / 6, mode="same")
    snare = noise * np.exp(-st * 22)
    # Hi-Hat
    hl = int(0.05 * sr)
    hat = np.diff(rng.standard_normal(hl + 1)) * np.exp(-np.arange(hl) / sr * 90)

    b = 0
    while b * beat < total:
        at = b * beat
        if b % 2 == 0:
            add(kick, at, 0.85)
        else:
            add(snare, at, 0.22)
        add(hat, at + beat / 2, 0.10)
        add(hat, at, 0.05)
        b += 1

    # Akkord-Pad Am - F - C - G, je 2 Takte
    chords = [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63],
              [196.0, 261.63, 329.63], [196.0, 246.94, 293.66]]
    bar_len = 4 * beat
    i = 0
    while i * 2 * bar_len < total:
        ch = chords[i % 4]
        s0 = i * 2 * bar_len
        L = int(2 * bar_len * sr)
        tt = np.arange(L) / sr
        env = np.minimum(1, tt / 0.4) * np.minimum(1, (2 * bar_len - tt) / 0.4)
        sig = sum(np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt + 0.5)
                  for f in ch)
        sig *= (0.8 + 0.2 * np.sin(2 * np.pi * 0.25 * tt))
        add(sig * env, s0, 0.045)
        # Bass
        bass = np.sin(2 * np.pi * ch[0] / 2 * tt) * env
        add(bass, s0, 0.16)
        i += 1

    # Blips bei Szenenwechseln
    bl = int(0.18 * sr)
    bt = np.arange(bl) / sr
    for k, c in enumerate(cuts):
        f = 880 if k % 2 == 0 else 1046.5
        blip = np.sin(2 * np.pi * f * bt) * np.exp(-bt * 25)
        add(blip, c, 0.18)

    # Fade-out
    fo = np.clip((total - t) / 1.5, 0, 1)
    out *= fo
    out = out / (np.max(np.abs(out)) + 1e-9) * 0.85
    pcm = (out * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- Render

def render():
    cuts, acc = [], 0.0
    for _, d in SCENES:
        cuts.append(acc)
        acc += d
    wav = os.path.join(HERE, "_audio.wav")
    make_audio(wav, TOTAL, cuts)

    proc = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", wav,
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", OUT,
    ], stdin=subprocess.PIPE)

    nframes = int(TOTAL * FPS)
    for fi in range(nframes):
        gt = fi / FPS
        acc = 0.0
        for fn, d in SCENES:
            if gt < acc + d:
                break
            acc += d
        lt = gt - acc
        img = BG.copy()
        fn(img, lt)
        # Ausblenden am Szenenende
        out_k = clamp((d - lt) / 0.25)
        if out_k < 1:
            img = Image.blend(BG, img, out_k)
        proc.stdin.write(img.convert("RGB").tobytes())
        if fi % 150 == 0:
            print(f"frame {fi}/{nframes}", flush=True)
    proc.stdin.close()
    proc.wait()
    os.remove(wav)
    print("fertig:", OUT)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "preview":
        # Standbilder je Szene zur Kontrolle
        acc = 0
        for i, (fn, d) in enumerate(SCENES):
            img = BG.copy()
            fn(img, d - 0.3)
            img.convert("RGB").save(os.path.join(sys.argv[2], f"scene{i}.png"))
    else:
        render()
