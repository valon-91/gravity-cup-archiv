#!/usr/bin/env python3
"""
audio.py – Tonspur aus dem Kollisionsprotokoll.

Kein Sample-Material, keine Fremdmusik: jeder Klang wird aus den Daten der
Simulation gerechnet.

  Lautstaerke   = Aufprallimpuls
  Tonhoehe      = Teilnehmer (pentatonisch, damit gleichzeitige Treffer
                  nie dissonant klingen)
  Klangfarbe    = Trefferart (Wand dumpf / Stift hell / Kugel-Kugel klar)
  Stereo        = X-Position des KONTAKTPUNKTS im Bild

Dazu ein leiser Klangteppich, ein Riser vor dem Zieleinlauf und ein Akkord
auf den Sieger.

Die Lautheit wird HIER gemessen und eingestellt, nicht spaeter im
ffmpeg-Aufruf – siehe „Lautheit" unten.

CLI-Test:
  python -m gravitycup.core.audio --seed 7 --out race.wav
"""
from __future__ import annotations

import argparse
import math
import sys
import wave

import numpy as np

from . import physics, theme

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SR = 48000                 # 48 kHz ist der Standard fuer Video
#: Pentatonisch – gleichzeitige Treffer klingen dadurch nie schief.
SCALE = [523.25, 587.33, 698.46, 783.99, 932.33]     # C D F G Bb

#: Ziel-Lautheit. YouTube normalisiert auf etwa -14 LUFS; wer lauter
#: abliefert, wird heruntergeregelt und klingt danach flach.
TARGET_LUFS = -14.0
TARGET_TRUE_PEAK = -1.5

TAIL_SECONDS = 2.0


# ---------------------------------------------------------------------------
# Bausteine des Klangs
# ---------------------------------------------------------------------------


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    a = max(1, int(attack * SR))
    e = np.exp(-np.linspace(0, decay, n))
    if a < n:
        e[:a] *= np.linspace(0, 1, a)
    return e


def click(freq: float, dur: float, amp: float, kind: str,
          rng: np.random.Generator) -> np.ndarray:
    """Ein Aufprall: Rauschtransiente plus gestimmter Nachklang."""
    n = int(dur * SR)
    t = np.arange(n) / SR

    if kind == "wall":
        freq *= 0.5
        decay, noise_amt, tone_amt = 26.0, 0.55, 0.45
    elif kind == "peg":
        # Faktor 2 statt 1.5: eine Oktave bleibt in der Skala, eine Quinte
        # daneben nicht. Der Prototyp verliess hier die Pentatonik.
        freq *= 2.0
        decay, noise_amt, tone_amt = 34.0, 0.30, 0.70
    else:
        freq *= 4.0
        decay, noise_amt, tone_amt = 30.0, 0.18, 0.82

    tone = (np.sin(2 * np.pi * freq * t)
            + 0.45 * np.sin(2 * np.pi * freq * 2.01 * t)
            + 0.18 * np.sin(2 * np.pi * freq * 3.03 * t))
    tone *= _env(n, 0.0004, decay)

    nz = rng.standard_normal(n)
    for _ in range(2):                      # einfacher Tiefpass gegen Zischen
        nz = np.convolve(nz, np.ones(3) / 3, mode="same")
    nz *= _env(n, 0.0002, 120.0)

    return (tone_amt * tone + noise_amt * nz) * amp


def pad(n: int) -> np.ndarray:
    """Leiser Klangteppich, der zum Ziel hin leicht ansteigt."""
    t = np.arange(n) / SR
    base = 65.41                                        # C2
    sig = np.zeros(n)
    for k, det in [(1, 0.0), (1, 0.6), (2, -0.4), (3, 0.3)]:
        sig += np.sin(2 * np.pi * (base * k + det) * t) / (k * 1.8)
    sig *= 0.82 + 0.18 * np.sin(2 * np.pi * 0.09 * t)
    sig *= np.linspace(0.55, 1.0, n)
    return sig * 0.07


def riser(n_total: int, start: int, dur: float = 2.4) -> np.ndarray:
    """Spannungsaufbau vor dem Zieleinlauf."""
    out = np.zeros(n_total)
    start = max(0, start)
    n = min(int(dur * SR), n_total - start)
    if n <= 0:
        return out
    f = np.linspace(180, 900, n)
    ph = 2 * np.pi * np.cumsum(f) / SR
    out[start:start + n] += np.sin(ph) * np.linspace(0.0, 0.16, n) ** 2
    return out


def sting(n_total: int, at: int, root: float = 392.0) -> np.ndarray:
    """Kurzer Akkord auf den Sieger."""
    out = np.zeros(n_total)
    at = max(0, at)
    dur = min(int(2.6 * SR), n_total - at)
    if dur <= 0:
        return out
    t = np.arange(dur) / SR
    sig = np.zeros(dur)
    for r in (1.0, 1.25, 1.5, 2.0):
        sig += np.sin(2 * np.pi * root * r * t) / 4
    sig *= np.exp(-np.linspace(0, 5.5, dur))
    out[at:at + dur] += sig * 0.30
    return out


# ---------------------------------------------------------------------------
# Lautheit
#
# Der Prototyp uebergab ffmpeg fest eingetragene measured_*-Werte aus EINEM
# Messlauf. Fuer jedes weitere Rennen sind die falsch – die Normalisierung
# rechnet dann mit den Zahlen eines fremden Videos. Bei einer Serie mit
# hunderten Folgen schwankt die Lautstaerke dadurch hoerbar.
#
# Darum wird hier gemessen, was tatsaechlich erzeugt wurde, und danach
# geregelt. Die Messung folgt ITU-R BS.1770 (K-Bewertung, Gating).
# ---------------------------------------------------------------------------


def _k_filter(x: np.ndarray) -> np.ndarray:
    """K-Bewertung nach BS.1770 (Hochtonanhebung + Hochpass)."""
    # Stufe 1: Kopfbuegel-Filter
    f0, G, Q = 1681.97, 3.99984, 0.7071752
    K = math.tan(math.pi * f0 / SR)
    Vh = 10 ** (G / 20)
    Vb = Vh ** 0.499666774
    a0_ = 1 + K / Q + K * K
    b = [(Vh + Vb * K / Q + K * K) / a0_,
         2 * (K * K - Vh) / a0_,
         (Vh - Vb * K / Q + K * K) / a0_]
    a = [1.0, 2 * (K * K - 1) / a0_, (1 - K / Q + K * K) / a0_]
    y = _biquad(x, b, a)

    # Stufe 2: Hochpass
    f0, Q = 38.13547087, 0.5003270
    K = math.tan(math.pi * f0 / SR)
    a0_ = 1 + K / Q + K * K
    b = [1.0, -2.0, 1.0]
    a = [1.0, 2 * (K * K - 1) / a0_, (1 - K / Q + K * K) / a0_]
    return _biquad(y, b, a)


try:
    from scipy.signal import lfilter as _lfilter
except ImportError:                                   # scipy ist nicht Pflicht
    _lfilter = None


def _biquad(x: np.ndarray, b: list[float], a: list[float]) -> np.ndarray:
    """Ein Biquad-Filter. Rekursiv, laesst sich nicht vektorisieren.

    Mit scipy laeuft das in C und dauert Millisekunden; die reine
    Python-Schleife darunter braucht fuer eine 30-Sekunden-Spur rund
    17 Sekunden. Sie bleibt als Rueckfall stehen, damit das Modul auch
    ohne scipy funktioniert.
    """
    if _lfilter is not None:
        return _lfilter(b, a, x)

    y = np.zeros_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, xi in enumerate(x):
        yi = b[0] * xi + b[1] * x1 + b[2] * x2 - a[1] * y1 - a[2] * y2
        y[i] = yi
        x2, x1 = x1, xi
        y2, y1 = y1, yi
    return y


def measure_lufs(stereo: np.ndarray) -> float:
    """Integrierte Lautheit in LUFS (BS.1770-4, mit Gating)."""
    kanaele = [_k_filter(stereo[:, c].astype(np.float64))
               for c in range(stereo.shape[1])]
    block = int(0.400 * SR)
    schritt = int(0.100 * SR)
    if len(kanaele[0]) < block:
        return -70.0

    lautheiten = []
    for start in range(0, len(kanaele[0]) - block + 1, schritt):
        summe = sum(np.mean(k[start:start + block] ** 2) for k in kanaele)
        if summe > 0:
            lautheiten.append(-0.691 + 10 * math.log10(summe))
    if not lautheiten:
        return -70.0

    werte = np.array(lautheiten)
    # absolutes Gate
    werte = werte[werte > -70.0]
    if len(werte) == 0:
        return -70.0
    # relatives Gate
    schwelle = 10 * math.log10(np.mean(10 ** (werte / 10))) - 10.0
    behalten = werte[werte > schwelle]
    if len(behalten) == 0:
        behalten = werte
    return float(10 * math.log10(np.mean(10 ** (behalten / 10))) - 0.691)


#: Ueberabtastung fuer die True-Peak-Messung. BS.1770-4 verlangt mindestens
#: das Vierfache bei 48 kHz.
TRUE_PEAK_OVERSAMPLE = 4

#: Soll der True Peak auf TARGET_TRUE_PEAK nachgezogen werden?
#:
#: AUS, und das ist eine offene Entscheidung, keine Nachlaessigkeit: das
#: Nachziehen kostet rund 2 LU Lautheit (siehe `normalize`). Umschalten
#: aendert den Klang JEDER kuenftigen Folge – vorher lesen, was in
#: `docs/naechste-schritte.md` unter „Ton" dazu steht.
TRUE_PEAK_NACHZIEHEN = False


def true_peak(stereo: np.ndarray, faktor: int = TRUE_PEAK_OVERSAMPLE) -> float:
    """Groesster Wert ZWISCHEN den Abtastpunkten, linear.

    Der Unterschied zu `np.abs(x).max()` ist nicht theoretisch. Zwischen zwei
    Abtastwerten kann die rekonstruierte Welle deutlich hoeher ausschlagen als
    an den Punkten selbst – am staerksten bei kurzen, harten Transienten. Also
    genau bei dem, woraus diese Tonspur besteht: Klicks.

    Gemessen am 29.07.2026 an den ersten neun Folgen: Sample-Peak brav unter
    der Grenze, True Peak bis **+3,6 dBFS**. Acht von neun Folgen uebersteuern.
    """
    from scipy.signal import resample_poly
    hoch = resample_poly(stereo.astype(np.float64), faktor, 1, axis=0)
    return float(np.abs(hoch).max())


def normalize(stereo: np.ndarray) -> tuple[np.ndarray, dict]:
    """Auf die Ziel-Lautheit bringen und den Spitzenwert begrenzen."""
    vorher = measure_lufs(stereo)
    verstaerkung = 10 ** ((TARGET_LUFS - vorher) / 20)
    aus = stereo * verstaerkung

    grenze = 10 ** (TARGET_TRUE_PEAK / 20)
    spitze = float(np.abs(aus).max())
    begrenzt = False
    if spitze > grenze:
        # weicher Limiter statt hartem Abschneiden
        aus = np.tanh(aus / grenze * 1.1) * grenze
        begrenzt = True

    # Der weiche Limiter drueckt den SAMPLE-Peak unter die Grenze, den True
    # Peak nicht – tanh verschaerft die Flanken sogar. Gemessen an den ersten
    # neun Folgen: True Peak bis +3,6 dBFS, acht von neun uebersteuern.
    #
    # Das Nachziehen ist bewusst ABGESCHALTET. Es waere eine reine Skalierung
    # und wuerde den True Peak exakt auf die Grenze bringen – aber es nimmt
    # dabei rund 2 LU Lautheit mit, von -14 auf etwa -16 LUFS. YouTube regelt
    # lautes Material herunter und leises NICHT herauf; die Folge klaenge
    # danach leiser als alles neben ihr.
    #
    # Beides ist ein Fehler, und die Wahl zwischen ihnen ist keine, die ein
    # Programm treffen sollte. Der richtige Weg ist ein echter Limiter mit
    # Vorausschau, der nur die Transienten greift statt das ganze Signal –
    # das aendert den Klangcharakter und gehoert besprochen.
    # Bis dahin: gemessen und sichtbar, aber unveraendert.
    tp = true_peak(aus)
    tp_begrenzt = False
    if TRUE_PEAK_NACHZIEHEN and tp > grenze:
        aus = aus * (grenze / tp)
        tp_begrenzt = True

    return aus, {
        "lufs_vorher": round(vorher, 2),
        "lufs_nachher": round(measure_lufs(aus), 2),
        "verstaerkung_db": round(TARGET_LUFS - vorher, 2),
        "spitze_dbfs": round(20 * math.log10(max(1e-9, float(np.abs(aus).max()))), 2),
        "true_peak_dbfs": round(20 * math.log10(max(1e-9, true_peak(aus))), 2),
        "begrenzt": begrenzt,
        "true_peak_begrenzt": tp_begrenzt,
    }


# ---------------------------------------------------------------------------
# Zusammenbau
# ---------------------------------------------------------------------------


def build(result: physics.RunResult) -> tuple[np.ndarray, dict]:
    """Tonspur zu einem Lauf. Der Seed kommt aus dem Lauf – es gibt nur einen."""
    rng = np.random.default_rng(result.seed)
    n = int((len(result.frames) / result.fps + TAIL_SECONDS) * SR)
    links = np.zeros(n)
    rechts = np.zeros(n)

    if result.hits:
        max_imp = max(h.impulse for h in result.hits)
        for h in result.hits:
            pos = int(h.frame / result.fps * SR)
            amp = min(1.0, (h.impulse / max_imp) ** 0.55)
            if amp < 0.05:
                continue
            c = click(SCALE[h.competitor % len(SCALE)], 0.45, amp, h.kind, rng)
            ende = min(n, pos + len(c))
            if ende <= pos:
                continue
            c = c[:ende - pos]
            # Stereo aus der X-Position des Kontaktpunkts
            pan = float(np.clip(h.x / theme.WIDTH, 0.0, 1.0))
            links[pos:ende] += c * math.sqrt(1 - pan)
            rechts[pos:ende] += c * math.sqrt(pan)

    teppich = pad(n)
    links += teppich
    rechts += teppich

    if result.finish_frame is not None:
        ziel = int(result.finish_frame / result.fps * SR)
        r = riser(n, ziel - int(2.4 * SR))
        s = sting(n, ziel)
        links += r + s
        rechts += r + s

    stereo = np.stack([links, rechts], axis=1)
    stereo, messung = normalize(stereo)
    return stereo, messung


def write_wav(path, stereo: np.ndarray) -> None:
    daten = np.clip(stereo, -1.0, 1.0)
    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((daten * 32767).astype("<i2").tobytes())


def main() -> int:
    ap = argparse.ArgumentParser(description="Einzeltest Baustein B3")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--state", help="Lauf aus JSON laden statt neu rechnen")
    ap.add_argument("--out", default="race.wav")
    a = ap.parse_args()

    if a.state:
        r = physics.load(a.state)
    else:
        from ..disciplines import descent
        r = descent.run(a.seed)

    import time
    t0 = time.perf_counter()
    stereo, messung = build(r)
    dauer = time.perf_counter() - t0

    write_wav(a.out, stereo)

    print(f"{len(r.hits)} Aufpraelle -> {a.out}")
    print(f"Laenge      {len(stereo) / SR:.1f}s bei {SR} Hz stereo")
    print(f"Lautheit    {messung['lufs_vorher']:+.2f} LUFS gemessen "
          f"-> {messung['lufs_nachher']:+.2f} LUFS "
          f"(Ziel {TARGET_LUFS:+.1f}, Korrektur {messung['verstaerkung_db']:+.2f} dB)")
    print(f"Spitze      {messung['spitze_dbfs']:+.2f} dBFS Sample"
          f"{', begrenzt' if messung['begrenzt'] else ''}")
    print(f"True Peak   {messung['true_peak_dbfs']:+.2f} dBFS "
          f"(Grenze {TARGET_TRUE_PEAK:+.1f}"
          f"{', nachgezogen' if messung['true_peak_begrenzt'] else ''})")
    print(f"gerechnet in {dauer:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
