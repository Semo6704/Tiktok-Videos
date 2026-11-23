"""Render the 'Warum sind Flugzeugfenster rund?' TikTok explainer (1080x1920, 30 fps).

Inputs (same folder): voice.mp3, words.json (word timings from ElevenLabs alignment).
Output: flugzeugfenster.mp4
"""
import json, math, os, random, subprocess, sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1920
S = 2                      # supersampling factor for crisp shapes
SW, SH = W * S, H * S
FPS = 30
SPEED = 1.08               # voice is sped up by this factor

FONT_XB = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"
FONT_B = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"

YELLOW = (255, 210, 63)
RED = (255, 75, 75)
BLUE = (63, 169, 255)
WHITE = (255, 255, 255)
GREY = (150, 160, 180)

# ---------------------------------------------------------------- timing
words = [(w, s / SPEED, e / SPEED) for w, s, e in json.load(open(os.path.join(HERE, "words.json")))]
DUR = words[-1][2] + 1.6
NFRAMES = int(DUR * FPS)


def t_of(word, nth=1):
    n = 0
    for w, s, e in words:
        if w.strip(".,?:!").lower() == word.lower():
            n += 1
            if n == nth:
                return s
    raise KeyError(word)


SCENES = [  # (name, start)
    ("hook", 0.0),
    ("comet", t_of("Neunzehnhundertzweiundfünfzig")),
    ("crash", t_of("Doch")),
    ("fatigue", t_of("Die", 3)),
    ("corners", t_of("An")),
    ("round", t_of("Runde")),
    ("hole", t_of("Seitdem")),
    ("cta", t_of("Folg")),
]
SCENE_BOUNDS = [(n, s, SCENES[i + 1][1] if i + 1 < len(SCENES) else DUR) for i, (n, s) in enumerate(SCENES)]

DISPLAY = {"neunzehnhundertzweiundfünfzig.": "1952", "neunzehnhundertzweiundfünfzig": "1952",
           "neunzehnhundertvierundfünfzig": "1954"}

# caption chunks
chunks, cur = [], []
for i, (w, s, e) in enumerate(words):
    cur.append(i)
    txt = " ".join(DISPLAY.get(words[j][0].lower(), words[j][0]) for j in cur)
    if w[-1] in ".,?:!" or len(cur) >= 3 or len(txt) > 16:
        chunks.append(cur)
        cur = []
if cur:
    chunks.append(cur)


# ---------------------------------------------------------------- helpers
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_back(x):
    x = clamp(x)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def ease_io(x):
    x = clamp(x)
    return 3 * x * x - 2 * x ** 3


_fonts = {}


def font(size, path=FONT_XB):
    size = max(int(size), 1)
    key = (size, path)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(path, size)
    return _fonts[key]


def text_center(d, xy, txt, size, fill, path=FONT_XB, stroke=0, stroke_fill=(0, 0, 0), maxw=None):
    f = font(size, path)
    if maxw:
        while d.textlength(txt, font=f) > maxw and size > 20:
            size -= 4
            f = font(size, path)
    d.text(xy, txt, font=f, fill=fill, anchor="mm", stroke_width=stroke, stroke_fill=stroke_fill)


def radial_sprite(r, color):
    """Soft radial glow, RGBA, radius r."""
    yy, xx = np.mgrid[-r:r, -r:r]
    dist = np.sqrt(xx ** 2 + yy ** 2) / r
    a = np.clip(1 - dist, 0, 1) ** 2
    img = np.zeros((2 * r, 2 * r, 4), np.uint8)
    img[..., 0], img[..., 1], img[..., 2] = color
    img[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(img, "RGBA")


def paste_alpha(base, sprite, xy, alpha):
    if alpha <= 0.01:
        return
    sp = sprite
    if alpha < 0.99:
        sp = sprite.copy()
        sp.putalpha(sp.getchannel("A").point(lambda v: int(v * alpha)))
    base.alpha_composite(sp, (int(xy[0] - sp.width / 2), int(xy[1] - sp.height / 2)))


# ---------------------------------------------------------------- static assets
def make_bg():
    y = np.linspace(0, 1, SH)[:, None]
    top = np.array([12, 18, 38])
    bot = np.array([4, 6, 16])
    grad = top * (1 - y) + bot * y
    img = np.repeat(grad[:, None, :], SW, axis=1).reshape(SH, SW, 3)
    # vignette
    yy, xx = np.mgrid[0:SH, 0:SW]
    d = np.sqrt(((xx - SW / 2) / SW) ** 2 + ((yy - SH / 2) / SH) ** 2)
    img *= np.clip(1.15 - d * 0.9, 0.4, 1)[..., None]
    bg = Image.fromarray(img.astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(bg)
    for x in range(0, SW, 120 * S // 2):
        d.line([(x, 0), (x, SH)], fill=(255, 255, 255, 10), width=S)
    for yv in range(0, SH, 120 * S // 2):
        d.line([(0, yv), (SW, yv)], fill=(255, 255, 255, 10), width=S)
    return bg


def sky(w, h):
    y = np.linspace(0, 1, h)[:, None]
    top = np.array([40, 110, 220])
    bot = np.array([170, 215, 255])
    g = top * (1 - y) + bot * y
    arr = np.repeat(g[:, None, :], w, axis=1).astype(np.uint8)
    im = Image.fromarray(arr, "RGB").convert("RGBA")
    d = ImageDraw.Draw(im)
    random.seed(3)
    for _ in range(5):  # clouds
        cx, cy = random.randint(0, w), random.randint(int(h * .5), h)
        for k in range(4):
            r = random.randint(w // 10, w // 6)
            d.ellipse([cx + k * r // 2 - r, cy - r // 2, cx + k * r // 2 + r, cy + r // 2], fill=(255, 255, 255, 200))
    return im


def make_window(w, h, radius, frame_col=(215, 220, 230)):
    """Airplane window sprite at supersampled resolution."""
    pad = int(w * 0.16)
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w + 2 * pad - 1, h + 2 * pad - 1], radius=radius + pad if radius else 6 * S,
                        fill=frame_col)
    d.rounded_rectangle([pad // 3, pad // 3, w + 2 * pad - pad // 3, h + 2 * pad - pad // 3],
                        radius=radius + pad * 2 // 3 if radius else 4 * S, fill=(185, 190, 200))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius if radius else 2 * S, fill=255)
    sk = sky(w, h)
    im.paste(sk, (pad, pad), mask)
    # glass reflection
    gl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gl)
    gd.polygon([(w * .1, h), (w * .45, 0), (w * .62, 0), (w * .27, h)], fill=(255, 255, 255, 45))
    refl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    refl.paste(gl, (0, 0), mask)
    im.alpha_composite(refl, (pad, pad))
    return im


def make_plane(length, color=(235, 240, 250)):
    """Side-view airliner silhouette facing right."""
    L = length
    h = int(L * 0.42)
    im = Image.new("RGBA", (L, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fy0, fy1 = h * 0.42, h * 0.62            # fuselage band
    # tail fin
    d.polygon([(L * .02, fy0 + 4), (L * .06, h * .02), (L * .14, h * .02), (L * .22, fy0 + 4)], fill=color)
    # fuselage
    d.rounded_rectangle([L * .03, fy0, L * .97, fy1], radius=int((fy1 - fy0) / 2), fill=color)
    d.polygon([(L * .03, fy0), (L * .12, fy0), (L * .12, fy1 - (fy1 - fy0) * .3), (L * .02, fy0 + (fy1 - fy0) * .2)],
              fill=color)
    # wing (going down/back)
    d.polygon([(L * .40, fy1 - 6), (L * .58, fy1 - 6), (L * .38, h * .98), (L * .30, h * .98)], fill=(200, 208, 225))
    # cockpit window
    d.polygon([(L * .9, fy0 + (fy1 - fy0) * .22), (L * .95, fy0 + (fy1 - fy0) * .3), (L * .93, fy0 + (fy1 - fy0) * .45),
               (L * .89, fy0 + (fy1 - fy0) * .45)], fill=(30, 40, 70))
    # cabin windows (squarish, Comet-style)
    ws = (fy1 - fy0) * 0.28
    for i in range(14):
        x = L * .2 + i * L * .045
        d.rectangle([x, fy0 + (fy1 - fy0) * .3, x + ws, fy0 + (fy1 - fy0) * .3 + ws], fill=(30, 40, 70))
    # engine
    d.rounded_rectangle([L * .40, fy1 - 2, L * .52, fy1 + (fy1 - fy0) * .35], radius=12, fill=(170, 178, 195))
    return im


BG = make_bg()
WIN_SQ = make_window(300 * S, 300 * S, 0)
WIN_RD = make_window(300 * S, 380 * S, 150 * S)
WIN_BIG = make_window(420 * S, 560 * S, 210 * S)
PLANE = make_plane(860 * S)
GLOW_RED = radial_sprite(150 * S, RED)
GLOW_BLUE = radial_sprite(330 * S, BLUE)
GLOW_YEL = radial_sprite(260 * S, YELLOW)


def crack_paths():
    random.seed(7)
    paths = []
    for sx, sy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
        for b in range(2):
            pts = [(0.0, 0.0)]
            ang = math.atan2(sy, sx) + random.uniform(-.5, .5)
            for _ in range(9):
                ang += random.uniform(-.45, .45)
                step = random.uniform(14, 26) * S
                x, y = pts[-1]
                pts.append((x + math.cos(ang) * step, y + math.sin(ang) * step))
            paths.append(((sx, sy), pts))
    return paths


CRACKS = crack_paths()


# ---------------------------------------------------------------- scene drawing (on 2x RGBA layer)
CX = SW // 2
GY = 760 * S  # graphic center y


def title(d, txt, y, size, fill=WHITE, p=1.0):
    if p <= 0:
        return
    size = int(size * S * (0.85 + 0.15 * ease_back(p)))
    text_center(d, (CX, y * S), txt, size, fill, stroke=4 * S, stroke_fill=(0, 0, 0), maxw=(W - 120) * S)


def scene_hook(layer, d, t, lt):
    p = ease_back(lt / 0.5)
    title(d, "WARUM", 270, 92, WHITE, lt / 0.4)
    title(d, "SIND SIE RUND?", 375, 92, YELLOW, (lt - 0.15) / 0.4)
    # square (crossed) vs round
    off = int(230 * S * p)
    bob = math.sin(t * 3) * 10 * S
    sq = WIN_SQ.resize((int(WIN_SQ.width * .8), int(WIN_SQ.height * .8)))
    layer.alpha_composite(sq, (CX - off - sq.width // 2, int(GY + bob) - sq.height // 2))
    rd = WIN_RD.resize((int(WIN_RD.width * .8), int(WIN_RD.height * .8)))
    layer.alpha_composite(rd, (CX + off - rd.width // 2, int(GY - bob) - rd.height // 2))
    # question mark pulsing
    q = 1 + 0.08 * math.sin(t * 6)
    text_center(d, (CX, GY + 330 * S), "?", int(160 * S * q * p), YELLOW, stroke=5 * S)
    if lt > 2.6:  # red X over square window
        k = ease_out((lt - 2.6) / 0.3)
        x0, y0 = CX - off, GY
        r = 150 * S * k
        d.line([(x0 - r, y0 - r), (x0 + r, y0 + r)], fill=RED, width=22 * S)
        d.line([(x0 - r, y0 + r), (x0 + r, y0 - r)], fill=RED, width=22 * S)


def scene_comet(layer, d, t, lt):
    title(d, "1952", 260, 150, YELLOW, lt / 0.4)
    title(d, "DE HAVILLAND COMET", 380, 62, WHITE, (lt - .2) / 0.4)
    # plane flies in and then cruises
    x = -PLANE.width + (CX + PLANE.width / 2) * ease_out(lt / 1.6) - PLANE.width / 2 + PLANE.width
    x = int(x - PLANE.width / 2)
    y = int(GY - PLANE.height / 2 + math.sin(t * 2) * 12 * S)
    # speed lines
    for i in range(7):
        ly = GY - 140 * S + i * 45 * S
        lx = (SW - ((t * 1400 * S + i * 377 * S) % (SW + 600 * S)))
        d.line([(lx, ly), (lx + 220 * S, ly)], fill=(255, 255, 255, 60), width=4 * S)
    layer.alpha_composite(PLANE, (x, y))
    # fact badges
    facts = ["1. JET-PASSAGIERFLUGZEUG", "SCHNELLER  ·  HÖHER"]
    for i, f in enumerate(facts):
        k = ease_back((lt - 2.6 - i * 2.2) / 0.4)
        if k <= 0:
            continue
        by = (1060 + i * 120) * S
        bw = (len(f) * 30 + 80) * S * k
        d.rounded_rectangle([CX - bw / 2, by - 45 * S, CX + bw / 2, by + 45 * S], radius=45 * S,
                            fill=(255, 210, 63, 235) if i == 0 else (63, 169, 255, 235))
        if k > 0.6:
            text_center(d, (CX, by), f, 44 * S, (10, 14, 30), maxw=bw - 40 * S)


def scene_crash(layer, d, t, lt):
    title(d, "1954", 260, 150, RED, lt / 0.4)
    title(d, "2 ABSTÜRZE IN 3 MONATEN", 380, 62, WHITE, (lt - .3) / 0.4)
    split = clamp((lt - 2.0) / 1.6)
    s = ease_out(split)
    shake = (random.Random(int(t * 30)).uniform(-1, 1) * 14 * S) if 1.6 < lt < 3.6 else 0
    x0 = CX - PLANE.width // 2
    y0 = GY - PLANE.height // 2
    cut = int(PLANE.width * 0.5)
    back = PLANE.crop((0, 0, cut, PLANE.height))
    front = PLANE.crop((cut, 0, PLANE.width, PLANE.height))
    if s > 0:
        back = back.rotate(-14 * s, resample=Image.BICUBIC, expand=False)
        front = front.rotate(20 * s, resample=Image.BICUBIC, expand=False)
    layer.alpha_composite(back, (int(x0 - 90 * S * s + shake), int(y0 + 160 * S * s * s)))
    layer.alpha_composite(front, (int(x0 + cut + 90 * S * s + shake), int(y0 + 230 * S * s * s)))
    if 1.9 < lt < 3.2:  # explosion flash
        k = 1 - abs(lt - 2.3) / 0.9
        paste_alpha(layer, GLOW_YEL, (CX, GY), clamp(k))
        paste_alpha(layer, GLOW_RED.resize((500 * S, 500 * S)), (CX, GY), clamp(k))
    if lt > 3.6:  # debris
        rng = random.Random(5)
        for i in range(18):
            ang = rng.uniform(0, math.tau)
            sp = rng.uniform(80, 300) * S
            tt = lt - 2.0
            px = CX + math.cos(ang) * sp * min(tt, 3) / 3
            py = GY + math.sin(ang) * sp * min(tt, 3) / 3 + 60 * S * tt
            r = rng.uniform(5, 14) * S
            d.rectangle([px - r, py - r, px + r, py + r], fill=(200, 208, 225))


def scene_fatigue(layer, d, t, lt):
    title(d, "METALL-", 250, 112, YELLOW, lt / 0.4)
    title(d, "ERMÜDUNG", 370, 112, YELLOW, (lt - .1) / 0.4)
    # fuselage cross-section breathing
    k = ease_back((lt - 0.2) / 0.5)
    breathe = (math.sin((lt - 2.5) * 2.4) * 0.5 + 0.5) if lt > 2.5 else 0
    r = (230 + 45 * breathe) * S * k
    if r > 0:
        d.ellipse([CX - r, GY - r, CX + r, GY + r], fill=(30, 40, 70), outline=(215, 220, 230), width=int(22 * S))
        # floor
        fy = GY + r * 0.35
        half = math.sqrt(max(r * r - (r * .35) ** 2, 0)) - 22 * S
        d.line([(CX - half, fy), (CX + half, fy)], fill=(215, 220, 230), width=10 * S)
        # arrows outward
        if lt > 2.5:
            for i in range(8):
                a = i * math.tau / 8 + 0.2
                r0 = r * 0.45
                r1 = r * (0.75 + 0.1 * breathe)
                p0 = (CX + math.cos(a) * r0, GY + math.sin(a) * r0)
                p1 = (CX + math.cos(a) * r1, GY + math.sin(a) * r1)
                d.line([p0, p1], fill=BLUE, width=10 * S)
                hx, hy = math.cos(a), math.sin(a)
                ah = 26 * S
                d.polygon([(p1[0] + hx * ah, p1[1] + hy * ah),
                           (p1[0] - hy * ah * .7, p1[1] + hx * ah * .7),
                           (p1[0] + hy * ah * .7, p1[1] - hx * ah * .7)], fill=BLUE)
            text_center(d, (CX, GY - 40 * S), "DRUCK", 58 * S, WHITE, stroke=3 * S)
    # flight counter
    if lt > 5.5:
        n = int((lt - 5.5) * 3.5) + 1
        text_center(d, (CX, GY + 390 * S), f"FLUG #{n}", 64 * S, YELLOW, stroke=3 * S)


def scene_corners(layer, d, t, lt):
    title(d, "ECKEN =", 250, 112, WHITE, lt / 0.4)
    title(d, "SCHWACHSTELLE", 370, 100, RED, (lt - .1) / 0.4)
    k = ease_back(lt / 0.5)
    win = WIN_SQ.resize((int(WIN_SQ.width * 1.35 * k) + 1, int(WIN_SQ.height * 1.35 * k) + 1))
    shake = 0
    crack_p = clamp((lt - 3.6) / 3.0)
    if crack_p > 0.85:
        shake = random.Random(int(t * 30)).uniform(-1, 1) * 8 * S
    layer.alpha_composite(win, (CX - win.width // 2 + int(shake), GY - win.height // 2))
    hw = 300 * S * 1.35 * k / 2
    corners = [(CX - hw, GY - hw), (CX + hw, GY - hw), (CX + hw, GY + hw), (CX - hw, GY + hw)]
    if lt > 1.0:
        pulse = 0.6 + 0.4 * math.sin(t * 7)
        a = clamp((lt - 1.0) / 1.0) * pulse
        for c in corners:
            paste_alpha(layer, GLOW_RED, c, a)
    # stress flow lines bending around corners
    if lt > 1.5:
        for i, ((sx, sy), pts) in enumerate(CRACKS):
            c = corners[[(-1, -1), (1, -1), (1, 1), (-1, 1)].index((sx, sy))]
            n = int(len(pts) * crack_p)
            if n >= 2:
                d.line([(c[0] + x, c[1] + y) for x, y in pts[:n]], fill=(255, 255, 255), width=5 * S, joint="curve")
    if lt > 2.0:
        text_center(d, (CX, GY + 390 * S), "SPANNUNG STAUT SICH", 54 * S, RED, stroke=3 * S)


def scene_round(layer, d, t, lt):
    title(d, "RUND =", 250, 112, WHITE, lt / 0.4)
    title(d, "KEIN RISS", 370, 112, (90, 230, 140), (lt - .1) / 0.4)
    k = ease_back(lt / 0.5)
    paste_alpha(layer, GLOW_BLUE, (CX, GY), 0.55 + 0.2 * math.sin(t * 3))
    win = WIN_RD.resize((int(WIN_RD.width * 1.2 * k) + 1, int(WIN_RD.height * 1.2 * k) + 1))
    layer.alpha_composite(win, (CX - win.width // 2, GY - win.height // 2))
    # flow lines around the oval
    if lt > 0.8:
        rot = t * 1.5
        rx, ry = 290 * S * k, 340 * S * k
        for i in range(24):
            a = rot + i * math.tau / 24
            p0 = (CX + math.cos(a) * rx, GY + math.sin(a) * ry)
            p1 = (CX + math.cos(a + .12) * rx, GY + math.sin(a + .12) * ry)
            d.line([p0, p1], fill=BLUE, width=8 * S)
    if lt > 2.6:
        ck = ease_back((lt - 2.6) / 0.4)
        cx, cy, r = CX + 230 * S, GY + 260 * S, 70 * S * ck
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(90, 230, 140))
        if ck > 0.5:
            d.line([(cx - r * .45, cy), (cx - r * .1, cy + r * .35), (cx + r * .5, cy - r * .35)],
                   fill=(10, 30, 20), width=int(14 * S), joint="curve")
    text_center(d, (CX, GY + 420 * S), "KRAFT VERTEILT SICH", 54 * S, BLUE, stroke=3 * S)


def scene_hole(layer, d, t, lt):
    title(d, "UND DAS LOCH?", 270, 100, YELLOW, lt / 0.4)
    k = ease_back(lt / 0.5)
    win = WIN_BIG.resize((int(WIN_BIG.width * k) + 1, int(WIN_BIG.height * k) + 1))
    layer.alpha_composite(win, (CX - win.width // 2, GY - win.height // 2 + 40 * S))
    hx, hy = CX, GY + 40 * S + 200 * S * k
    zoom_in = clamp((lt - 3.6) / 0.5)
    hr = 7 * S
    d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=(20, 25, 40))
    if zoom_in > 0:
        # callout circle
        z = ease_back(zoom_in)
        zx, zy, zr = CX + 260 * S, GY - 220 * S, 140 * S * z
        d.line([(hx, hy), (zx, zy)], fill=YELLOW, width=6 * S)
        d.ellipse([zx - zr, zy - zr, zx + zr, zy + zr], fill=(150, 200, 255), outline=YELLOW, width=10 * S)
        d.ellipse([zx - zr * .28, zy - zr * .28, zx + zr * .28, zy + zr * .28], fill=(20, 25, 40))
        if z > 0.6:
            text_center(d, (CX, GY + 470 * S), "DRUCKAUSGLEICH", 60 * S, YELLOW, stroke=3 * S)
        # little pulse
        pr = zr * (0.3 + (t * 1.2 % 1) * 0.7)
        d.ellipse([zx - pr, zy - pr, zx + pr, zy + pr], outline=(255, 255, 255, int(200 * (1 - t * 1.2 % 1))),
                  width=4 * S)


def scene_cta(layer, d, t, lt):
    title(d, "FOLG FÜR MEHR", 330, 100, WHITE, lt / 0.4)
    title(d, "ALLTAGS-RÄTSEL", 440, 90, YELLOW, (lt - .15) / 0.4)
    k = ease_back((lt - 0.3) / 0.5)
    r = 150 * S * k * (1 + 0.05 * math.sin(t * 8))
    paste_alpha(layer, GLOW_YEL, (CX, GY + 60 * S), 0.7)
    d.ellipse([CX - r, GY + 60 * S - r, CX + r, GY + 60 * S + r], fill=RED)
    if k > 0.3:
        a = r * .45
        d.line([(CX - a, GY + 60 * S), (CX + a, GY + 60 * S)], fill=WHITE, width=int(26 * S))
        d.line([(CX, GY + 60 * S - a), (CX, GY + 60 * S + a)], fill=WHITE, width=int(26 * S))


SCENE_FN = {"hook": scene_hook, "comet": scene_comet, "crash": scene_crash, "fatigue": scene_fatigue,
            "corners": scene_corners, "round": scene_round, "hole": scene_hole, "cta": scene_cta}


# ---------------------------------------------------------------- captions (1x, on final frame)
def draw_captions(img, t):
    d = ImageDraw.Draw(img)
    ci = None
    for i, ch in enumerate(chunks):
        st = words[ch[0]][1]
        en = words[chunks[i + 1][0]][1] if i + 1 < len(chunks) else words[ch[-1]][2] + 0.8
        if st <= t < en:
            ci = i
            break
    if ci is None:
        return
    ch = chunks[ci]
    st = words[ch[0]][1]
    pop = 0.8 + 0.2 * ease_back((t - st) / 0.15)
    toks = [DISPLAY.get(words[j][0].lower(), words[j][0]).upper() for j in ch]
    size = int(86 * pop)
    f = font(size)
    space = d.textlength(" ", font=f)
    total = sum(d.textlength(x, font=f) for x in toks) + space * (len(toks) - 1)
    while total > W - 110 and size > 30:
        size -= 4
        f = font(size)
        space = d.textlength(" ", font=f)
        total = sum(d.textlength(x, font=f) for x in toks) + space * (len(toks) - 1)
    x = (W - total) / 2
    y = 1330
    for j, tok in zip(ch, toks):
        active = words[j][1] <= t
        cur = active and (j == ch[-1] or words[j + 1][1] > t)
        col = YELLOW if cur else (WHITE if active else (200, 205, 215))
        d.text((x, y), tok, font=f, fill=col, anchor="lm", stroke_width=8, stroke_fill=(0, 0, 0))
        x += d.textlength(tok, font=f) + space


# ---------------------------------------------------------------- frame
def render(fi):
    t = fi / FPS
    frame = BG.copy()
    for name, s, e in SCENE_BOUNDS:
        # keep scene visible slightly beyond its end for crossfade
        if s - 0.001 <= t < e + 0.25:
            lt = t - s
            alpha = clamp(lt / 0.25) * clamp((e + 0.25 - t) / 0.25) if t > e else clamp(lt / 0.25)
            if name == "hook" and t < 0.25:
                alpha = 1
            layer = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            # slide-up on enter
            SCENE_FN[name](layer, d, t, lt)
            if alpha < 0.99:
                layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
            frame.alpha_composite(layer)
    img = frame.convert("RGB").reduce(S)
    d = ImageDraw.Draw(img)
    # progress bar
    d.rectangle([0, 0, int(W * t / DUR), 10], fill=YELLOW)
    draw_captions(img, t)
    return img.tobytes()


def main():
    out = os.path.join(HERE, "flugzeugfenster.mp4")
    music = os.path.join(HERE, "music.wav")
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", os.path.join(HERE, "voice.mp3"), "-i", music,
           "-filter_complex",
           f"[1:a]atempo={SPEED},volume=1.0[v];[2:a]volume=0.22[m];[v][m]amix=inputs=2:duration=first:dropout_transition=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
           "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-t", f"{DUR:.2f}", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    only = [int(x) for x in sys.argv[1:]]
    if only:  # preview stills
        for fi in only:
            Image.frombytes("RGB", (W, H), render(fi)).save(os.path.join(HERE, f"preview_{fi}.png"))
        proc.stdin.close(); proc.kill()
        return
    with Pool(os.cpu_count()) as pool:
        for i, buf in enumerate(pool.imap(render, range(NFRAMES), chunksize=4)):
            proc.stdin.write(buf)
            if i % 150 == 0:
                print(f"frame {i}/{NFRAMES}", flush=True)
    proc.stdin.close()
    proc.wait()
    print("done", out)


if __name__ == "__main__":
    main()
