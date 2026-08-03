#!/usr/bin/env python3
"""
gauntlet.py – Disziplin 5: der Spiessrutenlauf. Die Langform-Show, Fassung 2.

Valons Wahl vom 03.08.2026 nach den Konzept-Vorschauen: die Mischung aus
`pulk` und `formen`. Eine Kette bildschirmgrosser Kammern, jede eine
Landschaft aus GROSSEN Formen, die das Feld QUER durchlaufen muss – der
Ausgang liegt am Eck, und zwar am jeweils ANDEREN Eck der naechsten
Kammer (Valons Vorschlag vom 30.07.). Vor jedem Ausgang eine Sperre:
das Feld sammelt sich, dann geht das Tor auf und alle wollen
gleichzeitig durch. An jedem Tor scheidet ein ANTEIL aus, nicht einer –
vorn grosse Schnitte, hinten Duelle.

Was hier bewusst WIEDERVERWENDET wird, statt es neu zu bauen:

  * `arena.Kammern` – die Regel. Sie oeffnet die Sperre adaptiv (alle
    da + Ruhemoment, die Obergrenze ist nur Notdeckel) und wertet die
    Ausscheidungen ueber eine vollstaendige Rangfolge. Beide Lehren
    darin sind teuer bezahlt (Ladebildschirm-Timer, seed 11 mit zwei
    Siegern); dieselbe Klasse Fehler ein drittes Mal zu riskieren waere
    mutwillig.
  * `build.kammerkamera` – feste Kamera je Kammer, gewechselt, wenn die
    MEHRHEIT der Aktiven unten ist. Der Fuehrende ist damit automatisch
    im Bild, sobald es um ihn geht (kleine Kammern, Zieleinlauf), ohne
    dass die Kamera einem Ausreisser durch leere Kammern hinterherjagt –
    genau das tat die Verfolgerkamera an der Zweikammer-Vorschau.
  * Die Grossformen-Geometrie aus `tools/konzepte.py` (k_formen/k_mix),
    dort in fuenf Trockenlaeufen vermessen: Rampen ab 28 Grad tragen
    einen STROM, Boeden um 13 Grad tragen ihn, sobald er faehrt, und
    jede Oeffnung, durch die das FELD muss, braucht
    `physics.mindest_luecke(feld)` – hier erstmals je Kammer an die
    SCHRUMPFENDE Feldgroesse gekoppelt statt an eine feste Zahl.

CLI:
  python -m gravitycup.disciplines.gauntlet --seed 3
  python -m gravitycup.disciplines.gauntlet --search 6
"""
from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass

from ..core import physics, theme
from . import arena

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NAME = "gauntlet"

HOOK = ("THE GAUNTLET", "{n} enter, one leaves")

MARBLE_D = 2 * theme.MARBLE_RADIUS
SEG_RADIUS = arena.SEG_RADIUS
SOLVER_ITERATIONEN = arena.SOLVER_ITERATIONEN

#: Annahmekriterien und Notbremsen-Budget: dieselben wie in der Arena.
MIN_SECONDS = arena.MIN_SECONDS
MAX_SECONDS = arena.MAX_SECONDS
NOTBREMSE_JE_KAMMER = arena.NOTBREMSE_JE_KAMMER

kennzahlen = arena.kennzahlen
check = arena.check


@dataclass(frozen=True)
class Bauart:
    """Die Masse der Kammerkette.

    1700x900 als groesste Kammer ist die Arena-Messung (1800x950 lag bei
    81 % statt 100 % im Bild). Die Ausgaenge bleiben ueberall AUF ODER
    UEBER fuenf Kugelbreiten – unter fuenf beginnt der
    Verklemmungsbereich der Schuettgutmechanik, gemessen am 31.07.
    (seed 7: dreieinhalb Minuten Stau bei 4,0) und noch einmal am 03.08.
    an den Konzept-Trockenlaeufen (4,0-Dosiertrichter verklemmt).
    """

    breite_max: float = 1700.0
    breite_min: float = 820.0
    hoehe: float = 900.0
    #: Senkrechter Abstand Kammerunterkante -> naechste Oberkante. Die
    #: Fangrampe der naechsten Kammer liegt IN ihr, nicht dazwischen.
    abstand: float = 140.0
    #: Ausgangsweite in Kugeldurchmessern, gross -> klein mit dem Feld.
    ausgang_kugeln: float = 6.0
    ausgang_kugeln_min: float = 5.0
    #: Anteil des Feldes, der an einem Tor ausscheidet, solange das Feld
    #: gross ist. Ab `einzel_ab` Aktiven scheidet genau einer je Kammer
    #: aus – das Finale sind Duelle, nicht Schnitte. 0,07 statt 0,15 nach
    #: den Messungen vom 03.08.: die Laenge kommt aus der Kammerzahl,
    #: und seit das Tor bei Ruhe oeffnet, ist mehr Kammern der einzige
    #: Hebel ohne tote Luft.
    schnitt: float = 0.07
    einzel_ab: int = 10
    #: Wuehlzeit: wie lange der volle Pulk vor der Sperre wuehlt, NACHDEM
    #: alle da sind – zusaetzlich zum `halt_beat`, skaliert mit dem
    #: Feldanteil der Kammer (volles Feld: ganze Zeit, Duell: praktisch
    #: null). Das ist der Kern von Valons Konzeptwahl (der `pulk`-Moment)
    #: und bewusst KEIN fester Timer je Kammer: genau der war in der
    #: Arena ein Ladebildschirm. Ein 100er-Pulk ruht nie sichtbar
    #: (Stillstand blieb bei 1,2 s), drei wartende Kugeln schon – deshalb
    #: die Skalierung. 12,0: mit 9,0 lag seed 3 bei 281 s und damit
    #: unter dem 300-s-Fenster der Langform.
    wuehlzeit: float = 12.0
    #: Haltezeit-OBERGRENZEN erste/letzte Kammer (die Sperre oeffnet
    #: vorher, sobald alle da sind + `halt_beat`). Werte aus der Arena.
    halt_erste: float = 22.0
    halt_letzte: float = 8.0
    halt_beat: float = 1.6

    def pruefen(self) -> None:
        if self.ausgang_kugeln_min < 5.0:
            raise ValueError(
                "Ausgang unter fuenf Kugelbreiten liegt im "
                "Verklemmungsbereich (Messung 31.07./03.08.2026)")
        if not 0.0 < self.schnitt < 0.5:
            raise ValueError(f"Schnittanteil {self.schnitt} ist kein Anteil")

    def breite(self, drin: int, hoechste: int) -> float:
        if hoechste <= 1:
            return self.breite_max
        anteil = max(0.0, min(1.0, (drin - 1) / (hoechste - 1)))
        return self.breite_min + (self.breite_max - self.breite_min) * anteil

    def ausgang(self, drin: int | None = None,
                hoechste: int | None = None) -> float:
        if drin is None or hoechste is None or hoechste <= 1:
            return self.ausgang_kugeln * MARBLE_D
        anteil = max(0.0, min(1.0, (drin - 1) / (hoechste - 1)))
        kugeln = (self.ausgang_kugeln_min
                  + (self.ausgang_kugeln - self.ausgang_kugeln_min) * anteil)
        return kugeln * MARBLE_D


VORGABE = Bauart()


def leiter(teilnehmer: int, bauart: Bauart = VORGABE) -> list[int]:
    """Wie viele nach jeder Kammer noch im Spiel sind.

    Anders als in der Arena (eine Ausscheidung je Kammer) faellt hier ein
    ANTEIL: das ist das `pulk`-Bild – ein Massen-Moment am Tor. Kleine
    Felder wechseln auf Einzelausscheidung, sonst waere das Finale nach
    zwei Toren vorbei.
    """
    if teilnehmer < 2:
        raise ValueError("mindestens zwei Teilnehmer")
    stufen: list[int] = []
    n = teilnehmer
    while n > 1:
        raus = max(1, round(n * bauart.schnitt)) if n > bauart.einzel_ab else 1
        n -= raus
        stufen.append(max(1, n))
        n = stufen[-1]
    return stufen


def kammerformen(teilnehmer: int,
                 bauart: Bauart = VORGABE) -> list[arena.Kammerform]:
    """Die Kette, von oben nach unten. Nutzt arenas Kammerform, damit
    `arena.Kammern` und `build.kammerkamera` sie unveraendert verstehen."""
    mitte = theme.WIDTH / 2
    stufen = leiter(teilnehmer, bauart)
    formen: list[arena.Kammerform] = []
    y = 0.0
    drin = teilnehmer
    for k, weiter in enumerate(stufen):
        b = bauart.breite(drin, teilnehmer)
        formen.append(arena.Kammerform(
            nummer=k + 1, oben=y, unten=y + bauart.hoehe,
            links=mitte - b / 2, rechts=mitte + b / 2,
            weiter=weiter,
            ausgang=bauart.ausgang(drin, teilnehmer),
            halt=bauart.halt_erste
            + (bauart.halt_letzte - bauart.halt_erste)
            * (k / max(1, len(stufen) - 1)),
            austritt=y + bauart.hoehe + 70.0))
        y += bauart.hoehe + bauart.abstand
        drin = weiter
    return formen


def _seite(nummer: int) -> int:
    """+1: Ausgang rechts, -1: Ausgang links. Wechselt je Kammer."""
    return +1 if nummer % 2 == 1 else -1


class KammernMitRuhe(arena.Kammern):
    """Arenas Kammern-Regel, plus die Wuehlzeit je Kammer.

    Die Wuehlzeit ist KEIN Timer: das Tor oeffnet, sobald der Pulk zur
    Ruhe gekommen ist (alle da, und zwei Sekunden lang bewegt sich
    praktisch nichts mehr) – die Zahl aus der Bauart ist nur die
    Obergrenze. Mit fester Wuehlzeit lag ein fertig gesetzter Haufen
    10-11 s bewegungslos vor der Sperre (gemessen an sechs Seeds am
    03.08.); genau die tote Luft, die Valon an der Vorschau
    beanstandet hat.

    Die Regel selbst bleibt unangetastet – sie liest `halt_beat` in
    jedem Schritt, also reicht es, den Wert lagegerecht zu liefern.
    Die Obergrenze `form.halt` greift unveraendert als Notdeckel.
    """

    #: Ab weniger als dieser Bewegung (px/s der lebhaftesten Kugel)
    #: gilt der Pulk als ruhig.
    RUHE_EPS = 4.0
    RUHIG_DAUER = 2.0

    def __init__(self, formen, finish_y, ruhe: list[float],
                 halt_beat: float = 1.6):
        self._beat_basis = halt_beat
        self._ruhe = list(ruhe)
        self._ruhig_seit: float | None = None
        self._ruhig = False
        super().__init__(formen, finish_y, halt_beat=halt_beat)

    @property
    def halt_beat(self) -> float:
        if self._ruhig:
            return self._beat_basis
        k = min(getattr(self, "kammer", 0), len(self._ruhe) - 1)
        return self._beat_basis + self._ruhe[k]

    @halt_beat.setter
    def halt_beat(self, wert: float) -> None:
        self._beat_basis = wert

    def schritt(self, zeit_von, dt, y_vorher, y_jetzt, x_jetzt=None):
        zeit = zeit_von + dt
        delta = max((abs(y_jetzt[i] - y_vorher[i]) for i in self.aktiv),
                    default=0.0)
        if delta > self.RUHE_EPS * dt:
            self._ruhig_seit = None
        elif self._ruhig_seit is None:
            self._ruhig_seit = zeit
        self._ruhig = (self._ruhig_seit is not None
                       and zeit - self._ruhig_seit >= self.RUHIG_DAUER)
        return super().schritt(zeit_von, dt, y_vorher, y_jetzt, x_jetzt)


def build_track(seed: int, teilnehmer: int,
                bauart: Bauart = VORGABE) -> physics.Track:
    """Die Strecke einer Folge. Gleicher Seed, gleiche Strecke."""
    bauart.pruefen()
    rng = random.Random(seed * 7919 + 11)
    formen = kammerformen(teilnehmer, bauart)
    segments: list[physics.Segment] = []
    pegs: list[physics.Peg] = []
    tore: list[list[physics.Segment]] = []

    start_hoehe = _starthoehe(teilnehmer, formen[0])

    drin = teilnehmer
    for form in formen:
        b = form.rechts - form.links
        o = _seite(form.nummer)
        luecke = physics.mindest_luecke(drin)
        exit_x = form.rechts if o > 0 else form.links   # Ausgangs-Eck
        entry_x = form.links if o > 0 else form.rechts  # Einstiegs-Seite

        # Seitenwaende. Die erste Kammer traegt die Startkammer oben.
        oben_wand = form.oben - 60 - (start_hoehe if form.nummer == 1 else 0)
        segments.append(physics.Segment(form.links, oben_wand,
                                        form.links, form.unten + 40,
                                        SEG_RADIUS))
        segments.append(physics.Segment(form.rechts, oben_wand,
                                        form.rechts, form.unten + 40,
                                        SEG_RADIUS))

        # Die KASKADE: ein Band an der Einstiegswand, 26 Grad steil, ueber
        # gut die halbe Kammer. Es faengt den Torstoss von oben garantiert
        # (es haengt, wo die Kugeln einfallen) und traegt ihn quer in die
        # Kammer, bevor er auf Formen und Boden faellt.
        #
        # ZWEI verworfene Fassungen davor, beide gemessen am 03.08.:
        # eine Rampe, die auf ein 12-Grad-Band an der Gegenwand wirft
        # (12 Grad liegt unter dem Schuettwinkel – der Torstoss landet
        # als Klumpen und PARKT: 19 Kugeln, 763 s Stillstand, Notbremse),
        # und ein steiles Band an der Gegenwand (der Strom muss die
        # Oeffnung im Flug queren – ob er das Band trifft, haengt am
        # Tempo, und das ist Glueckssache je Kammer). Ein Band UNTER dem
        # Einfall mit mehr als Schuettwinkel-Neigung hat beide Probleme
        # nicht.
        segments.append(physics.Segment(
            entry_x, form.oben + 90,
            entry_x + o * 0.55 * b, form.oben + 90 + 0.268 * b,
            SEG_RADIUS))

        # Boden zum Ausgangs-Eck, zwei Baender wie in k_formen/k_mix
        # (dort vermessen: ~13 Grad tragen den fahrenden Strom).
        ausgang = form.ausgang
        knick_x = form.links + (0.63 * b if o > 0 else 0.37 * b)
        segments.append(physics.Segment(
            entry_x, form.unten - 0.095 * b, knick_x, form.unten,
            SEG_RADIUS))
        segments.append(physics.Segment(
            knick_x, form.unten, exit_x - o * ausgang, form.unten + 40,
            SEG_RADIUS))

        # Umlenk-Dach ueber dem Ausgangsweg, Spitze nach OBEN (die
        # Spitze nach unten war ein Becher – Konzept-Trockenlauf 03.08.).
        if b > 1100:
            apex_x = exit_x - o * 0.21 * b
            fuss = 0.047 * b
            segments.append(physics.Segment(
                apex_x - fuss, form.unten - 210, apex_x, form.unten - 280,
                SEG_RADIUS))
            segments.append(physics.Segment(
                apex_x + fuss, form.unten - 210, apex_x, form.unten - 280,
                SEG_RADIUS))

        # Die grossen Formen: wenige, GROSSE Kreise statt Stiftraster.
        # Jede einzeln gegen alles Bisherige geprueft, mit der Luecke des
        # FELDES dieser Kammer – nicht der Kugel, nicht der Stammfuenf.
        wieviele = max(1, int(b / 540))
        gesetzt = 0
        versuche = 0
        while gesetzt < wieviele and versuche < 400:
            versuche += 1
            r = rng.uniform(0.055 * b, 0.085 * b)
            px = rng.uniform(form.links + r + luecke,
                             form.rechts - r - luecke)
            py = rng.uniform(form.oben + 0.28 * bauart.hoehe,
                             form.unten - 300)
            if physics.passt_durch(px, py, r, segments, pegs, luecke + 16):
                pegs.append(physics.Peg(px, py, r))
                gesetzt += 1

        # Die Sperre, knapp unter dem Trichtermund des Ecks.
        tor_innen = exit_x - o * ausgang
        tor_l, tor_r = sorted((tor_innen, exit_x))
        tore.append([physics.Segment(tor_l - SEG_RADIUS, form.unten + 70,
                                     tor_r + SEG_RADIUS, form.unten + 70,
                                     SEG_RADIUS)])
        drin = form.weiter

    # Auslauf: Becken tief UNTER der Ziellinie, Waende beginnen deutlich
    # darueber. Beide Masse sind Messwerte der Konzept-Trockenlaeufe vom
    # 03.08.: ein flaches Becken laesst den Schuettkegel ueber die Linie
    # zurueckwachsen, und ein Eck-Ausgang wirft Kugeln mit Querschwung
    # ueber jede Wand, die erst unterhalb beginnt.
    letzte = formen[-1]
    finish_y = letzte.unten + 520.0
    segments.append(physics.Segment(60, finish_y + 700, 1860,
                                    finish_y + 700, SEG_RADIUS))
    segments.append(physics.Segment(60, finish_y - 470, 60,
                                    finish_y + 710, SEG_RADIUS))
    segments.append(physics.Segment(1860, finish_y - 470, 1860,
                                    finish_y + 710, SEG_RADIUS))

    starts = _startplaetze(teilnehmer, formen[0])
    return physics.Track(segments=segments, pegs=pegs, starts=starts,
                         finish_y=finish_y, tore=tore,
                         name=f"{NAME}-{teilnehmer}")


def _startraster(erste: arena.Kammerform) -> tuple[float, float, int, float]:
    innen_l = erste.links + SEG_RADIUS + theme.MARBLE_RADIUS + 6
    innen_r = erste.rechts - SEG_RADIUS - theme.MARBLE_RADIUS - 6
    abstand = MARBLE_D + 10
    je_reihe = max(1, int((innen_r - innen_l) // abstand))
    return innen_l, innen_r, je_reihe, abstand


def _starthoehe(anzahl: int, erste: arena.Kammerform) -> float:
    _, _, je_reihe, _ = _startraster(erste)
    reihen = -(-anzahl // je_reihe)
    return reihen * (MARBLE_D + 8) + 60.0


def _startplaetze(anzahl: int,
                  erste: arena.Kammerform) -> list[tuple[float, float]]:
    innen_l, innen_r, je_reihe, abstand = _startraster(erste)
    plaetze: list[tuple[float, float]] = []
    reihe = 0
    while len(plaetze) < anzahl:
        y = erste.oben - 80.0 - reihe * (MARBLE_D + 8)
        rest = min(je_reihe, anzahl - len(plaetze))
        breite = (rest - 1) * abstand
        x0 = (innen_l + innen_r) / 2 - breite / 2
        for i in range(rest):
            plaetze.append((x0 + i * abstand, y))
        reihe += 1
    return plaetze


def notbremse(teilnehmer: int, bauart: Bauart | None = None) -> float:
    b = bauart or VORGABE
    formen = kammerformen(teilnehmer, b)
    halten = sum(f.halt for f in formen)
    return max(physics.MAX_SECONDS,
               halten + len(formen) * NOTBREMSE_JE_KAMMER)


def run(seed: int, teilnehmer: int = 100,
        bauart: Bauart = VORGABE) -> physics.RunResult:
    """Einen Lauf rechnen. Regel und Kamera-Daten wie in der Arena."""
    track = build_track(seed, teilnehmer, bauart)
    formen = kammerformen(teilnehmer, bauart)
    grenze = notbremse(teilnehmer, bauart)
    drin = teilnehmer
    ruhe = []
    for f in formen:
        ruhe.append(bauart.wuehlzeit * (drin / teilnehmer))
        drin = f.weiter
    return physics.simulate(
        track, seed,
        regel=KammernMitRuhe(formen, track.finish_y, ruhe,
                             halt_beat=bauart.halt_beat),
        marks=[f.austritt for f in formen],
        count=teilnehmer,
        max_seconds=grenze,
        patience_seconds=grenze,
        iterationen=SOLVER_ITERATIONEN,
        extras={"mark_label": "STAGE",
                "notbremse": round(grenze, 1),
                "kammern": [[f.links, f.oben, f.rechts, f.unten, f.weiter]
                            for f in formen]})


def main() -> int:
    ap = argparse.ArgumentParser(description="Spiessrutenlauf (Langform)")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--teilnehmer", type=int, default=100)
    ap.add_argument("--search", type=int, metavar="N",
                    help="N Seeds messen; zeigt bewusst NICHT den Sieger")
    a = ap.parse_args()

    theme.set_format("quer")
    theme.set_competitors(theme.feld(a.teilnehmer))

    seeds = (range(1, a.search + 1) if a.search
             else [a.seed if a.seed is not None else 3])
    for seed in seeds:
        r = run(seed, a.teilnehmer)
        k = kennzahlen(r)
        probleme = check(r)
        urteil = "brauchbar" if not probleme else "; ".join(probleme)
        print(f"seed {seed:3d}  {r.duration / 60:5.1f} min  "
              f"{len(r.eliminated):3d} raus  "
              f"stillstand {k['stillstand']:5.1f} s  "
              f"totzeit {k['totzeit']:5.1f} s  "
              f"kugel-kugel {k['kugel_kugel'] * 100:3.0f} %  {urteil}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
