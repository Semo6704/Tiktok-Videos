"""Erzeugt die Erzählerstimme (Thorsten-VITS, Coqui TTS) Satz für Satz + timing.json.

Aufruf:  python synth.py <modellordner> [length_scale]
Der Modellordner enthält model_file.pth + config.json von
https://github.com/coqui-ai/TTS/releases/download/v0.7.0_models/tts_models--de--thorsten--vits.zip
"""
import json
import os
import re
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# (Szene, gesprochener Text, Untertitel)
SCRIPT = [
    ("hook", "Du zahlst für hundert Megabit, aber beim Spiedtest kommen nur sechzig an?",
     "Du zahlst für 100 Mbit – aber beim Speedtest kommen nur 60 an?"),
    ("hook", "Ich zeig dir, warum.", "Ich zeig dir, warum."),
    ("weg", "Dein Internet startet in riesigen Rechenzentren.",
     "Dein Internet startet in riesigen Rechenzentren."),
    ("weg", "Über Unterseekabel und Glasfasernetze rast es bis zum grauen Verteilerkasten an deiner Straße.",
     "Über Unterseekabel und Glasfasernetze rast es bis zum grauen Verteilerkasten an deiner Straße."),
    ("weg", "Von dort geht es oft noch über alte Kupferleitungen bis in deine Wohnung.",
     "Von dort geht es oft noch über alte Kupferleitungen bis in deine Wohnung."),
    ("glas", "Glasfaser funktioniert mit Licht.", "Glasfaser funktioniert mit Licht."),
    ("glas", "Ein Laser blinkt Milliarden Mal pro Sekunde.", "Ein Laser blinkt Milliarden Mal pro Sekunde."),
    ("glas", "Licht an heißt eins, Licht aus heißt null.", "Licht an = 1, Licht aus = 0."),
    ("glas", "In der hauchdünnen Faser wird das Licht immer wieder an der Wand gespiegelt.",
     "In der hauchdünnen Faser wird das Licht immer wieder an der Wand gespiegelt."),
    ("glas", "So kommt es fast ohne Verlust über viele Kilometer an.",
     "So kommt es fast ohne Verlust über viele Kilometer an."),
    ("kupfer", "Bei Kupfer, also bei De Es El, wird das Signal mit jedem Meter schwächer.",
     "Bei Kupfer, also bei DSL, wird das Signal mit jedem Meter schwächer."),
    ("kupfer", "Je weiter du vom Verteiler weg wohnst, desto langsamer wird es.",
     "Je weiter du vom Verteiler weg wohnst, desto langsamer wird es."),
    ("gruende", "Und warum kommt weniger an als versprochen?", "Und warum kommt weniger an als versprochen?"),
    ("g1", "Erstens: Im Vertrag steht meistens nur bis zu.", "1. Im Vertrag steht meistens nur „bis zu“."),
    ("g2", "Zweitens: Abends surfen alle Nachbarn gleichzeitig und teilen sich die Leitung.",
     "2. Abends surfen alle Nachbarn gleichzeitig und teilen sich die Leitung."),
    ("g3", "Drittens: Wehlan durch dicke Wände kostet richtig viel Tempo.",
     "3. WLAN durch dicke Wände kostet richtig viel Tempo."),
    ("g4", "Und viertens: Ein Teil der Bandbreite geht für Steuerdaten drauf.",
     "4. Ein Teil der Bandbreite geht für Steuerdaten drauf."),
    ("tipp", "Mein Tipp: Mach den Test immer mit Kabel.", "Mein Tipp: Mach den Test immer mit Kabel."),
    ("tipp", "Und kommt dauerhaft viel zu wenig an, darfst du sogar weniger bezahlen.",
     "Und kommt dauerhaft viel zu wenig an, darfst du sogar weniger bezahlen."),
    ("outro", "Folg mir für mehr!", "Folg mir für mehr!"),
]

# gruut rät viele Wörter falsch -> Lautschrift-Korrekturen (falsch -> richtig)
WORD_FIX = {
    "ʔeːs": "ʔɛs", "ʔalteː": "ʔaltə", "ʔʊntɛʁzəʔeːkabəl": "ʔʊntɐzeːkaːbəl",
    "glasfazɐ": "ɡlaːsfaːzɐ", "glasfazɛʁnɛtsə": "ɡlaːsfaːzɐnɛtsə",
    "fɛːɐtaeːlɛʁkastən": "fɛɐtaɪlɐkastən", "fɛːɐtəiːlɐ": "fɛɐtaɪlɐ",
    "kʊp͡fɛʁləiːtʊŋən": "kʊpfɐlaɪtʊŋən", "ləiːtʊŋ": "laɪtʊŋ", "vənɪgɐ": "veːnɪɡɐ",
    "vəiːtɐ": "vaɪtɐ", "tsaeːk": "tsaɪk", "ʁiːəsɪgən": "ʁiːzɪɡən",
    "ʁɛçɛntsɛntʁən": "ʁɛçəntsɛntʁən", "mɪlliːaʁdən": "mɪliaʁdən", "haoːxdʏnnən": "haʊxdʏnən",
    "faːst": "fast", "fɛːɐlʊst": "fɛɐlʊst", "fɛːɐʃpʁɔxən": "fɛɐʃpʁɔxən", "fɛɐtʁaːk": "fɛɐtʁaːk",
    "ʔɛːɐʃtɛns": "ʔeːɐstəns", "tsvaeːtɛns": "tsvaɪtəns", "dʁɪtɛns": "dʁɪtəns",
    "viːʁtɛns": "fiːɐtəns", "ʔapʔɛnts": "ʔaːbənts", "maeːstɛns": "maɪstəns",
    "glaeːçtsəiːtɪç": "ɡlaɪçtsaɪtɪç", "veːlan": "veːlaːn", "bandbʁəiːtə": "bantbʁaɪtə",
    "ʃtɔɔʏ̯ɐdatən": "ʃtɔʏɐdaːtən", "dʁaoːf": "dʁaʊf", "daʔuːɐhaft": "daʊɐhaft",
    "daʁfʃt": "daʁfst", "tɪpp": "tɪp", "ʃpiːtɛst": "spiːtɛst", "meːgabiːt": "meːɡabɪt",
    "nʊll": "nʊl", "aeːn": "aɪn", "aeːns": "aɪns", "haeːzst": "haɪst", "taeːl": "taɪl",
    "gʁaoːən": "ɡʁaʊən", "gəʃpiːgɛlt": "ɡəʃpiːɡəlt", "ʃtʁaszə": "ʃtʁaːsə",
    "kiːloːmeːtɐ": "kiloˈmeːtɐ".replace("ˈ", ""), "ʔalzoː": "ʔalzoː", "zeːkʊndə": "zeˈkʊndə".replace("ˈ", ""),
    "fʊŋktsɪoːniːʁt": "fʊŋktsi̯oniːɐt".replace("̯", ""), "laːzɐ": "leːzɐ", "maːl": "maːl",
    "deːʔɛsʔɛl": "deːʔɛsʔɛl", "ʔɛs": "ʔɛs",
}
WORD_FIX.update({"ʔeːl": "ʔɛl", "ʔaːbeːʁ": "ʔaːbɐ", "zoːgaʁ": "zoɡaːɐ"})
WORD_FIX_N = {k.replace("g", "ɡ"): v for k, v in WORD_FIX.items()}
GENERIC = [("aeː", "aɪ"), ("əiː", "aɪ"), ("aoː", "aʊ"), ("ɔɔʏ", "ɔʏ"), ("̯", ""), ("͡", ""), ("g", "ɡ")]


def fix_phonemes(ph):
    out = []
    for tok in ph.split(" "):
        m = re.match(r"^(.*?)([!'(),\-.:;?]*)$", tok)
        core, punct = m.group(1), m.group(2)
        core = core.replace("g", "ɡ")
        core = WORD_FIX_N.get(core, core)
        for a, b in GENERIC:
            core = core.replace(a, b)
        out.append(core + punct)
    return " ".join(out)


def main():
    from TTS.api import TTS
    mdir = sys.argv[1]
    ls = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    tts = TTS(model_path=os.path.join(mdir, "model_file.pth"),
              config_path=os.path.join(mdir, "config.json"))
    model = tts.synthesizer.tts_model
    model.length_scale = ls
    model.inference_noise_scale = 0.6
    model.inference_noise_scale_dp = 0.7
    phz = model.tokenizer.phonemizer
    orig = phz.phonemize

    def patched(text, separator="|", language=None):
        return fix_phonemes(orig(text, separator=separator, language=language))
    phz.phonemize = patched

    sr = tts.synthesizer.output_sample_rate
    clips = []
    for i, (scene, spoken, sub) in enumerate(SCRIPT):
        wav = np.array(tts.tts(spoken), dtype=np.float32)
        # Stille an den Rändern trimmen
        thr = 0.01 * np.max(np.abs(wav))
        idx = np.where(np.abs(wav) > thr)[0]
        wav = wav[max(0, idx[0] - int(0.02 * sr)): idx[-1] + int(0.05 * sr)]
        clips.append(wav)
        print(i, f"{len(wav) / sr:.2f}s", fix_phonemes(orig(spoken, separator="", language=None)))
    np.save(os.path.join(HERE, "_clips.npy"), np.array(clips, dtype=object), allow_pickle=True)
    json.dump({"sr": sr, "lens": [len(c) / sr for c in clips]},
              open(os.path.join(HERE, "_clips.json"), "w"))


if __name__ == "__main__":
    main()
