#!/usr/bin/env python3
"""
konzepte.py – Prüfstand für das BILD der Langform, nicht für ihre Mechanik.

Anlass (03.08.2026): SHOW-01 ist mechanisch heil und trotzdem „langweilig
des Todes" (Valon, 31.07.). Kein Kriterium des Projekts kann Langeweile
sehen – deshalb wird hier andersherum gearbeitet als bisher: erst mehrere
grundverschiedene BILDER bauen und ansehen, dann die Mechanik des
Gewinners härten. Vorbild ist der Katalog von Square League (188k Abos,
03.08.2026): deren Topformate unterscheiden sich pro Folge im Spielfeld,
nicht im Parameter.

Vier Konzepte, jedes eine bildschirmgrosse Kammer im Vollbild, 100
Teilnehmer, feste Kamera (nichts zu verfolgen – die Kammer IST das Bild):

  pulk       Massenausscheidung: das Feld sammelt sich vor einer Sperre,
             dann geht das Tor auf und alle wollen gleichzeitig durch.
  formen     Valons Vorschlag vom 30.07.: grosse geometrische Formen statt
             Stifte, Einstieg oben links, Ausgang unten rechts – das Feld
             muss die Kammer DURCHQUEREN.
  labyrinth  Versetzte Simse zwingen das Feld in Serpentinen; es fliesst
             als Strom, nicht als Regen.
  kessel     Eine grosse Schüssel: das Feld rollt von beiden Seiten
             hinein, kreist und staut sich an der Sperre in der Mitte.

Dies ist ein WEGWERF-Prüfstand: er schreibt bewusst KEIN Manifest nach
runs/ (die Lehre aus SHOW-01.json, das drei Tage lang die Saisonauswertung
stilllegte) und fasst keine Disziplin an – die Kurzfolgen bleiben
unberührt. Neben jede MP4 kommt eine .txt mit Seed und Messwerten.

Erster echter Verbraucher von `physics.mindest_luecke(feld)`: jede lichte
Weite, durch die das Feld muss, ist daran bemessen – nicht an der einzelnen
Kugel. Die fünffach bezahlte Lehre des Projekts, hier zum ersten Mal als
Bauregel statt als Test.

  python -m gravitycup.tools.konzepte --alle --vorschau
  python -m gravitycup.tools.konzepte --konzept formen --seed 5
  python -m gravitycup.tools.konzepte --alle --nur-lauf   # ohne Video
"""
from __future__ import annotations

import argparse
import math
import random
import sys
import time
from pathlib import Path

from .. import build
from ..core import audio, physics, theme

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TEILNEHMER = 100
MARBLE_D = 2 * theme.MARBLE_RADIUS

#: Wanddicke wie in der Arena (dort gemessen: 9 px werden von einem
#: 100er-Stapel durchdrueckt, Endpositionen bei y = 87 Mio.).
SEG_RADIUS = 22.0
SOLVER_ITERATIONEN = 40

#: Jede Oeffnung, durch die das FELD muss, ist hieran bemessen.
LUECKE = physics.mindest_luecke(TEILNEHMER)

#: Ausgaenge in Kugeldurchmessern. Nicht unter 5,0 – darunter beginnt der
#: Verklemmungsbereich der Schuettgutmechanik (gemessen am 31.07.2026:
#: bei 4,0 stand seed 7 dreieinhalb Minuten, bei 5,0 keiner von sechs).
AUSGANG_KUGELN = 6.0

NL_ = chr(10)


# ---------------------------------------------------------------------------
# Regel: eine Zeitsperre vor der Ziellinie
# ---------------------------------------------------------------------------


class TorZeiten(physics.RaceToLine):
    """Wertung wie das Sturzrennen, aber jede Sperre oeffnet zu ihrer
    Zeit. `simulate` schreibt die Oeffnungen selbst nach
    `extras["tore_auf"]`, das Bild zeichnet sie darueber weg."""

    name = "torzeiten"

    def __init__(self, finish_y: float, zeiten: dict[int, float]):
        super().__init__(finish_y)
        self.zeiten = zeiten
        self._zeit = 0.0

    def schritt(self, zeit_von, dt, y_vorher, y_jetzt, x_jetzt=None):
        self._zeit = zeit_von + dt
        return super().schritt(zeit_von, dt, y_vorher, y_jetzt, x_jetzt)

    def offene_tore(self) -> set[int]:
        return {k for k, t0 in self.zeiten.items() if self._zeit >= t0}


def TorZeit(finish_y: float, sperrzeit: float) -> TorZeiten:
    """Bequemlichkeitsform fuer genau eine Sperre."""
    return TorZeiten(finish_y, {0: sperrzeit})


# ---------------------------------------------------------------------------
# Gemeinsame Bauteile
# ---------------------------------------------------------------------------


def startreihen(anzahl: int, x_von: float, x_bis: float,
                y_unterste: float) -> list[tuple[float, float]]:
    """Startplaetze in Reihen ueber der Kammer, unterste Reihe zuerst."""
    abstand = MARBLE_D + 10
    je_reihe = max(1, int((x_bis - x_von) // abstand))
    plaetze: list[tuple[float, float]] = []
    reihe = 0
    while len(plaetze) < anzahl:
        y = y_unterste - reihe * (MARBLE_D + 8)
        rest = min(je_reihe, anzahl - len(plaetze))
        # mittig in der verfuegbaren Breite
        breite = (rest - 1) * abstand
        x0 = (x_von + x_bis) / 2 - breite / 2
        for i in range(rest):
            plaetze.append((x0 + i * abstand, y))
        reihe += 1
    return plaetze


def wanne(segments: list[physics.Segment], mitte: float, unten: float,
          links: float, rechts: float, ausgang: float,
          hoehe: float = 240.0) -> tuple[float, float]:
    """Trichterboden auf einen mittigen Ausgang zu. Liefert die Torkanten."""
    tor_l = mitte - ausgang / 2
    tor_r = mitte + ausgang / 2
    segments.append(physics.Segment(links, unten - hoehe, tor_l, unten,
                                    SEG_RADIUS))
    segments.append(physics.Segment(rechts, unten - hoehe, tor_r, unten,
                                    SEG_RADIUS))
    return tor_l, tor_r


def sperre(tor_l: float, tor_r: float, y: float) -> list[physics.Segment]:
    """Die Sperre unter dem Ausgang, wie in der Arena: unter dem
    Trichtermund, damit der Pulk DAVOR liegt und nicht darin klemmt."""
    return [physics.Segment(tor_l - SEG_RADIUS, y, tor_r + SEG_RADIUS, y,
                            SEG_RADIUS)]


def auslauf(segments: list[physics.Segment], finish_y: float) -> None:
    """Becken unter der Ziellinie. Zweierlei ist hier gemessen:

    Ohne Becken fallen Angekommene ins Nichts und zaehlen als 'verloren'
    (erster Trockenlauf, kessel: 67 angekommen, 67 verloren). Und ein
    Becken 170 px unter der Linie ist zu flach: 100 Kugeln schuetten
    einen Kegel von rund 400 px Hoehe, der ueber die Ziellinie
    ZURUECKWAECHST – 33 Kugeln 'kamen nie an', weil sie auf dem Haufen
    ihrer Vorgaenger standen (zweiter Trockenlauf). Der Boden liegt
    deshalb 700 px tief und reicht bis an beide Raender, damit auch ein
    einseitiger Haufen an der Wand unter der Linie bleibt."""
    # Die Waende beginnen deutlich UEBER der Linie: im dritten Trockenlauf
    # verliess ein Teil des Feldes das Eck-Ausgangs-Konzept mit Querschwung
    # und flog zwischen Kammerwand-Ende und Beckenwand-Beginn hindurch –
    # acht Kugeln bei x = 2000, Endpositionen bei y = 670 000.
    segments.append(physics.Segment(60, finish_y + 700, 1860,
                                    finish_y + 700, SEG_RADIUS))
    segments.append(physics.Segment(60, finish_y - 470, 60,
                                    finish_y + 710, SEG_RADIUS))
    segments.append(physics.Segment(1860, finish_y - 470, 1860,
                                    finish_y + 710, SEG_RADIUS))


# ---------------------------------------------------------------------------
# Die vier Konzepte. Jede Funktion liefert (Track, Regel, Kameraoberkante).
# ---------------------------------------------------------------------------


def k_pulk(seed: int):
    """Massenausscheidung: EIN grosses Tor, das ganze Feld davor.

    Das Bild ist der Moment, in dem die Sperre aufgeht: 100 Kugeln, die
    sich zwoelf Sekunden lang uebereinander geschoben haben, wollen
    gleichzeitig durch acht Kugelbreiten. In der Show waere das EINE
    Kammer von wenigen – nicht 99 gleiche.
    """
    rng = random.Random(seed * 7919 + 11)
    mitte = 960.0
    links, rechts, unten = 110.0, 1810.0, 880.0
    segments: list[physics.Segment] = []
    pegs: list[physics.Peg] = []

    segments.append(physics.Segment(links, -420, links, unten - 200,
                                    SEG_RADIUS))
    segments.append(physics.Segment(rechts, -420, rechts, unten - 200,
                                    SEG_RADIUS))
    # Grosszuegiges Tor: 8 Kugeln – der Stau soll vom FELD kommen,
    # nicht von einem Nadeloehr im Verklemmungsbereich.
    tor_l, tor_r = wanne(segments, mitte, unten, links, rechts,
                         8.0 * MARBLE_D)
    tore = [sperre(tor_l, tor_r, unten + 30)]

    # Eine Handvoll GROSSER Rührsteine im Fallweg, jeder einzeln geprueft.
    for _ in range(200):
        if len(pegs) >= 5:
            break
        px = rng.uniform(links + 240, rechts - 240)
        py = rng.uniform(120, unten - 420)
        if physics.passt_durch(px, py, 52.0, segments, pegs,
                               LUECKE + 16):
            pegs.append(physics.Peg(px, py, 52.0))

    finish_y = unten + 420
    auslauf(segments, finish_y)
    starts = startreihen(TEILNEHMER, links + 80, rechts - 80, -80)
    track = physics.Track(segments=segments, pegs=pegs, starts=starts,
                          finish_y=finish_y, tore=tore, name="konzept-pulk")
    return track, TorZeit(finish_y, sperrzeit=12.0), -140.0


def k_formen(seed: int):
    """Valons Vorschlag: grosse Formen, Einstieg oben links, Ausgang
    unten rechts. Das Feld DURCHQUERT die Kammer, statt durch sie
    hindurchzufallen – jede Form teilt den Strom sichtbar.

    Zweite Fassung. Die erste hatte zwei gemessene Fehler: ein auf dem
    Boden stehendes Dreieck bildete mit dem fallenden Boden eine
    Keiltasche, in der das Feld parkte (Stillstand 30 s, 3 von 100
    angekommen), und ein grosser Stein sass 3 px ueber dem Boden – die
    Verklemmung war GEBAUT. Jede Form steht jetzt frei, jeder Abstand
    ist gegen `mindest_luecke(100)` gerechnet und im Kommentar belegt.
    """
    rng = random.Random(seed * 7919 + 11)
    links, rechts, unten = 110.0, 1810.0, 900.0
    segments: list[physics.Segment] = []
    pegs: list[physics.Peg] = []

    segments.append(physics.Segment(links, -420, links, unten,
                                    SEG_RADIUS))
    segments.append(physics.Segment(rechts, -420, rechts, unten + 40,
                                    SEG_RADIUS))

    # Geschwungene Rutsche oben links: Kreisbogen um (680, 120), r = 480,
    # von 180 Grad (Einstieg bei x = 200) bis 100 Grad – dort ist die
    # Tangente fast waagerecht, das Feld verlaesst die Rutsche mit
    # QUERBEWEGUNG nach rechts, etwa bei (600, 590).
    cx, cy, r_bogen = 680.0, 120.0, 480.0
    winkel = [math.radians(a) for a in range(180, 96, -8)]
    punkte = [(cx + r_bogen * math.cos(a), cy + r_bogen * math.sin(a))
              for a in winkel]
    for (x1, y1), (x2, y2) in zip(punkte, punkte[1:]):
        segments.append(physics.Segment(x1, y1, x2, y2, SEG_RADIUS))

    # Die grossen Formen, jede frei stehend. Abstaende (gerechnet):
    #   Kreis 1 zu Rutschenbogen  141 px   Kreis 1 zu Kreis 2  163 px
    #   Kreis 2 zu Boden          190 px   Kreis 3 zu Wand     158 px
    # alle ueber LUECKE = 138.
    pegs.append(physics.Peg(760.0, 300.0, 120.0))
    pegs.append(physics.Peg(1140.0, 540.0, 140.0))
    pegs.append(physics.Peg(1540.0, 260.0, 90.0))
    # Umlenk-Dach ueber dem Ausgang: Spitze nach OBEN. Die erste Fassung
    # hatte die Spitze nach unten und war damit ein Becher – drei Kugeln
    # lagen am Ende einfach darin (Stillstand 21 s).
    segments.append(physics.Segment(1460.0, 690.0, 1540.0, 620.0,
                                    SEG_RADIUS))
    segments.append(physics.Segment(1620.0, 690.0, 1540.0, 620.0,
                                    SEG_RADIUS))

    # Boden faellt nach rechts zum Ausgang im Eck. Lichte Weite des
    # Ausgangs: 362 px zwischen Bodenende und Wand, knapp 6 Kugeln.
    tor_breite = AUSGANG_KUGELN * MARBLE_D
    segments.append(physics.Segment(links, unten - 160, 1180.0, unten,
                                    SEG_RADIUS))
    segments.append(physics.Segment(1180.0, unten, rechts - tor_breite,
                                    unten + 40, SEG_RADIUS))

    finish_y = unten + 460
    auslauf(segments, finish_y)
    starts = startreihen(TEILNEHMER, links + 60, 690.0, -100)
    track = physics.Track(segments=segments, pegs=pegs, starts=starts,
                          finish_y=finish_y, tore=[],
                          name="konzept-formen")
    _ = rng  # Seed variiert hier nur den Lauf, nicht die Landschaft
    return track, physics.RaceToLine(finish_y), -140.0


def k_labyrinth(seed: int):
    """Serpentinen: versetzte Simse, das Feld fliesst als Strom im
    Zickzack. Die Oeffnungen wechseln die Seite; jede ist am FELD
    bemessen, nicht an der Kugel.

    ⚠ GEMESSEN VERWORFEN (03.08.2026) – wie Rotor, Prellboecke und
    Zwischenboeden zuvor. Sieben Fassungen, eine Messreihe, ein Gesetz:

      * Offene Simse: der Pulk parkt unterhalb seines Schuettwinkels
        (1,7 Grad: 0 von 100 unten · 6 Grad: 4 · 14 Grad: 12).
      * Dosier-Trichter 4 Kugeln: verklemmt unter Pulkdruck – exakt die
        Arena-Messung.
      * Korridor 4,4 Kugeln, 26-31 Grad: Bogen ueber dem Mund (9 unten).
      * Korridor 5,9 Kugeln, Kehren als steile Abwuerfe, Fangtrichter
        36 Grad: weiterhin Bogen ueber dem Mund, 94 von 100 stehen.

    Ein 100er-Feld laesst sich ohne Ruettler oder bewegte Teile nicht
    durch Serpentinen schicken: jede Kehre ist lokal ein flacher Sims,
    jeder Uebergang Pulk -> Strom ein Trichter, und der Pulk woelbt
    einen Bogen ueber JEDE Verengung, sobald er als Ganzes drueckt.
    Die Funktion bleibt stehen, damit die naechste Sitzung das Video
    ansehen kann statt die Messreihe zu wiederholen.
    """
    rng = random.Random(seed * 7919 + 11)
    segments: list[physics.Segment] = []
    pegs: list[physics.Peg] = []

    # Mittellinie der Serpentine; die Waende liegen 190 px links und
    # rechts davon. Der Korridormund misst damit 380 px – knapp sechs
    # Kugelbreiten. Mit 140 px (4,4 Kugeln) verklemmte der Pulk am Mund:
    # JEDER Uebergang Pulk -> Strom ist ein Trichter, und unter fuenf
    # Kugelbreiten liegt er im Verklemmungsbereich (Arena-Messung).
    # Kein Punkt des Weges unter 26 Grad, die Kehren selbst sind steile
    # Abwuerfe (fast senkrecht): die Fassung mit 22-Grad-Ellbogen stand
    # genau dort – eine Kehre ist lokal ein flacher Sims, und darauf gilt
    # dasselbe Gesetz wie ueberall: der Pulk parkt.
    mitte_weg = [(960.0, -140.0), (420.0, 200.0), (500.0, 380.0),
                 (1440.0, 800.0), (1360.0, 950.0)]
    for dx in (-190.0, +190.0):
        punkte = [(x + dx, y) for x, y in mitte_weg]
        for (x1, y1), (x2, y2) in zip(punkte, punkte[1:]):
            segments.append(physics.Segment(x1, y1, x2, y2, SEG_RADIUS))

    # Fangtrichter ueber dem Korridormund: STEIL (36 Grad), die flache
    # 22-Grad-Fassung war eine Parkflaeche fuer die aeusseren Reihen.
    segments.append(physics.Segment(250.0, -560.0, 770.0, -150.0,
                                    SEG_RADIUS))
    segments.append(physics.Segment(1670.0, -560.0, 1150.0, -150.0,
                                    SEG_RADIUS))

    # Ruehrsteine IN den Kehren, einzeln geprueft.
    for (x1, y1), (x2, y2) in zip(mitte_weg, mitte_weg[1:]):
        gesetzt = 0
        for _ in range(120):
            if gesetzt >= 2:
                break
            t = rng.uniform(0.25, 0.75)
            px = x1 + (x2 - x1) * t + rng.uniform(-70, 70)
            py = y1 + (y2 - y1) * t + rng.uniform(-40, 40)
            if physics.passt_durch(px, py, 22.0, segments, pegs,
                                   MARBLE_D + 14):
                pegs.append(physics.Peg(px, py, 22.0))
                gesetzt += 1

    # Der Ausgang ist der Absturz am Ende der letzten Kehre, unten links.
    finish_y = 1100.0
    auslauf(segments, finish_y)
    starts = startreihen(TEILNEHMER, 430.0, 1490.0, -600.0)
    track = physics.Track(segments=segments, pegs=pegs, starts=starts,
                          finish_y=finish_y, tore=[],
                          name="konzept-labyrinth")
    return track, physics.RaceToLine(finish_y), -140.0


def k_kessel(seed: int):
    """Die Schuessel: das Feld rollt von beiden Seiten hinein und staut
    sich an der Sperre im tiefsten Punkt. Kreisbewegung statt Fall –
    ein Bild, das keine der Schacht-Disziplinen erzeugen kann."""
    rng = random.Random(seed * 7919 + 11)
    mitte = 960.0
    segments: list[physics.Segment] = []
    pegs: list[physics.Peg] = []

    # Aussenwaende. Der Kesselrand ENDET an ihnen – in der ersten Fassung
    # blieb aussen eine 31-px-Ritze, und 33 Kugeln verklemmten darin.
    # Dieselbe Fehlerklasse wie fuenfmal zuvor: eine Luecke, in die das
    # Feld nicht passt, nur diesmal eine, in die es nicht passen SOLL
    # und trotzdem hineinfand.
    segments.append(physics.Segment(70.0, -420, 70.0, 600.0, SEG_RADIUS))
    segments.append(physics.Segment(1850.0, -420, 1850.0, 600.0, SEG_RADIUS))

    # Der Kessel: Kreisbogen um (960, -20), Radius 920. Die Bogenenden
    # liegen AUF den Wandlinien (x = 92 / 1828, y = 285) – keine Ritze.
    # Tiefster Punkt bei y = 900, unten bleibt ein mittiger Ausgang frei.
    cz, r_kessel = (mitte, -20.0), 920.0
    ausgang = AUSGANG_KUGELN * MARBLE_D
    halb_gap = math.degrees(math.asin((ausgang / 2) / r_kessel))
    a_ende = math.degrees(math.acos((mitte - 92.0) / r_kessel))
    for seite in (+1, -1):
        a_von, a_bis = 90.0 - halb_gap, a_ende
        schritte = 12
        winkel = [a_von + (a_bis - a_von) * i / schritte
                  for i in range(schritte + 1)]
        punkte = [(cz[0] + seite * r_kessel * math.cos(math.radians(a)),
                   cz[1] + r_kessel * math.sin(math.radians(a)))
                  for a in winkel]
        for (x1, y1), (x2, y2) in zip(punkte, punkte[1:]):
            segments.append(physics.Segment(x1, y1, x2, y2, SEG_RADIUS))

    tor_l = mitte - ausgang / 2
    tor_r = mitte + ausgang / 2
    tiefste = cz[1] + r_kessel
    tore = [sperre(tor_l, tor_r, tiefste + 26)]

    # Drei Rührsteine im Kessel, gross genug, um den Strom zu teilen.
    for _ in range(120):
        if len(pegs) >= 3:
            break
        px = rng.uniform(mitte - 520, mitte + 520)
        py = rng.uniform(260, 600)
        if physics.passt_durch(px, py, 60.0, segments, pegs, LUECKE + 16):
            pegs.append(physics.Peg(px, py, 60.0))

    finish_y = tiefste + 420
    auslauf(segments, finish_y)
    starts = startreihen(TEILNEHMER, 380.0, 1540.0, -160)
    track = physics.Track(segments=segments, pegs=pegs, starts=starts,
                          finish_y=finish_y, tore=tore,
                          name="konzept-kessel")
    return track, TorZeit(finish_y, sperrzeit=10.0), -150.0


def k_mix(seed: int):
    """Valons Wahl vom 03.08.2026: pulk × formen. Zwei Kammern als Kette,
    jede eine Grossformen-Landschaft, die das Feld QUER durchlaeuft, und
    an jedem Eck-Ausgang eine Sperre – der Massen-Moment aus `pulk` am
    Ende jeder Durchquerung. Der Ausgang liegt am jeweils ANDEREN Eck
    der naechsten Kammer (Valons Vorschlag vom 30.07.). Kammer B ist
    Kammer A gespiegelt; alle Abstaende uebernehmen damit die in
    `k_formen` gerechneten Werte. Die Kamera faehrt mit.
    """
    rng = random.Random(seed * 7919 + 11)
    links, rechts = 110.0, 1810.0
    dy = 1040.0                       # Versatz der zweiten Kammer
    segments: list[physics.Segment] = []
    pegs: list[physics.Peg] = []

    segments.append(physics.Segment(links, -420, links, 1980.0, SEG_RADIUS))
    segments.append(physics.Segment(rechts, -420, rechts, 1940.0,
                                    SEG_RADIUS))

    # --- Kammer A: wie k_formen ----------------------------------------
    cx, cy, r_bogen = 680.0, 120.0, 480.0
    winkel = [math.radians(a) for a in range(180, 96, -8)]
    punkte = [(cx + r_bogen * math.cos(a), cy + r_bogen * math.sin(a))
              for a in winkel]
    for (x1, y1), (x2, y2) in zip(punkte, punkte[1:]):
        segments.append(physics.Segment(x1, y1, x2, y2, SEG_RADIUS))
    pegs.append(physics.Peg(760.0, 300.0, 120.0))
    pegs.append(physics.Peg(1140.0, 540.0, 140.0))
    pegs.append(physics.Peg(1540.0, 260.0, 90.0))
    segments.append(physics.Segment(1460.0, 690.0, 1540.0, 620.0,
                                    SEG_RADIUS))
    segments.append(physics.Segment(1620.0, 690.0, 1540.0, 620.0,
                                    SEG_RADIUS))
    segments.append(physics.Segment(links, 740.0, 1180.0, 900.0,
                                    SEG_RADIUS))
    segments.append(physics.Segment(1180.0, 900.0, 1426.0, 940.0,
                                    SEG_RADIUS))
    tore = [sperre(1426.0, rechts, 970.0)]

    # --- Kammer B: Kammer A gespiegelt (x -> 1920 - x, y + dy) ---------
    # Fangrampe unter dem A-Ausgang: steil (29 Grad), ein STROM fliesst
    # dort, wo ein ruhender Pulk laengst parken wuerde.
    segments.append(physics.Segment(rechts, 1080.0, 1480.0, 1260.0,
                                    SEG_RADIUS))
    pegs.append(physics.Peg(1160.0, 300.0 + dy, 120.0))
    pegs.append(physics.Peg(780.0, 540.0 + dy, 140.0))
    pegs.append(physics.Peg(380.0, 260.0 + dy, 90.0))
    segments.append(physics.Segment(460.0, 690.0 + dy, 380.0, 620.0 + dy,
                                    SEG_RADIUS))
    segments.append(physics.Segment(300.0, 690.0 + dy, 380.0, 620.0 + dy,
                                    SEG_RADIUS))
    segments.append(physics.Segment(rechts, 740.0 + dy, 740.0, 900.0 + dy,
                                    SEG_RADIUS))
    segments.append(physics.Segment(740.0, 900.0 + dy, 494.0, 940.0 + dy,
                                    SEG_RADIUS))
    tore.append(sperre(links, 494.0, 970.0 + dy))

    finish_y = 2120.0
    auslauf(segments, finish_y)
    starts = startreihen(TEILNEHMER, links + 60, 690.0, -100.0)
    track = physics.Track(segments=segments, pegs=pegs, starts=starts,
                          finish_y=finish_y, tore=tore,
                          name="konzept-mix")
    _ = rng
    # Kamera: None heisst "mitfahren" (build.kamerafahrt).
    return track, TorZeiten(finish_y, {0: 14.0, 1: 34.0}), None


KONZEPTE = {
    "pulk": (k_pulk, "MASS ELIMINATION", "one gate, everybody at once"),
    "formen": (k_formen, "THE CROSSING", "big shapes, far corner exit"),
    "labyrinth": (k_labyrinth, "THE MAZE", "the field flows in serpentines"),
    "kessel": (k_kessel, "THE CAULDRON", "swirl, jam, release"),
    "mix": (k_mix, "THE GAUNTLET", "shapes to cross, gates to survive"),
}


# ---------------------------------------------------------------------------
# Lauf und Video
# ---------------------------------------------------------------------------


def kamera_fahrt(r: physics.RunResult) -> list[float]:
    """Oberkante je Bild fuer die Kammerkette: dem MEDIAN des noch
    laufenden Feldes hinterher, traege gedaempft.

    `build.kamerafahrt` folgt dem Fuehrenden und ist fuer Schaechte
    gebaut – an der Zweikammer-Kette zeigte sie bei Sekunde 36 die leere
    Kammer A, waehrend das Feld laengst in B war (Bild angesehen am
    03.08.2026). Der Median haelt den PULK im Bild, nicht den
    Ausreisser; wer durch ist, zaehlt nicht mehr mit.
    """
    ziel_bild = {i: t * r.fps for i, t in (r.finish_times or {}).items()}
    tops: list[float] = []
    top = -140.0
    for f, bild in enumerate(r.frames):
        ys = sorted(p[1] for i, p in enumerate(bild)
                    if ziel_bild.get(i) is None or ziel_bild[i] > f)
        if ys:
            median = ys[len(ys) // 2]
            wunsch = median - 0.45 * theme.HEIGHT
            wunsch = max(-140.0, min(wunsch,
                                     r.finish_y - theme.HEIGHT + 260))
            top += (wunsch - top) * 0.06
        tops.append(top)
    return tops


def messen(r: physics.RunResult, dauer_deckel: float) -> dict:
    """Die ehrlichen Zahlen eines Konzeptlaufs.

    `verloren` zaehlt Kugeln ausserhalb jeder plausiblen Welt – die stille
    Fehlerklasse aller Arena-Baufehler (Kugel durch die Wand, y = 87 Mio.).
    """
    letzte = r.frames[-1]
    verloren = sum(1 for (x, y, _) in letzte
                   if not (-2000 <= x <= 4000) or not (-3000 <= y <= r.finish_y + 3000))
    kk = sum(1 for h in r.hits if h.kind == "marble")
    return {
        "dauer_s": round(r.duration, 1),
        "am_deckel": r.duration >= dauer_deckel - 0.5,
        "angekommen": len(r.finished),
        "verloren": verloren,
        "stillstand_s": round(physics.stillstand(r), 1),
        "kugel_kugel": round(kk / max(1, len(r.hits)), 2),
        "aufpraelle": len(r.hits),
    }


def lauf(name: str, seed: int, dauer: float):
    bau, _, _ = KONZEPTE[name]
    track, regel, top = bau(seed)
    r = physics.simulate(track, seed, fps=theme.FPS, max_seconds=dauer,
                         patience_seconds=30.0, count=TEILNEHMER,
                         regel=regel, iterationen=SOLVER_ITERATIONEN)
    return r, top


def video(name: str, seed: int, ziel: Path, dauer: float, scale: int,
          crf: int, preset: str) -> dict:
    bau, titel, unter = KONZEPTE[name]
    exe = build.ffmpeg_pfad()
    t0 = time.perf_counter()
    r, top = lauf(name, seed, dauer)
    m = messen(r, dauer)
    print(f"  Lauf      {m['dauer_s']}s, {m['angekommen']}/{TEILNEHMER} "
          f"angekommen, {m['verloren']} verloren, "
          f"Stillstand {m['stillstand_s']}s, "
          f"{m['kugel_kugel'] * 100:.0f} % Kugel-Kugel")

    wav = ziel.with_suffix(".wav")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    stereo, messung = audio.build(r)
    audio.write_wav(wav, stereo)

    gesamt = len(r.frames)
    comps = theme.competitors()
    # top None heisst: die Kammern passen nicht in EIN Bild, die Kamera
    # faehrt mit (Zweikammer-Kette in `mix`). Sonst feste Kamera – die
    # Kammer IST das Bild.
    tops = kamera_fahrt(r) if top is None else None

    def bild_fuer(f):
        # karte_start jenseits des Endes – die Endkarte kann 100 Zeilen
        # noch nicht (draw.result_card, bekannter Befund vom 03.08.),
        # und beurteilt wird hier der LAUF.
        oben = tops[min(f, len(tops) - 1)] if tops is not None else top
        return build.zeichne_bild(r, f, oben, (titel, unter), scale,
                                  gesamt + 10, comps=comps,
                                  runde="KONZEPT " + name.upper(),
                                  punkte=None, seed=seed)

    ergebnis = build.video_schreiben(exe, wav, ziel, theme.FPS, crf, preset,
                                     gesamt, bild_fuer, fortschritt="  Bilder")
    wav.unlink(missing_ok=True)
    print(f"\r  Bilder    {gesamt}/{gesamt}  fertig in "
          f"{time.perf_counter() - t0:.0f}s")

    zeilen = [
        "KONZEPT " + name + " - " + titel,
        "seed " + str(seed) + ", " + str(TEILNEHMER) + " Teilnehmer, "
        + str(m['dauer_s']) + " s",
        "",
    ] + [k + " = " + str(v) for k, v in m.items()] + [
        "",
        "Wegwerf-Vorschau, kein Manifest. Beurteilt wird das BILD.",
    ]
    ziel.with_suffix(".txt").write_text(NL_.join(zeilen) + NL_,
                                        encoding="utf-8")
    print(f"  fertig: {ziel}  ({ziel.stat().st_size / 1e6:.0f} MB)")
    return m


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Konzept-Vorschauen fuer die Langform")
    ap.add_argument("--konzept", choices=sorted(KONZEPTE))
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--dauer", type=float, default=75.0,
                    help="Deckel je Lauf, Sekunden")
    ap.add_argument("--out-dir", default="data/konzepte")
    ap.add_argument("--vorschau", action="store_true",
                    help="klein und schnell (crf 23, veryfast)")
    ap.add_argument("--nur-lauf", action="store_true",
                    help="nur simulieren und messen, kein Video")
    a = ap.parse_args()

    namen = sorted(KONZEPTE) if a.alle or not a.konzept else [a.konzept]
    theme.set_format("quer")
    theme.set_competitors(theme.feld(TEILNEHMER))
    crf, preset = (23, "veryfast") if a.vorschau else (19, "slow")

    for name in namen:
        print(f"{name}  (seed {a.seed})")
        if a.nur_lauf:
            r, _ = lauf(name, a.seed, a.dauer)
            for k, v in messen(r, a.dauer).items():
                print(f"  {k} = {v}")
        else:
            ziel = Path(a.out_dir) / f"K-{name}-seed{a.seed}.mp4"
            video(name, a.seed, ziel, a.dauer, 1, crf, preset)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
