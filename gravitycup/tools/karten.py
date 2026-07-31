#!/usr/bin/env python3
"""
karten.py – Vorspann und Trailer: Bilder, die kein Rennen zeigen.

Beides war seit dem 30.07.2026 als Baustein vorgemerkt und hing an
derselben Voraussetzung: `build.video_schreiben` muss eine beliebige
Bildquelle annehmen. Seit sie herausgelöst ist, sind Vorspann und Trailer
nur noch gezeichnete Bilder, die durch dieselbe Kodierung laufen wie ein
Rennen – gleiche Farbkennzeichnung, gleiche Tonbehandlung, keine zweite
Kodierung.

Der **Vorspann** erklärt in wenigen Sekunden, was gleich passiert. Ohne ihn
sieht ein Zuschauer 64 Kugeln in einem Kasten und weiß nicht, worauf er
achten soll – und die Regel („wer als Letzter durch die Tür kommt, ist
raus") ist der Grund, warum man überhaupt hinschaut.

Der **Trailer** ist das Video, das Nicht-Abonnenten auf der Kanalseite
sehen. Er wirbt nicht mit dem Ergebnis, sondern mit dem Versprechen: der
Ausgang wird simuliert, nicht geschrieben, und jeder kann es nachrechnen.
"""
from __future__ import annotations

import math

from ..core import draw, theme

#: Wie lange die einzelnen Tafeln des Vorspanns stehen, in Sekunden.
VORSPANN_TAFELN = (2.6, 3.4, 2.6)

#: Ein- und Ausblendung je Tafel, in Sekunden.
BLENDE = 0.45


def vorspann_bilder(fps: int = theme.FPS) -> int:
    """Wie viele Bilder der Vorspann belegt."""
    return int(round(sum(VORSPANN_TAFELN) * fps))


def _blende(t: float, dauer: float) -> int:
    """Deckkraft 0..255 über eine Tafel hinweg."""
    if t < BLENDE:
        anteil = t / BLENDE
    elif t > dauer - BLENDE:
        anteil = max(0.0, (dauer - t) / BLENDE)
    else:
        anteil = 1.0
    # Weich an beiden Enden, nicht linear – sonst zuckt der Wechsel.
    return int(255 * (anteil * anteil * (3.0 - 2.0 * anteil)))


def _tafel(nummer: int) -> tuple[str, list[str]]:
    """Überschrift und Zeilen einer Vorspanntafel."""
    return {
        0: ("GRAVITY CUP", ["THE SHOW"]),
        1: ("{n} ENTER", ["ONE LEAVES",
                          "",
                          "every stage: the last one out is eliminated"]),
        2: ("NO SCRIPT", ["the outcome is simulated, not written",
                          "seed {seed} · verify it yourself"]),
    }[nummer]


def vorspann(f: int, teilnehmer: int, seed: int, scale: int,
             fps: int = theme.FPS):
    """Bild `f` des Vorspanns.

    Bewusst nur Text auf dem Hausraster – kein Standbild aus dem Rennen.
    Ein eingefrorenes Rennbild verrät die Startaufstellung, und die ist
    das Erste, was der Zuschauer selbst sehen soll.
    """
    c = draw.Canvas(scale=scale)
    c.grid()
    c.scrim(alpha=theme.SCRIM_ALPHA)

    t = f / fps
    for nummer, dauer in enumerate(VORSPANN_TAFELN):
        if t < dauer:
            break
        t -= dauer
    else:
        nummer, dauer = len(VORSPANN_TAFELN) - 1, VORSPANN_TAFELN[-1]
        t = dauer

    alpha = _blende(t, dauer)
    if alpha <= 0:
        return c.finish()

    titel, zeilen = _tafel(nummer)
    titel = titel.format(n=teilnehmer, seed=seed)
    mitte = theme.HEIGHT * 0.42

    c.text_centered(mitte, titel, "result_name", fill=theme.TEXT,
                    alpha=alpha)
    y = mitte + 96
    for zeile in zeilen:
        if zeile:
            c.text_centered(y, zeile.format(n=teilnehmer, seed=seed),
                            "result_label", fill=theme.TEXT_MUTED,
                            alpha=alpha)
        y += 62

    # Ein Band aus Teilnehmerkennungen unter dem Text – es zeigt sofort,
    # dass es viele sind und dass sie unterscheidbar sind.
    if nummer == 1:
        comps = theme.competitors()
        wieviele = min(len(comps), 16)
        breite = theme.WIDTH - 2 * theme.SAFE_LEFT - 120
        schritt = breite / max(1, wieviele - 1)
        y_band = theme.HEIGHT * 0.74
        for i in range(wieviele):
            x = theme.SAFE_LEFT + 60 + i * schritt
            # Die ersten sechzehn sind die vollen Farben und damit die am
            # weitesten auseinanderliegenden. Ein Griff ueber das ganze Feld
            # (`i * len // wieviele`) landet dagegen im Musterraster und
            # zeigt viermal dieselbe Farbe.
            c.marble(comps[i % len(comps)], x, y_band,
                     angle=0.6 + i * 0.4, alpha=alpha, radius=26)
    return c.finish()


# ---------------------------------------------------------------------------
# Trailer
# ---------------------------------------------------------------------------

TRAILER_TAFELN = (
    ("GRAVITY CUP", ["physics, not a script"], 3.0),
    ("EVERY OUTCOME", ["is computed, never chosen"], 3.0),
    ("EVERY EPISODE", ["carries its seed", "anyone can recompute it"], 3.4),
    ("VERIFY IT", ["github.com/valon-91/gravity-cup-archiv"], 3.2),
)


def trailer_bilder(fps: int = theme.FPS) -> int:
    return int(round(sum(t[2] for t in TRAILER_TAFELN) * fps))


def trailer(f: int, scale: int, fps: int = theme.FPS):
    """Bild `f` des Kanaltrailers.

    Wirbt mit dem VERSPRECHEN, nicht mit einem Ergebnis. Ein Trailer, der
    einen Sieger zeigt, verfällt mit der Folge; das Versprechen nicht –
    genau deshalb steht er als Kanaltrailer und nicht als Video im Feed
    (siehe `docs/b9-langform-und-trailer.md`).
    """
    c = draw.Canvas(scale=scale)
    c.grid()
    c.scrim(alpha=theme.SCRIM_ALPHA)

    t = f / fps
    for titel, zeilen, dauer in TRAILER_TAFELN:
        if t < dauer:
            break
        t -= dauer
    else:
        titel, zeilen, dauer = TRAILER_TAFELN[-1]
        t = dauer

    alpha = _blende(t, dauer)
    if alpha <= 0:
        return c.finish()

    mitte = theme.HEIGHT * 0.40
    c.text_centered(mitte, titel, "result_name", fill=theme.TEXT, alpha=alpha)
    y = mitte + 100
    for zeile in zeilen:
        c.text_centered(y, zeile, "result_label", fill=theme.TEXT_MUTED,
                        alpha=alpha)
        y += 62

    # Kugelband, das sich mit der Zeit dreht – Bewegung, ohne ein Rennen
    # zu zeigen.
    comps = theme.competitors()
    wieviele = min(len(comps), 12)
    y_band = theme.HEIGHT * 0.72
    breite = theme.WIDTH - 2 * theme.SAFE_LEFT - 160
    schritt = breite / max(1, wieviele - 1)
    for i in range(wieviele):
        x = theme.SAFE_LEFT + 80 + i * schritt
        hebung = math.sin(f / fps * 2.2 + i * 0.8) * 16
        c.marble(comps[i % len(comps)], x, y_band + hebung,
                 angle=f / fps * 2.0 + i, alpha=alpha, radius=28)
    return c.finish()
