"""Erzählerstimme über ElevenLabs (Satz für Satz, mit Wort-Zeitstempeln).

Aufruf:  python synth_elevenlabs.py <voice_id> [speed]
Der API-Key wird als Header xi-api-key gesendet: aus $ELEVENLABS_API_KEY oder
(in der Cloud-Umgebung) vom Netzwerk-Proxy eingesetzt.
Erzeugt _clips.npy / _clips.json für render.py.
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synth import SCRIPT  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 44100
MODEL = os.environ.get("ELEVEN_MODEL", "eleven_multilingual_v2")

# Normale Schreibweise statt der Lautschrift-Tricks für das lokale Modell
REPL = [("Spiedtest", "Speedtest"), ("De Es El", "DSL"), ("Wehlan", "WLAN"),
        ("nur bis zu.", "nur „bis zu“.")]


def spoken(i):
    s = SCRIPT[i][1]
    for a, b in REPL:
        s = s.replace(a, b)
    return s


def tts(voice, text, prev, nxt, speed):
    body = {
        "text": text, "model_id": MODEL, "language_code": "de",
        "previous_text": prev, "next_text": nxt,
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25,
                           "use_speaker_boost": True, "speed": speed},
    }
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps"
        "?output_format=mp3_44100_128",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "xi-api-key": os.environ.get("ELEVENLABS_API_KEY", "proxy-injected")})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            raise SystemExit(f"ElevenLabs-Fehler {e.code}: {msg}")


def decode_mp3(b):
    p = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "-", "-f", "f32le", "-ac", "1",
                        "-ar", str(SR), "-"], input=b, capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.float32)


def word_starts(al):
    chars, starts = al["characters"], al["character_start_times_seconds"]
    words, cur, st = [], "", None
    for c, s in zip(chars, starts):
        if c.isspace():
            if cur:
                words.append((cur, st))
            cur, st = "", None
        else:
            if not cur:
                st = s
            cur += c
    if cur:
        words.append((cur, st))
    return words


def main():
    voice = sys.argv[1]
    speed = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    clips, words_all = [], []
    n = len(SCRIPT)
    for i in range(n):
        txt = spoken(i)
        prev = " ".join(spoken(j) for j in range(max(0, i - 2), i))
        nxt = spoken(i + 1) if i + 1 < n else ""
        res = tts(voice, txt, prev, nxt, speed)
        wav = decode_mp3(base64.b64decode(res["audio_base64"]))
        words = word_starts(res["alignment"])
        # Stille am Anfang/Ende kürzen, Wortzeiten mitschieben
        thr = 0.02 * np.max(np.abs(wav))
        idx = np.where(np.abs(wav) > thr)[0]
        a = max(0, idx[0] - int(0.03 * SR))
        b = min(len(wav), idx[-1] + int(0.08 * SR))
        wav = wav[a:b]
        words = [(w, max(0.0, s - a / SR)) for w, s in words]
        clips.append(wav)
        words_all.append(words)
        print(i, f"{len(wav) / SR:.2f}s", txt, flush=True)
    np.save(os.path.join(HERE, "_clips.npy"), np.array(clips, dtype=object), allow_pickle=True)
    json.dump({"sr": SR, "lens": [len(c) / SR for c in clips], "words": words_all},
              open(os.path.join(HERE, "_clips.json"), "w"), ensure_ascii=False)
    print("gesamt", sum(len(c) for c in clips) / SR)


if __name__ == "__main__":
    main()
