"""Render 'Warum Casinos keine Uhren haben' – gold neon / dark reflective style (1080x1920, 30 fps).

Inputs: voice.mp3, words.json, music.wav   Output: casino-uhren.mp4
Usage: python3 render.py            -> full video
       python3 render.py 100 400    -> preview stills of those frames
"""
import json, math, os, random, subprocess, sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, S, FPS = 1080, 1920, 2, 30
SW, SH = W * S, H * S
SPEED = 1.15
FY = 1180                       # floor line (1x)

F_XB = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"
F_B = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
F_BL = "/usr/share/fonts/opentype/inter/Inter-Black.otf" if os.path.exists(
    "/usr/share/fonts/opentype/inter/Inter-Black.otf") else F_XB

GOLD = (255, 200, 70)
GOLD_D = (200, 140, 30)
CORAL = (255, 92, 80)
RED = (255, 60, 60)
WHITE = (255, 255, 255)
NAVY = (28, 45, 110)

# ------------------------------------------------------------------ timing
words = [(w, s / SPEED, e / SPEED) for w, s, e in json.load(open(os.path.join(HERE, "words.json")))]
DUR = words[-1][2] + 1.3
NFRAMES = int(DUR * FPS)


def norm(w):
    return w.strip(".,?:!").lower()


def t_of(word, nth=1):
    n = 0
    for w, s, e in words:
        if norm(w) == word.lower():
            n += 1
            if n == nth:
                return s
    raise KeyError(word)


T = {k: t_of(*v) if isinstance(v, tuple) else t_of(v) for k, v in {
    "uhren": "uhren", "fenster": "fenster", "zufall": "zufall", "stell": "stell", "acht": "acht",
    "500a": ("fünfhundert", 1), "drinnen": "drinnen", "sonnen": "sonnenuntergang", "zeit": ("zeit", 1),
    "plan": ("und", 2), "jedes": "jedes", "roulette": "roulette", "stunden": "stunden", "chips_s": ("und", 3),
    "chips": "chips", "spielgeld": "spielgeld", "gaenge": "gänge", "ausgang": "ausgang", "drinks": ("und", 4), "gratis": "gratis",
    "handy": "irgendwann", "vier": "vier", "fast": ("fast", 1), "punch": ("das", 4), "gezeigt": "gezeigt",
    "folg": "folg", "teil": "teil", "automat": "spielautomaten"}.items()}

T["punch"] = next(words[i][1] for i in range(len(words) - 1)
                  if words[i][0] == "Das" and words[i + 1][0].startswith("Casino"))

SCENES = [("hook", 0), ("enter", T["stell"]), ("light", T["drinnen"]), ("edge", T["plan"]),
          ("chips", T["chips_s"]), ("maze", T["gaenge"] - 0.25), ("drinks", T["drinks"]),
          ("phone", T["handy"]), ("punch", T["punch"]), ("cta", T["folg"])]
BOUNDS = [(n, s, SCENES[i + 1][1] if i + 1 < len(SCENES) else DUR) for i, (n, s) in enumerate(SCENES)]

DISPLAY = {"fünfhundert": "500 €", "acht": "20 Uhr", "vier": "4 Uhr", "zwei": "2", "drei": "3 %",
           "prozent": None, "uhr": None}
HILITE = {"uhren", "fenster", "zufall", "zeit", "plan", "casino", "chips", "labyrinth", "gratis", "gestohlen",
          "gezeigt", "fast", "spielgeld", "licht", "500 €", "20 uhr", "4 uhr", "3 %", "nie", "bleibst", "geld",
          "stunden", "gewinnt", "nichts"}
CAPS = []  # (text, start, end, hilite)
for i, (w, s, e) in enumerate(words):
    k = norm(w)
    disp = DISPLAY.get(k, w.strip(".,:!"))
    if disp is None:
        continue
    nxt = words[i + 1][1] if i + 1 < len(words) else e + 0.8
    CAPS.append((disp.lower() if not disp[0].isdigit() else disp, s, max(nxt, s + 0.12), disp.lower() in HILITE))
# merge: a skipped word extends the previous caption
for i in range(len(CAPS) - 1):
    CAPS[i] = (CAPS[i][0], CAPS[i][1], CAPS[i + 1][1], CAPS[i][3])


# ------------------------------------------------------------------ helpers
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def eo(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def eb(x):
    x = clamp(x)
    return 1 + 2.70158 * (x - 1) ** 3 + 1.70158 * (x - 1) ** 2


def eio(x):
    x = clamp(x)
    return 3 * x * x - 2 * x ** 3


_F = {}


def font(size, path=F_XB):
    size = max(int(size), 1)
    if (size, path) not in _F:
        _F[(size, path)] = ImageFont.truetype(path, size)
    return _F[(size, path)]


def ctext(d, xy, txt, size, fill, path=F_XB, stroke=0, sfill=(0, 0, 0), maxw=None, anchor="mm"):
    f = font(size, path)
    if maxw:
        while d.textlength(txt, font=f) > maxw and size > 10:
            size -= 3
            f = font(size, path)
    d.text(xy, txt, font=f, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=sfill)


def spaced(d, cx, cy, txt, size, fill, spacing, path=F_XB):
    f = font(size, path)
    widths = [d.textlength(c, font=f) for c in txt]
    total = sum(widths) + spacing * (len(txt) - 1)
    x = cx - total / 2
    for c, w_ in zip(txt, widths):
        d.text((x, cy), c, font=f, fill=fill, anchor="lm")
        x += w_ + spacing


def P(x, y):  # 1x coords -> 2x
    return (x * S, y * S)


def pill(d, cx, cy, txt, size=44, k=1.0, col=GOLD, fill=(12, 10, 4, 230)):
    if k <= 0.02:
        return
    f = font(size * S * (0.7 + 0.3 * k))
    tw = d.textlength(txt, font=f)
    w_, h_ = tw + 60 * S, size * S * 1.7
    d.rounded_rectangle([cx * S - w_ / 2, cy * S - h_ / 2, cx * S + w_ / 2, cy * S + h_ / 2], radius=16 * S,
                        fill=fill, outline=col, width=5 * S)
    d.text((cx * S, cy * S), txt, font=f, fill=col, anchor="mm")


def wire_box(d, x, yb, w, h, depth=60, cols=5, rows=6, col=GOLD, alpha=255, width=3, fill=None):
    """Gold wireframe box standing on yb (bottom front edge). 1x coords."""
    c = col + (alpha,)
    dx, dy = depth * 0.8, -depth * 0.55
    fr = [P(x, yb - h), P(x + w, yb - h), P(x + w, yb), P(x, yb)]
    bk = [(px + dx * S, py + dy * S) for px, py in fr]
    if fill:
        d.polygon(fr, fill=fill)
    for i in range(4):
        d.line([fr[i], bk[i]], fill=c, width=width * S)
    d.line(bk + [bk[0]], fill=c, width=width * S)
    for i in range(1, cols):
        xx = x + w * i / cols
        d.line([P(xx, yb - h), P(xx, yb)], fill=c, width=max(1, width - 1) * S)
        d.line([P(xx, yb - h), (xx * S + dx * S, (yb - h) * S + dy * S)], fill=c, width=max(1, width - 1) * S)
    for j in range(1, rows):
        yy = yb - h * j / rows
        d.line([P(x, yy), P(x + w, yy)], fill=c, width=max(1, width - 1) * S)
        d.line([P(x + w, yy), ((x + w) * S + dx * S, yy * S + dy * S)], fill=c, width=max(1, width - 1) * S)
    d.line(fr + [fr[0]], fill=c, width=(width + 1) * S)


def strike(d, cx, cy, r, k):
    if k <= 0:
        return
    r = r * k
    d.line([P(cx - r, cy - r), P(cx + r, cy + r)], fill=RED, width=12 * S)
    d.line([P(cx - r, cy + r), P(cx + r, cy - r)], fill=RED, width=12 * S)


def clock(d, cx, cy, r, hour_a, min_a, col=GOLD, width=6):
    d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], outline=col, width=width * S,
              fill=(15, 12, 5, 220))
    for i in range(12):
        a = i * math.tau / 12
        d.line([P(cx + math.cos(a) * r * .8, cy + math.sin(a) * r * .8),
                P(cx + math.cos(a) * r * .92, cy + math.sin(a) * r * .92)], fill=col, width=width * S // 2 + 1)
    d.line([P(cx, cy), P(cx + math.sin(hour_a) * r * .5, cy - math.cos(hour_a) * r * .5)], fill=col,
           width=width * S + 2)
    d.line([P(cx, cy), P(cx + math.sin(min_a) * r * .78, cy - math.cos(min_a) * r * .78)], fill=col,
           width=width * S)


# ------------------------------------------------------------------ sprites
def shaded_sphere(r, base, spec=0.6):
    yy, xx = np.mgrid[-r:r, -r:r] + 0.5
    nx, ny = xx / r, yy / r
    m = nx ** 2 + ny ** 2
    nz = np.sqrt(np.clip(1 - m, 0, 1))
    L = np.array([-0.45, -0.6, 0.66])
    lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    rim = np.clip((m - 0.75) * 3, 0, 1) * np.clip(ny + 0.2, 0, 1) * 0.5     # warm rim light from floor
    hv = np.array([-0.2, -0.3, 0.93]); hv /= np.linalg.norm(hv)
    sp = np.clip(nx * hv[0] + ny * hv[1] + nz * hv[2], 0, 1) ** 40 * spec
    col = np.array(base)[None, None, :] * (0.25 + 0.85 * lam[..., None]) + 255 * sp[..., None] \
          + np.array(GOLD)[None, None, :] * rim[..., None]
    a = np.clip((1 - np.sqrt(m)) * r, 0, 1)
    img = np.dstack([np.clip(col, 0, 255), a * 255]).astype(np.uint8)
    return Image.fromarray(img, "RGBA")


def shaded_capsule(w, h, base):
    r = w / 2
    yy, xx = np.mgrid[0:h, 0:w] + 0.5
    nx = (xx - r) / r
    cy = np.clip(yy, r, h - r)
    ny = (yy - cy) / r
    m = nx ** 2 + ny ** 2
    nz = np.sqrt(np.clip(1 - m, 0, 1))
    L = np.array([-0.45, -0.6, 0.66])
    lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    hv = np.array([-0.25, -0.2, 0.95]); hv /= np.linalg.norm(hv)
    sp = np.clip(nx * hv[0] + ny * hv[1] + nz * hv[2], 0, 1) ** 30 * 0.45
    rim = np.clip((nx ** 2 - 0.7) * 3, 0, 1) * 0.4
    col = np.array(base)[None, None, :] * (0.3 + 0.9 * lam[..., None]) + 255 * sp[..., None] \
          + np.array(GOLD)[None, None, :] * rim[..., None]
    a = np.clip((1 - np.sqrt(m)) * r, 0, 1)
    return Image.fromarray(np.dstack([np.clip(col, 0, 255), a * 255]).astype(np.uint8), "RGBA")


def make_figure():
    hr, bw, bh = 72 * S, 150 * S, 250 * S
    im = Image.new("RGBA", (bw + 40 * S, bh + 2 * hr + 30 * S), (0, 0, 0, 0))
    cx = im.width // 2
    body = shaded_capsule(bw, bh, NAVY)
    d = ImageDraw.Draw(body)
    d.rectangle([bw * .38, bh * .18, bw * .48, bh * .62], fill=GOLD)      # gold details like reference
    d.rectangle([bw * .58, bh * .2, bw * .7, bh * .26], fill=GOLD)
    im.alpha_composite(body, (cx - bw // 2, 2 * hr + 18 * S))
    im.alpha_composite(shaded_sphere(hr, (235, 238, 245)), (cx - hr, 0))
    return im


def coin_sprite(r):
    im = Image.new("RGBA", (2 * r, 2 * r), (0, 0, 0, 0))
    sp = shaded_sphere(r, (230, 170, 40), spec=0.8)
    im.alpha_composite(sp)
    d = ImageDraw.Draw(im)
    d.ellipse([r * .25, r * .25, r * 1.75, r * 1.75], outline=(255, 230, 140, 200), width=max(2, r // 8))
    return im


def chip_sprite(r, col):
    im = Image.new("RGBA", (2 * r, int(r * 1.3)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    hgt = int(r * 0.25)
    d.ellipse([0, hgt, 2 * r - 1, int(r * 1.3) - 1], fill=tuple(int(c * .55) for c in col))
    d.rectangle([0, int(r * .5), 2 * r - 1, int(r * .5) + hgt], fill=tuple(int(c * .55) for c in col))
    d.ellipse([0, 0, 2 * r - 1, r], fill=col)
    for i in range(6):
        a = i * math.tau / 6
        x, y = r + math.cos(a) * r * .8, r / 2 + math.sin(a) * r * .4
        d.ellipse([x - r * .12, y - r * .07, x + r * .12, y + r * .07], fill=WHITE)
    d.ellipse([r * .45, r * .22, r * 1.55, r * .78], outline=(255, 255, 255, 160), width=max(2, r // 14))
    return im


FIG = make_figure()
COIN = coin_sprite(34 * S)
CHIPS = [chip_sprite(70 * S, c) for c in [(220, 40, 50), (30, 90, 210), (30, 150, 70), (20, 20, 25)]]


def glow_sprite(r, color, power=2.0):
    yy, xx = np.mgrid[-r:r, -r:r]
    a = np.clip(1 - np.sqrt(xx ** 2 + yy ** 2) / r, 0, 1) ** power
    img = np.zeros((2 * r, 2 * r, 4), np.uint8)
    img[..., :3] = color
    img[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(img, "RGBA")


GLOW_G = glow_sprite(260 * S, GOLD, 2.5)
GLOW_R = glow_sprite(200 * S, RED, 2.5)


def paste_a(base, sp, cx, cy, alpha=1.0):
    if alpha <= 0.01:
        return
    if alpha < 0.99:
        sp = sp.copy()
        sp.putalpha(sp.getchannel("A").point(lambda v: int(v * alpha)))
    base.alpha_composite(sp, (int(cx - sp.width / 2), int(cy - sp.height / 2)))


def figure(layer, x, t, tilt=0.0, scale=1.0, walk=0.0, alpha=1.0):
    """Place the figure standing on the floor at x (1x)."""
    f = FIG if scale == 1 else FIG.resize((int(FIG.width * scale), int(FIG.height * scale)), Image.LANCZOS)
    bob = abs(math.sin(t * 9)) * 14 * S * walk
    if tilt:
        f = f.rotate(tilt, resample=Image.BICUBIC, expand=True, center=(f.width / 2, f.height))
    d = ImageDraw.Draw(layer)
    d.ellipse([x * S - 90 * S * scale, FY * S - 14 * S, x * S + 90 * S * scale, FY * S + 14 * S],
              fill=(0, 0, 0, 160))
    paste_a(layer, f, x * S, FY * S - f.height / 2 - bob, alpha)


# ------------------------------------------------------------------ background (1x, numpy float)
def make_bg():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    bg = np.zeros((H, W, 3), np.float32)
    fog = np.exp(-(((xx - W / 2) / 520) ** 2 + ((yy - FY + 120) / 380) ** 2))
    bg += fog[..., None] * np.array([70, 48, 12], np.float32)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # skyline line art (dim gold)
    random.seed(11)
    x = -20
    while x < W + 20:
        bw = random.randint(50, 120)
        bh = random.randint(80, 330)
        col = (255, 200, 70, random.randint(50, 95))
        d.rectangle([x, FY - bh, x + bw, FY], outline=col, width=2)
        for wy in range(FY - bh + 14, FY - 8, 22):
            for wx in range(x + 10, x + bw - 10, 18):
                if random.random() < 0.45:
                    d.rectangle([wx, wy, wx + 7, wy + 9], fill=(255, 205, 90, random.randint(40, 140)))
        if random.random() < 0.3:
            d.line([(x + bw / 2, FY - bh), (x + bw / 2, FY - bh - 50)], fill=col, width=2)
        x += bw + random.randint(4, 26)
    arr = np.asarray(im).astype(np.float32)
    a = arr[..., 3:4] / 255
    bg = bg * (1 - a) + arr[..., :3] * a
    # reflection of skyline
    L = H - FY
    refl = bg[FY - L:FY][::-1] * np.linspace(0.35, 0, L)[:, None, None]
    bg[FY:] = bg[FY:] * 0.5 + refl
    # perspective floor lines
    fl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(fl)
    vx = W / 2
    for i in range(-12, 13):
        d.line([(vx + i * 30, FY), (vx + i * 260, H)], fill=(255, 200, 70, 26), width=2)
    y = FY
    gap = 8
    while y < H:
        d.line([(0, y), (W, y)], fill=(255, 200, 70, 22), width=2)
        y += gap
        gap *= 1.35
    d.line([(0, FY), (W, FY)], fill=(255, 200, 70, 80), width=2)
    arr = np.asarray(fl).astype(np.float32)
    a = arr[..., 3:4] / 255
    bg = bg * (1 - a) + arr[..., :3] * a
    return bg


BG = make_bg()

# maze (DFS) for the labyrinth scene
MZ_C, MZ_R = 7, 7
random.seed(4)
walls = {(c, r): {"N": True, "S": True, "E": True, "W": True} for c in range(MZ_C) for r in range(MZ_R)}
order, stack, seen = [], [(0, MZ_R - 1)], {(0, MZ_R - 1)}
DIRS = {"N": (0, -1, "S"), "S": (0, 1, "N"), "E": (1, 0, "W"), "W": (-1, 0, "E")}
path_walk = [(0, MZ_R - 1)]
while stack:
    c, r = stack[-1]
    opts = [(k, c + dx, r + dy, o) for k, (dx, dy, o) in DIRS.items()
            if 0 <= c + dx < MZ_C and 0 <= r + dy < MZ_R and (c + dx, r + dy) not in seen]
    if opts:
        k, nc, nr, o = random.choice(opts)
        walls[(c, r)][k] = False
        walls[(nc, nr)][o] = False
        seen.add((nc, nr))
        stack.append((nc, nr))
    else:
        stack.pop()
    if stack:
        path_walk.append(stack[-1])


# ------------------------------------------------------------------ scenes (draw on 2x RGBA layer)
CX = W // 2


def casino_hall(d, k, x=150, w=560, h=520, alpha=255):
    hh = h * eo(k)
    if hh < 4:
        return
    wire_box(d, x, FY, w, hh, depth=110, cols=6, rows=6, alpha=alpha, fill=(20, 14, 4, 170))
    if k > 0.7:
        # neon sign
        sx, sy = x + w / 2 + 40, FY - hh - 70
        d.rounded_rectangle([P(sx - 170, sy - 48), P(sx + 170, sy + 48)], radius=14 * S, outline=GOLD,
                            width=5 * S, fill=(25, 16, 4, 255))
        spaced(d, sx * S, sy * S, "CASINO", 58 * S, GOLD, 10 * S)


def sc_hook(L, d, t, lt):
    casino_hall(d, lt / 0.8)
    k1 = eb((t - T["uhren"]) / 0.35)
    k2 = eb((t - T["fenster"]) / 0.35)
    if k1 > 0:
        clock(d, 300, 830, 85 * k1, t * 2, t * 12)
    strike(d, 300, 830, 95, eo((t - T["uhren"] - 0.3) / 0.25))
    if k2 > 0:
        r = 85 * k2
        d.rectangle([P(590 - r, 830 - r * 1.1), P(590 + r, 830 + r * 1.1)], outline=GOLD, width=6 * S,
                    fill=(15, 12, 5, 220))
        d.line([P(590, 830 - r * 1.1), P(590, 830 + r * 1.1)], fill=GOLD, width=4 * S)
        d.line([P(590 - r, 830), P(590 + r, 830)], fill=GOLD, width=4 * S)
        strike(d, 590, 830, 95, eo((t - T["fenster"] - 0.3) / 0.25))
    pill(d, 300, 975, "KEINE UHR", 38, k1)
    pill(d, 590, 975, "KEINE FENSTER", 38, k2)
    figure(L, 860, t, scale=0.85)
    if t > T["zufall"]:
        k = eb((t - T["zufall"]) / 0.4)
        ctext(d, P(860, 560), "?", 200 * S * k, GOLD)


def sc_enter(L, d, t, lt):
    casino_hall(d, 1, x=380, w=560, h=520)
    # door
    d.rectangle([P(560, FY - 230), P(700, FY)], fill=(60, 40, 8, 255), outline=GOLD, width=5 * S)
    walk = clamp((lt - 0.3) / 3.2)
    x = 140 + 350 * eio(walk)
    figure(L, x, t, walk=1.0 if 0 < walk < 1 else 0, scale=0.85,
           alpha=1 - clamp((lt - 3.8) / 0.5))
    pill(d, 230, 540, "20:00 UHR", 46, eb((t - T["acht"]) / 0.35))
    k = eb((t - T["500a"]) / 0.35)
    if k > 0:  # coin stack next to figure
        for i in range(6):
            paste_a(L, COIN, (x + 115) * S, (FY - 30 - i * 22) * S - (1 - k) * 200 * S)


def sc_light(L, d, t, lt):
    casino_hall(d, 1, x=190, w=700, h=420)
    # constant ceiling lamps
    for i in range(5):
        lx = 260 + i * 140
        paste_a(L, GLOW_G.resize((220 * S, 220 * S)), lx * S, (FY - 370) * S, 0.8)
        d.ellipse([P(lx - 16, FY - 386), P(lx + 16, FY - 354)], fill=(255, 240, 190))
    # sun & moon cycle outside, struck through
    ks = eb((t - T["sonnen"]) / 0.4)
    if ks > 0:
        d.ellipse([P(200 - 60 * ks, 640 - 60 * ks), P(200 + 60 * ks, 640 + 60 * ks)], fill=(255, 170, 40))
        d.ellipse([P(880 - 55 * ks, 640 - 55 * ks), P(880 + 55 * ks, 640 + 55 * ks)], fill=(220, 225, 240))
        d.ellipse([P(900 - 50 * ks, 620 - 50 * ks), P(900 + 50 * ks, 620 + 50 * ks)], fill=(0, 0, 0))
        strike(d, 200, 640, 80, eo((t - T["sonnen"] - 0.4) / 0.3))
        strike(d, 880, 640, 80, eo((t - T["sonnen"] - 0.9) / 0.3))
    pill(d, CX, 545, "LICHT: IMMER GLEICH", 42, eb((lt - 0.4) / 0.4))
    # spinning confused clock
    kz = eb((t - T["zeit"] + 0.6) / 0.4)
    if kz > 0:
        clock(d, 420, 960, 100 * kz, t * 7, t * 31)
        ctext(d, P(420, 960), "?", 120 * S * kz, CORAL, stroke=4 * S)
    figure(L, 720, t, scale=0.9, tilt=6 * math.sin(t * 2))


def roulette(L, d, cx, cy, r, ang):
    n = 37
    for i in range(n):
        a0 = ang + i * math.tau / n
        a1 = a0 + math.tau / n
        col = (30, 150, 70) if i == 0 else ((200, 35, 40) if i % 2 else (25, 22, 20))
        pts = [P(cx, cy)] + [P(cx + math.cos(a0 + (a1 - a0) * j / 3) * r, cy + math.sin(a0 + (a1 - a0) * j / 3) * r * .45)
                             for j in range(4)]
        d.polygon(pts, fill=col)
    d.ellipse([P(cx - r, cy - r * .45), P(cx + r, cy + r * .45)], outline=GOLD, width=7 * S)
    d.ellipse([P(cx - r * .45, cy - r * .2), P(cx + r * .45, cy + r * .2)], fill=(60, 40, 10), outline=GOLD,
              width=4 * S)
    d.rectangle([P(cx - r - 10, cy), P(cx + r + 10, cy + 60)], fill=(30, 20, 5))
    d.ellipse([P(cx - r, cy + 60 - r * .45), P(cx + r, cy + 60 + r * .45)], outline=GOLD_D, width=4 * S)
    d.rectangle([P(cx - r, cy), P(cx + r, cy + 60)], fill=(35, 24, 6))
    d.line([P(cx - r, cy), P(cx - r, cy + 60)], fill=GOLD, width=5 * S)
    d.line([P(cx + r, cy), P(cx + r, cy + 60)], fill=GOLD, width=5 * S)
    # redraw top to cover body overlap
    for i in range(n):
        a0 = ang + i * math.tau / n
        a1 = a0 + math.tau / n
        if math.sin((a0 + a1) / 2) < 0:
            continue
    ba = -ang * 2.3
    d.ellipse([P(cx + math.cos(ba) * r * .75 - 10, cy + math.sin(ba) * r * .34 - 10),
               P(cx + math.cos(ba) * r * .75 + 10, cy + math.sin(ba) * r * .34 + 10)], fill=WHITE)


def sc_edge(L, d, t, lt):
    # house box right with lock, coins arcing from figure into it (like reference)
    k = eb(lt / 0.5)
    wire_box(d, 640, FY, 300 * k + 1, 420 * k + 1, depth=90, cols=4, rows=5, fill=(20, 14, 4, 170))
    pill(d, 800, 650, "DAS HAUS", 40, k)
    figure(L, 200, t, scale=0.85)
    kr = eb((t - T["roulette"] + 0.3) / 0.5)
    if kr > 0:
        roulette(L, d, 430, 1080, 150 * kr, t * 2.4)
    pill(d, 430, 955, "HAUSVORTEIL 2,7 %", 42, eb((t - T["roulette"] - 0.3) / 0.4))
    # coins flow faster over time
    if t > T["jedes"]:
        rate = 2.0 if t < T["stunden"] else 6.0
        for i in range(14):
            ph = ((t - T["jedes"]) * rate / 6 + i / 14) % 1
            if (t - T["jedes"]) * rate / 6 + i / 14 < 1 and i > 2:
                continue
            x = 260 + (790 - 260) * ph
            y = 840 - math.sin(ph * math.pi) * 250 + ph * 60
            paste_a(L, COIN, x * S, y * S, 1 - clamp((ph - 0.9) * 10))
    if t > T["stunden"]:
        paste_a(L, GLOW_G, 790 * S, 950 * S, 0.5 + 0.3 * math.sin(t * 6))


def sc_chips(L, d, t, lt):
    figure(L, 230, t, scale=0.85)
    # coin -> chip morph
    kk = eo((t - T["chips"]) / 0.6)
    random.seed(2)
    for s_ in range(4):
        n = 4 + s_ * 2
        for i in range(n):
            x = 470 + s_ * 140
            y = FY - 30 - i * 26 - (1 - eb((lt - 0.2 - s_ * 0.15) / 0.5)) * 600
            if kk < 1 and t < T["chips"] + 0.6 and t < T["chips"]:
                paste_a(L, COIN, x * S, y * S)
            else:
                paste_a(L, CHIPS[s_], x * S, y * S)
    pill(d, 680, 620, "CHIPS ≠ ECHTES GELD", 44, eb((t - T["chips"] - 0.2) / 0.4))
    pill(d, 680, 740, "FÜHLT SICH AN WIE SPIELGELD", 32, eb((t - T["spielgeld"]) / 0.4), col=CORAL)


def sc_maze(L, d, t, lt):
    cell = 92
    ox, oy = CX - MZ_C * cell / 2, 560
    k = eo(lt / 0.6)
    for (c, r), wl in walls.items():
        x0, y0 = ox + c * cell, oy + r * cell
        if wl["N"]:
            d.line([P(x0, y0), P(x0 + cell * k, y0)], fill=GOLD, width=6 * S)
        if wl["W"]:
            d.line([P(x0, y0), P(x0, y0 + cell * k)], fill=GOLD, width=6 * S)
        if wl["S"] and r == MZ_R - 1:
            d.line([P(x0, y0 + cell), P(x0 + cell * k, y0 + cell)], fill=GOLD, width=6 * S)
        if wl["E"] and c == MZ_C - 1 and r != 0:
            d.line([P(x0 + cell, y0), P(x0 + cell, y0 + cell * k)], fill=GOLD, width=6 * S)
    # exit top-right
    ex, ey = ox + MZ_C * cell + 20, oy + cell / 2
    pill(d, ex - 40, oy - 55, "AUSGANG?", 38, eb((t - T["ausgang"]) / 0.4), col=CORAL)
    # wandering player dot
    pos = (lt - 0.4) * 3.2
    if pos > 0:
        i = int(pos) % (len(path_walk) - 1)
        f = pos - int(pos)
        (c0, r0), (c1, r1) = path_walk[i], path_walk[i + 1]
        x = ox + (c0 + (c1 - c0) * f + .5) * cell
        y = oy + (r0 + (r1 - r0) * f + .5) * cell
        trail = [path_walk[max(0, i - j)] for j in range(8)]
        for j, (tc, tr) in enumerate(trail):
            rr = 14 - j * 1.5
            d.ellipse([P(ox + (tc + .5) * cell - rr, oy + (tr + .5) * cell - rr),
                       P(ox + (tc + .5) * cell + rr, oy + (tr + .5) * cell + rr)], fill=(28, 70, 190, 200 - j * 22))
        paste_a(L, GLOW_G.resize((160 * S, 160 * S)), x * S, y * S, 0.6)
        paste_a(L, FIG.resize((FIG.width // 4, FIG.height // 4)), x * S, y * S - 20 * S)


def sc_drinks(L, d, t, lt):
    figure(L, 300, t, scale=0.9, tilt=4 * math.sin(t * 2.5))
    k = eb(lt / 0.5)
    gx, gy = 680, FY
    # cocktail glass outline
    if k > 0:
        s_ = k
        top = gy - 520 * s_
        d.polygon([P(gx - 170 * s_, top), P(gx + 170 * s_, top), P(gx, top + 230 * s_)], outline=GOLD,
                  fill=(255, 92, 80, 150), width=6 * S)
        d.polygon([P(gx - 150 * s_, top + 18 * s_), P(gx + 150 * s_, top + 18 * s_), P(gx, top + 205 * s_)],
                  fill=(255, 92, 80, 200))
        d.line([P(gx, top + 230 * s_), P(gx, gy - 20)], fill=GOLD, width=8 * S)
        d.ellipse([P(gx - 100 * s_, gy - 30), P(gx + 100 * s_, gy + 5)], outline=GOLD, width=6 * S)
        d.ellipse([P(gx + 90 * s_, top - 70 * s_), P(gx + 170 * s_, top + 10 * s_)], fill=(90, 200, 90))
        for i in range(6):  # bubbles
            ph = (t * 0.7 + i / 6) % 1
            bx = gx + math.sin(i * 2.1) * 70 * s_ * (1 - ph)
            by = top + 180 * s_ - ph * 150 * s_
            d.ellipse([P(bx - 7, by - 7), P(bx + 7, by + 7)], outline=(255, 230, 200, 220), width=2 * S)
    pill(d, 680, 520, "GRATIS", 58, eb((t - T["gratis"]) / 0.35))
    pill(d, 680, 640, "DAMIT DU BLEIBST", 34, eb((t - T["gratis"] - 0.7) / 0.35), col=CORAL)


def sc_phone(L, d, t, lt):
    k = eb(lt / 0.5)
    figure(L, 250, t, scale=0.85, tilt=-10 * clamp((t - T["fast"]) / 0.6))
    px, py, pw, ph = 690, 820, 300 * k + 1, 560 * k + 1
    d.rounded_rectangle([P(px - pw / 2, py - ph / 2), P(px + pw / 2, py + ph / 2)], radius=40 * S,
                        outline=GOLD, width=7 * S, fill=(10, 10, 14, 245))
    d.rounded_rectangle([P(px - 40, py - ph / 2 + 18), P(px + 40, py - ph / 2 + 34)], radius=8 * S,
                        fill=(40, 40, 40))
    if k > 0.8:
        show = t > T["vier"] - 0.1
        txt = "04:00" if show else "??:??"
        col = RED if show else GOLD
        if show:
            paste_a(L, GLOW_R, px * S, (py - 60) * S, 0.6)
        ctext(d, P(px, py - 70), txt, 92 * S, col)
        ctext(d, P(px, py + 10), "MONTAG", 30 * S, (200, 200, 200), path=F_B)
        if t > T["fast"]:
            kk = eb((t - T["fast"]) / 0.4)
            d.rounded_rectangle([P(px - 125, py + 80), P(px + 125, py + 200)], radius=18 * S,
                                fill=(40, 12, 12, int(240 * kk)), outline=RED, width=3 * S)
            ctext(d, P(px, py + 115), "KONTOSTAND", 24 * S, (230, 200, 200), path=F_B)
            ctext(d, P(px, py + 160), "23 €", 50 * S, RED)


def sc_punch(L, d, t, lt):
    k = eb(lt / 0.6)
    paste_a(L, GLOW_G, CX * S, 820 * S, 0.5)
    clock(d, CX, 820, 230 * k + 1, -0.6, 0.0, width=9)
    strike(d, CX, 820, 0, 0)
    pill(d, CX, 1105, "NICHT GESTOHLEN", 40, eb((lt - 0.3) / 0.4), col=GOLD)
    if t > T["gezeigt"] - 0.9:
        kk = eb((t - T["gezeigt"] + 0.9) / 0.4)
        # blindfold band over clock
        d.rectangle([P(CX - 300 * kk, 780), P(CX + 300 * kk, 860)], fill=(10, 8, 4, 245), outline=CORAL,
                    width=5 * S)
        ctext(d, P(CX, 820), "NIE GEZEIGT", 54 * S * kk + 1, CORAL)


def sc_cta(L, d, t, lt):
    k = eb(lt / 0.5)
    # slot machine wireframe
    wire_box(d, 330, FY, 420 * k + 1, 560 * k + 1, depth=80, cols=1, rows=1, fill=(25, 16, 4, 220))
    pill(d, 540, 560, "TEIL 2", 54, eb((t - T["teil"]) / 0.35), col=CORAL)
    if k > 0.8:
        for i in range(3):
            rx = 390 + i * 120
            d.rounded_rectangle([P(rx, 760), P(rx + 100, 900)], radius=12 * S, fill=(245, 240, 225),
                                outline=GOLD, width=4 * S)
            spin = t > T["automat"] + 0.3 * i
            sym = "7" if (i < 2 or not spin) else "7"
            if i == 2:
                off = (t * 900) % 140 if t < T["automat"] + 1.3 else 70
                sym = "7"
                ctext(d, P(rx + 50, 760 + off), sym, 90 * S, (200, 30, 40))
                ctext(d, P(rx + 50, 760 + off - 140), "🍒" if False else "$", 80 * S, (30, 120, 60))
            else:
                ctext(d, P(rx + 50, 830), sym, 90 * S, (200, 30, 40))
        # mask reel overflow
        d.rectangle([P(330, 640), P(750, 758)], fill=(25, 16, 4, 255))
        d.rectangle([P(330, 902), P(750, 1020)], fill=(25, 16, 4, 255))
        wire_box(d, 330, FY, 420, 560, depth=80, cols=1, rows=1)
        pill(d, 540, 1000, "FAST GEWONNEN?", 36, eb((t - T["automat"] - 0.5) / 0.4))
        # lever
        d.line([P(780, 900), P(830, 700)], fill=GOLD, width=8 * S)
        d.ellipse([P(810, 670), P(855, 715)], fill=RED)


FN = {"hook": sc_hook, "enter": sc_enter, "light": sc_light, "edge": sc_edge, "chips": sc_chips,
      "maze": sc_maze, "drinks": sc_drinks, "phone": sc_phone, "punch": sc_punch, "cta": sc_cta}


# ------------------------------------------------------------------ HUD + captions (1x)
def budget(t):
    if t < T["500a"]:
        return None
    if t < T["jedes"]:
        return 500.0
    if t < T["fast"]:
        p = (t - T["jedes"]) / (T["fast"] - T["jedes"])
        wob = 25 * math.sin(t * 5.1) * math.sin(t * 1.7) * (1 - p)
        return max(60, 500 - 400 * p ** 0.8 + wob)
    p = clamp((t - T["fast"]) / 0.8)
    return 100 - 77 * eio(p)


def draw_overlay(t):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    b = budget(t)
    if b is not None:
        k = eb((t - T["500a"]) / 0.4)
        low = b < 120
        col = RED if low else GOLD
        spaced(d, W / 2, 250, "DEIN BUDGET", 34, (255, 255, 255, 210), 14)
        txt = f"{int(round(b)):,}".replace(",", ".") + " €"
        ctext(d, (W / 2, 345), txt, int(150 * (0.8 + 0.2 * k)), col)
        # time chip
        if t < T["acht"]:
            tt = None
        elif t < T["drinnen"]:
            tt = "20:00"
        elif t < T["vier"]:
            tt = "??:??" if int(t * 6) % 7 else "  :  "
        else:
            tt = "04:00"
        if tt:
            tc = RED if tt == "04:00" else (255, 255, 255)
            d.rounded_rectangle([W / 2 - 120, 425, W / 2 + 120, 475], radius=25, outline=tc + (180,), width=3,
                                fill=(0, 0, 0, 160))
            ctext(d, (W / 2, 451), "UHRZEIT  " + tt, 28, tc)
    # single-word caption
    for txt, s, e, hi in CAPS:
        if s <= t < e:
            pop = 0.75 + 0.25 * eb((t - s) / 0.14)
            col = GOLD if hi else CORAL
            ctext(d, (W / 2, 1420), txt, int(140 * pop), col, path=F_BL, maxw=W - 140, stroke=2,
                  sfill=tuple(int(c * .5) for c in col))
            break
    return ov


# ------------------------------------------------------------------ frame compositing
def comp_glow(rgb, prem, alpha, strength):
    """rgb: base float HxWx3. prem: premultiplied layer HxWx3 float, alpha HxW float -> composited with glow."""
    out = rgb * (1 - alpha[..., None]) + prem
    small = Image.fromarray(np.clip(prem, 0, 255).astype(np.uint8)).resize((W // 4, H // 4), Image.BILINEAR)
    g1 = np.asarray(small.filter(ImageFilter.GaussianBlur(3)).resize((W, H), Image.BILINEAR)).astype(np.float32)
    g2 = np.asarray(small.filter(ImageFilter.GaussianBlur(12)).resize((W, H), Image.BILINEAR)).astype(np.float32)
    return out + (g1 * 0.55 + g2 * 0.6) * strength


def render(fi):
    t = fi / FPS
    layer = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    for name, s, e in BOUNDS:
        if s - 0.001 <= t < e + 0.22:
            lt = t - s
            sub = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
            FN[name](sub, ImageDraw.Draw(sub), t, lt)
            a = clamp(lt / 0.22) if name != "hook" else 1.0
            if t > e:
                a *= clamp((e + 0.22 - t) / 0.22)
            if a < 0.99:
                sub.putalpha(sub.getchannel("A").point(lambda v: int(v * a)))
            layer.alpha_composite(sub)
    sc = np.asarray(layer.reduce(S)).astype(np.float32)
    alpha = sc[..., 3] / 255
    prem = sc[..., :3] * alpha[..., None]
    # floor reflection of everything above the floor line
    Lr = H - FY
    rp = prem[FY - Lr:FY][::-1] * np.linspace(0.42, 0, Lr)[:, None, None]
    ra = alpha[FY - Lr:FY][::-1] * np.linspace(0.42, 0, Lr)[:, None]
    prem[FY:] = prem[FY:] + rp * (1 - alpha[FY:, :, None])
    alpha[FY:] = np.clip(alpha[FY:] + ra * (1 - alpha[FY:]), 0, 1)
    out = comp_glow(BG, prem, alpha, 0.9)
    ov = np.asarray(draw_overlay(t)).astype(np.float32)
    oa = ov[..., 3] / 255
    out = comp_glow(out, ov[..., :3] * oa[..., None], oa, 1.0)
    # progress bar
    out[0:8, :int(W * t / DUR)] = GOLD
    return np.clip(out, 0, 255).astype(np.uint8).tobytes()


def main():
    only = [int(x) for x in sys.argv[1:]]
    if only:
        for fi in only:
            Image.frombytes("RGB", (W, H), render(fi)).save(os.path.join(HERE, f"preview_{fi}.png"))
        return
    out = os.path.join(HERE, "casino-uhren.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", os.path.join(HERE, "voice.mp3"), "-i", os.path.join(HERE, "music.wav"),
           "-filter_complex",
           f"[1:a]atempo={SPEED}[v];[2:a]volume=0.18[m];[v][m]amix=inputs=2:duration=longest:normalize=0,"
           f"loudnorm=I=-14:TP=-1.5:LRA=11[a]",
           "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt",
           "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-t", f"{DUR:.2f}", "-movflags", "+faststart",
           out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(os.cpu_count()) as pool:
        for i, buf in enumerate(pool.imap(render, range(NFRAMES), chunksize=4)):
            proc.stdin.write(buf)
            if i % 300 == 0:
                print(f"frame {i}/{NFRAMES}", flush=True)
    proc.stdin.close()
    proc.wait()
    print("done", out, f"{DUR:.1f}s")


if __name__ == "__main__":
    main()
