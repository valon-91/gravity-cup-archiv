#!/usr/bin/env python3
"""
elimination.py – Disziplin 2: Eliminierung.

An jedem Kontrollpunkt scheidet der Letzte aus. Fuenf Teilnehmer, vier
Kontrollpunkte, einer bleibt uebrig.

Das ist die erste Disziplin, die eine ANDERE Siegbedingung hat als „wer
zuerst unten ist". Bis hierher stand die in `physics.simulate` fest
verdrahtet, obwohl die Doku seit B2 behauptet, eine Disziplin liefere
„Geometrie UND Siegbedingung". Diese Datei ist der Beleg, dass die Naht
jetzt wirklich existiert: sie bringt ihre Regel selbst mit.

Warum das Format traegt: beim Sturzrennen ist nach zehn Sekunden meist
klar, wer vorn liegt. Hier faellt alle paar Sekunden eine Entscheidung,
und wer zurueckliegt, ist beim naechsten Kontrollpunkt raus – nicht bloss
Vierter. Der Zuschauer hat vier Mal einen Grund weiterzuschauen statt
einmal.

CLI-Test:
  python -m gravitycup.disciplines.elimination --seed 1
  python -m gravitycup.disciplines.elimination --search 10
  python -m gravitycup.disciplines.elimination --geometrie 200
"""
from __future__ import annotations

import argparse
import random
import sys

from ..core import physics, theme

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NAME = "elimination"

HOOK = ("Last one out.", "four gates, one survivor")

# ---------------------------------------------------------------------------
# Streckenform
#
# Bewusst NICHT der Zickzack des Sturzrennens. Die Roadmap verlangt eigenen
# Simulationscode je Disziplin, und der Zuschauer soll die Disziplin am
# Bild erkennen, nicht am Titel. Hier: ein senkrechter Schacht aus
# Abschnitten, jeder mit Stiftfeld und Trichter, darunter ein
# Kontrollpunkt.
# ---------------------------------------------------------------------------

WALL_LEFT, WALL_RIGHT = 40.0, 1040.0
SEG_RADIUS = theme.TRACK_WIDTH / 2
PEG_RADIUS = float(theme.PEG_RADIUS)

MARBLE_D = 2 * theme.MARBLE_RADIUS            # 64 px
MIN_GAP = MARBLE_D + 10                       # 74 px
CLEARANCE = MARBLE_D + 26                     # 90 px

START_Y = 150.0
START_SPACING = 78.0

#: Vier Kontrollpunkte fuer fuenf Teilnehmer. Die Zahl ist nicht frei:
#: es muss genau einer uebrig bleiben.
TORE = len(theme.competitors()) - 1

#: Wo der erste Abschnitt beginnt – darueber ist Platz fuer den Start.
ERSTER_ABSCHNITT = 620.0

#: Jeder Abschnitt beginnt mit flachen Rutschen.
#:
#: Ohne sie ist die Strecke fast reiner freier Fall, und der ist schnell:
#: die erste Fassung war nach 8,8 Sekunden vorbei, das Fenster verlangt
#: 20–38. Mehr Hoehe haette es schlimmer gemacht – laenger fallen heisst
#: schneller fallen. Die Bremse ist das ROLLEN, nicht der Weg.
#:
#: Gemessen ueber 40 Seeds: eine Rutsche je Abschnitt ergab 8,6–10,5 s,
#: zwei ergeben das Doppelte. Das Sturzrennen kommt auf denselben Wert –
#: rund 2,8 s je Rampe.
RUTSCHEN_JE_ABSCHNITT = 3
RUTSCHE_NEIGUNG = (0.26, 0.40)
RUTSCHE_LAENGE = (620.0, 880.0)
RUTSCHE_ABSTAND = 430.0

#: Gefaelle-Deckel. Ohne ihn faellt eine Rutsche fast auf die naechste:
#: bei 370 px Abstand und bis zu 352 px Gefaelle blieben 18 px – eine Kugel
#: ist 64. Das Sturzrennen hat denselben Deckel (RAMP_DROP_MAX); hier
#: fehlte er, und genau dort standen die Kugeln der Seeds 16, 36, 37, 38,
#: 44 und 55 gestapelt fest.
RUTSCHE_DROP_MAX = RUTSCHE_ABSTAND - (MARBLE_D + 2 * SEG_RADIUS + 40)

#: Lichte Weite zwischen Rutschenende und gegenueberliegender Wand.
#:
#: Hier reicht CLEARANCE NICHT, anders als beim Sturzrennen. Der Grund ist
#: die Disziplin selbst: der Trichter fuehrt das Feld vor jedem Tor
#: zusammen, danach kommen die Kugeln als Pulk an. Vier Kugeln in einem
#: Durchlass, der genau eine breit ist, verkeilen sich – gemessen an den
#: Seeds 20, 21 und 33, die alle bei 60 s Notbremse endeten, mit vier
#: gestapelten Kugeln am selben Rutschenende. Platz fuer zwei loest es.
RUTSCHE_ENDE_WEITE = 2 * MARBLE_D + 26        # 154 px

#: Lichte Weite des Trichters. Zwei Kugeln nebeneinander passen (2x64),
#: drei nicht – so entsteht am Tor ein Gedraenge, ohne dass es verklemmt.
#: Enger waere die Stelle, an der B4 sich verkeilt hat.
TOR_WEITE = 190.0

#: Stiftfeld je Abschnitt: versetzte Reihen, die das Feld auseinanderziehen,
#: bevor der Trichter es wieder zusammenfuehrt.
STIFT_REIHEN = 2
STIFT_JE_REIHE = 5
STIFT_REIHEN_ABSTAND = 116.0

#: Aufbau eines Abschnitts, alles als Abstand von seiner Oberkante.
#: ABGELEITET, nicht gewaehlt – die Reihenfolge Rutschen, Stifte, Trichter,
#: Kontrollpunkt muss stimmen, und ein Test prueft sie. Stand der
#: Kontrollpunkt einmal ueber dem Tor, entschied er, bevor das Tor
#: ueberhaupt gewirkt hatte.
RUTSCHE_OBEN = 60.0
#: tiefste Stelle, die eine Rutsche erreichen kann
_RUTSCHE_TIEF = (RUTSCHE_OBEN
                 + (RUTSCHEN_JE_ABSCHNITT - 1) * RUTSCHE_ABSTAND
                 + RUTSCHE_DROP_MAX)
STIFTE_OBEN = _RUTSCHE_TIEF + 90.0
_STIFTE_TIEF = STIFTE_OBEN + (STIFT_REIHEN - 1) * STIFT_REIHEN_ABSTAND
TRICHTER_OBEN = _STIFTE_TIEF + 110.0
TRICHTER_HOEHE = 300.0
KONTROLLPUNKT = TRICHTER_OBEN + TRICHTER_HOEHE + 60.0
ABSCHNITT = KONTROLLPUNKT + 80.0

#: Ein Lauf darf nur veroeffentlicht werden, wenn er hier hineinpasst.
MIN_SECONDS = 20.0
MAX_SECONDS = 38.0
SEARCH_CUTOFF = 46.0

#: Mindestabstand zweier Ausscheidungen. Fallen zwei Tore fast gleichzeitig,
#: sieht der Zuschauer die erste gar nicht.
MIN_ABSTAND_TORE = 1.2


# ---------------------------------------------------------------------------
# Die Siegbedingung
# ---------------------------------------------------------------------------


class Elimination(physics.Regel):
    """An jedem Kontrollpunkt scheidet der Letzte aus.

    Der Kontrollpunkt loest aus, sobald alle bis auf EINEN der noch aktiven
    Teilnehmer ihn ueberquert haben. Wer dann noch darueber steht, ist raus.

    Das macht die Disziplin nebenbei robust: eine haengengebliebene Kugel
    blockiert nicht den Lauf, sie scheidet aus. Beim Sturzrennen war genau
    das der Grund, warum 94 % der Seeds unbrauchbar waren.
    """

    name = "eliminierung"

    def __init__(self, kontrollpunkte: list[float], finish_y: float):
        if not kontrollpunkte:
            raise ValueError("Eliminierung ohne Kontrollpunkte")
        self.kontrollpunkte = list(kontrollpunkte)
        self.finish_y = finish_y

    def vorbereiten(self, count: int) -> None:
        super().vorbereiten(count)
        if len(self.kontrollpunkte) != count - 1:
            raise ValueError(
                f"{count} Teilnehmer brauchen {count - 1} Kontrollpunkte, "
                f"die Strecke hat {len(self.kontrollpunkte)}")
        self.aktiv = set(range(count))
        self.tor = 0                       # naechster Kontrollpunkt
        self.durch: dict[int, float] = {}  # wer ihn wann gequert hat
        self.reihenfolge_raus: list[int] = []
        #: Fuers Bild: (Zeit, Kontrollpunkt, wer raus ist)
        self.ereignisse: list[tuple[float, int, int]] = []

    # -- Ablauf ------------------------------------------------------------

    def schritt(self, zeit_von: float, dt: float,
                y_vorher: list[float], y_jetzt: list[float],
                x_jetzt: list[float] | None = None) -> set[int]:
        if self.tor >= len(self.kontrollpunkte):
            # Alle Tore durch. Der Letzte laeuft noch ins Ziel, damit das
            # Rennen einen sichtbaren Schlusspunkt hat.
            for i in sorted(self.aktiv):
                if i in self.zielzeiten:
                    continue
                anteil = physics.linie_gequert(y_vorher[i], y_jetzt[i],
                                               self.finish_y)
                if anteil is not None:
                    self.zielzeiten[i] = zeit_von + anteil * dt
            return set()

        linie = self.kontrollpunkte[self.tor]
        for i in sorted(self.aktiv):
            if i in self.durch:
                continue
            anteil = physics.linie_gequert(y_vorher[i], y_jetzt[i], linie)
            if anteil is not None:
                self.durch[i] = zeit_von + anteil * dt

        if len(self.aktiv) <= 1 or len(self.durch) < len(self.aktiv) - 1:
            return set()

        # Der Letzte ist entweder der, der noch nicht durch ist – oder,
        # wenn im selben Rechenschritt ALLE gequert haben, der mit der
        # spaetesten Querungszeit. Ohne den zweiten Fall bliebe bei einem
        # Gleichstand niemand haengen und der Lauf haette am Ende mehr
        # Teilnehmer als Tore.
        offen = self.aktiv - set(self.durch)
        if len(offen) == 1:
            verlierer = offen.pop()
        else:
            verlierer = max(self.durch, key=lambda i: self.durch[i])

        zeit = zeit_von + dt
        self.ausgeschieden[verlierer] = zeit
        self.reihenfolge_raus.append(verlierer)
        self.ereignisse.append((zeit, self.tor, verlierer))
        self.aktiv.discard(verlierer)
        self.tor += 1
        self.durch = {}
        return {verlierer}

    def erledigt(self) -> bool:
        return (len(self.aktiv) <= 1
                and all(i in self.zielzeiten for i in self.aktiv))

    def rangfolge(self, letzte) -> list[int]:
        """Der Ueberlebende zuerst, dann rueckwaerts nach Ausscheiden.

        Wer zuletzt rausgeflogen ist, wird Zweiter – wer zuerst, Letzter.
        Bricht der Lauf vorzeitig ab (Notbremse), werden die noch Aktiven
        nach erreichter Tiefe gereiht, damit die Wertung vollstaendig
        bleibt.
        """
        mit_ziel = sorted((i for i in self.aktiv if i in self.zielzeiten),
                          key=lambda i: self.zielzeiten[i])
        ohne_ziel = sorted((i for i in self.aktiv if i not in self.zielzeiten),
                           key=lambda i: -letzte[i][1])
        return mit_ziel + ohne_ziel + list(reversed(self.reihenfolge_raus))


# ---------------------------------------------------------------------------
# Geometrie
# ---------------------------------------------------------------------------


def kontrollpunkte(abschnitte: int = TORE) -> list[float]:
    """Die y-Linien der Kontrollpunkte. Immer UNTER dem jeweiligen Tor."""
    return [ERSTER_ABSCHNITT + k * ABSCHNITT + KONTROLLPUNKT
            for k in range(abschnitte)]


def build_track(seed: int, tore: int = TORE) -> physics.Track:
    """Die Strecke einer Runde. Gleicher Seed, gleiche Strecke."""
    rng = random.Random(seed * 97 + 11)
    segments: list[physics.Segment] = []
    pegs: list[physics.Peg] = []
    mitte = theme.WIDTH / 2

    punkte = kontrollpunkte(tore)
    finish_y = punkte[-1] + 520.0

    wand_links = physics.Segment(WALL_LEFT, 0, WALL_LEFT, finish_y + 200,
                                 SEG_RADIUS)
    wand_rechts = physics.Segment(WALL_RIGHT, 0, WALL_RIGHT, finish_y + 200,
                                  SEG_RADIUS)

    # Die Rutschen wechseln die Richtung, und ob sie links oder rechts
    # anfangen, entscheidet der Seed – sonst begaenstigt eine feste
    # Richtung immer dieselbe Bildseite (die Lehre aus B4).
    gespiegelt = rng.random() < 0.5

    # --- Erst ALLE Segmente, dann die Stifte -----------------------------
    # In der ersten Fassung wurden die Stifte auf ein Raster gesetzt, ohne
    # sie gegen den Trichter zu pruefen – dieselbe Blindheit, an der das
    # Sturzrennen 94 % seiner Laeufe verloren hat.
    stift_baender: list[tuple[float, float]] = []

    for k in range(tore):
        oben = ERSTER_ABSCHNITT + k * ABSCHNITT

        # --- Rutschen: die eigentliche Bremse ----------------------------
        for r in range(RUTSCHEN_JE_ABSCHNITT):
            laenge = rng.uniform(*RUTSCHE_LAENGE)
            gefaelle = min(laenge * rng.uniform(*RUTSCHE_NEIGUNG),
                           RUTSCHE_DROP_MAX)
            nach_rechts = ((k * RUTSCHEN_JE_ABSCHNITT + r) % 2 == 0) != gespiegelt
            if nach_rechts:
                x_von = WALL_LEFT + 20
                x_bis = min(WALL_RIGHT - SEG_RADIUS - RUTSCHE_ENDE_WEITE
                            - SEG_RADIUS, x_von + laenge)
            else:
                x_von = WALL_RIGHT - 20
                x_bis = max(WALL_LEFT + SEG_RADIUS + RUTSCHE_ENDE_WEITE
                            + SEG_RADIUS, x_von - laenge)
            y = oben + RUTSCHE_OBEN + r * RUTSCHE_ABSTAND
            segments.append(physics.Segment(x_von, y, x_bis, y + gefaelle,
                                            SEG_RADIUS))

        # --- Trichter auf das Tor zu -------------------------------------
        # Die Seite, zu der er zieht, wechselt mit dem Seed.
        versatz = rng.uniform(-90.0, 90.0)
        tor_links = mitte + versatz - TOR_WEITE / 2
        tor_rechts = mitte + versatz + TOR_WEITE / 2
        segments.append(physics.Segment(
            WALL_LEFT + 20, oben + TRICHTER_OBEN,
            tor_links, oben + TRICHTER_OBEN + TRICHTER_HOEHE, SEG_RADIUS))
        segments.append(physics.Segment(
            WALL_RIGHT - 20, oben + TRICHTER_OBEN,
            tor_rechts, oben + TRICHTER_OBEN + TRICHTER_HOEHE, SEG_RADIUS))

        stift_baender.append((oben + STIFTE_OBEN,
                              oben + STIFTE_OBEN
                              + (STIFT_REIHEN - 1) * STIFT_REIHEN_ABSTAND))

    # Auslauf hinter dem letzten Tor
    segments.append(physics.Segment(WALL_LEFT, finish_y + 190,
                                    WALL_RIGHT, finish_y + 190, SEG_RADIUS))
    segments.append(wand_links)
    segments.append(wand_rechts)

    # --- Stifte, jeder gegen alles bisherige geprueft --------------------
    links = WALL_LEFT + SEG_RADIUS + CLEARANCE + PEG_RADIUS
    rechts = WALL_RIGHT - SEG_RADIUS - CLEARANCE - PEG_RADIUS
    schritt = (rechts - links) / (STIFT_JE_REIHE - 1)
    for band_oben, _ in stift_baender:
        phase = rng.uniform(-schritt / 2, schritt / 2)
        for reihe in range(STIFT_REIHEN):
            y = band_oben + reihe * STIFT_REIHEN_ABSTAND
            zeilenversatz = schritt / 2 if reihe % 2 else 0.0
            for n in range(-1, STIFT_JE_REIHE + 1):
                x = links + phase + zeilenversatz + n * schritt
                if not links <= x <= rechts:
                    continue
                px = x + rng.uniform(-4, 4)
                py = y + rng.uniform(-4, 4)
                if physics.passt_durch(px, py, PEG_RADIUS,
                                       segments, pegs, CLEARANCE):
                    pegs.append(physics.Peg(px, py, PEG_RADIUS))

    starts = [(mitte + (i - 2) * START_SPACING, START_Y)
              for i in range(len(theme.competitors()))]

    return physics.Track(segments=segments, pegs=pegs, starts=starts,
                         finish_y=finish_y, name=f"{NAME}-{tore}")


#: Segmente je Abschnitt: die Rutschen, dann die beiden Trichterhaelften.
#: `build_track` haelt sich daran, `tor_paare` verlaesst sich darauf, und
#: ein Test nagelt es fest.
SEGMENTE_JE_ABSCHNITT = RUTSCHEN_JE_ABSCHNITT + 2


def tor_paare(track: physics.Track,
              tore: int = TORE) -> list[tuple[physics.Segment, physics.Segment]]:
    """Die beiden Trichterhaelften je Abschnitt.

    Sie werden ueber ihre Position in der Liste geholt, nicht geraten. Der
    erste Versuch paarte `segments[0::2]` mit `segments[1::2]` – bei fuenf
    Segmenten je Abschnitt liegt das echte Trichterpaar auf den Indizes 3
    und 4, und die Reissverschluss-Paarung liefert (2,3) und (4,5). Sie
    hat also nie ein Tor erwischt: die Torpruefung prueste nichts und
    meldete trotzdem „in Ordnung".
    """
    paare = []
    for k in range(tore):
        basis = k * SEGMENTE_JE_ABSCHNITT + RUTSCHEN_JE_ABSCHNITT
        if basis + 1 >= len(track.segments):
            break
        paare.append((track.segments[basis], track.segments[basis + 1]))
    return paare


def pruefe_durchlaesse(track: physics.Track,
                       clearance: float = MIN_GAP,
                       tore: int = TORE) -> list[str]:
    """Engstellen, in denen sich eine Kugel verkeilen kann."""
    maengel = physics.engstellen(track, clearance)

    # Das Tor selbst: es MUSS eng sein, aber nie enger als eine Kugel.
    for nummer, (a, b) in enumerate(tor_paare(track, tore), start=1):
        if a.y2 != b.y2:
            maengel.append(
                f"Tor {nummer}: die Trichterhaelften enden nicht auf gleicher "
                f"Hoehe ({a.y2:.0f} gegen {b.y2:.0f})")
            continue
        luecke = abs(b.x2 - a.x2) - a.radius - b.radius
        if luecke < clearance:
            maengel.append(
                f"Tor {nummer} bei y={a.y2:.0f}: nur {luecke:.0f} px lichte "
                f"Weite (Kugel ist {MARBLE_D:.0f} px)")
    return maengel


# ---------------------------------------------------------------------------
# Lauf und Annahme
# ---------------------------------------------------------------------------


def regel_kennung(seed: int, tore: int = TORE) -> str:
    """Fingerabdruck der Siegbedingung – fuer den Zwischenspeicher in B5.

    Die Kontrollpunkte gehoeren dazu: verschiebt sich einer, ist es ein
    anderes Rennen, auch wenn die Strecke gleich aussieht.
    """
    punkte = ",".join(f"{p:.3f}" for p in kontrollpunkte(tore))
    return f"{Elimination.name}:{punkte}"


def run(seed: int, tore: int = TORE) -> physics.RunResult:
    """Einen Lauf rechnen."""
    track = build_track(seed, tore)
    punkte = kontrollpunkte(tore)
    return physics.simulate(track, seed,
                            regel=Elimination(punkte, track.finish_y),
                            marks=punkte,
                            extras={"mark_label": "GATE"})


def check(result: physics.RunResult) -> list[str]:
    """Was gegen eine Veroeffentlichung spricht. Leere Liste = brauchbar."""
    probleme: list[str] = []
    n = len(theme.competitors())

    if result.duration < MIN_SECONDS:
        probleme.append(
            f"zu kurz: {result.duration:.1f}s "
            f"(Fenster {MIN_SECONDS:.0f}–{MAX_SECONDS:.0f}s)")
    if result.duration > MAX_SECONDS:
        probleme.append(
            f"zu lang: {result.duration:.1f}s "
            f"(Fenster {MIN_SECONDS:.0f}–{MAX_SECONDS:.0f}s)")

    if len(result.eliminated) != n - 1:
        probleme.append(
            f"{len(result.eliminated)} statt {n - 1} Ausscheidungen – "
            "das Format ist nicht aufgegangen")

    if not result.finished:
        probleme.append("der Ueberlebende hat das Ziel nicht erreicht")

    if len(result.hits) < 60:
        probleme.append(
            f"nur {len(result.hits)} Aufpraelle – die Tonspur bliebe leer")

    # Vier Ausscheidungen im Sekundentakt sind kein Spannungsbogen.
    zeiten = sorted(result.eliminated.values())
    for a, b in zip(zeiten, zeiten[1:]):
        if b - a < MIN_ABSTAND_TORE:
            probleme.append(
                f"zwei Ausscheidungen nur {b - a:.1f}s auseinander – "
                "die erste sieht niemand")
            break

    return probleme


def find_seeds(anzahl: int, start: int = 1,
               grenze: int = 400) -> list[tuple[int, physics.RunResult]]:
    """Sucht Seeds, die alle Annahmekriterien erfuellen."""
    treffer: list[tuple[int, physics.RunResult]] = []
    for seed in range(start, grenze):
        try:
            r = run(seed)
        except physics.SimulationError:
            continue
        if not check(r):
            treffer.append((seed, r))
            if len(treffer) >= anzahl:
                break
    return treffer


def fairness(laeufe: int = 60, start: int = 1) -> dict:
    """Misst, ob ein Startplatz strukturell im Vorteil ist."""
    from collections import Counter

    siege = Counter()
    zeiten: list[float] = []
    kaputt = 0
    seed = start
    gezaehlt = 0
    n = len(theme.competitors())

    while gezaehlt < laeufe and seed < start + laeufe * 6:
        try:
            track = build_track(seed)
            r = physics.simulate(track, seed,
                                 regel=Elimination(kontrollpunkte(),
                                                   track.finish_y),
                                 marks=kontrollpunkte(),
                                 max_seconds=SEARCH_CUTOFF)
        except physics.SimulationError:
            kaputt += 1
            seed += 1
            continue
        rng = random.Random(seed)
        plaetze = list(range(n))
        rng.shuffle(plaetze)
        siege[plaetze[r.winner]] += 1
        # Gemessen wird die ZIELZEIT des Ueberlebenden, nicht die Dauer des
        # Videos. Die Dauer ist auf ganze Bilder gerundet und vom festen
        # Nachlauf beschnitten – sie sieht dadurch gleichfoermiger aus, als
        # die Rennen sind, und haette hier faelschlich ein
        # Massenproduktions-Muster gemeldet.
        zeiten.append(round(min(r.finish_times.values(), default=r.duration), 3))
        gezaehlt += 1
        seed += 1

    groesster = max(siege.values()) if siege else 0
    return {
        "laeufe": gezaehlt,
        "kaputt": kaputt,
        "kaputt_anteil": kaputt / (gezaehlt + kaputt) if (gezaehlt + kaputt) else 0.0,
        "siege": {p: siege.get(p, 0) for p in range(n)},
        "erwartet": gezaehlt / n if gezaehlt else 0,
        "staerkster_anteil": groesster / gezaehlt if gezaehlt else 0.0,
        "verschiedene_zeiten": len(set(zeiten)),
        "zeit_spanne": (min(zeiten), max(zeiten)) if zeiten else (0, 0),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Einzeltest Disziplin 2")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tore", type=int, default=TORE)
    ap.add_argument("--json", help="Lauf als JSON speichern")
    ap.add_argument("--search", type=int, metavar="N",
                    help="N brauchbare Seeds suchen (ohne Ausgang)")
    ap.add_argument("--verraten", action="store_true",
                    help="bei --search auch den Ausgang zeigen. NICHT "
                         "benutzen, um einen Seed auszuwaehlen.")
    ap.add_argument("--fairness", type=int, metavar="N")
    ap.add_argument("--geometrie", type=int, metavar="N",
                    help="N Strecken auf Engstellen pruefen")
    a = ap.parse_args()

    if a.geometrie:
        print(f"Pruefe {a.geometrie} Strecken auf Engstellen "
              f"(< {MIN_GAP:.0f} px, Kugel ist {MARBLE_D:.0f} px) ...")
        schlecht = 0
        for seed in range(1, a.geometrie + 1):
            maengel = pruefe_durchlaesse(build_track(seed))
            if maengel:
                schlecht += 1
                print(f"  seed {seed}:")
                for m in maengel[:4]:
                    print(f"    - {m}")
        print()
        if schlecht:
            print(f"  ! {schlecht} von {a.geometrie} Strecken haben Engstellen.")
            return 1
        print(f"  in Ordnung: alle {a.geometrie} Strecken sind durchgaengig")
        return 0

    if a.fairness:
        print(f"Fairness ueber {a.fairness} Laeufe ...")
        f = fairness(a.fairness)
        print()
        track = build_track(1)
        for p, n in f["siege"].items():
            anteil = n / f["laeufe"] * 100 if f["laeufe"] else 0
            print(f"  Platz {p} x={track.starts[p][0]:4.0f}: {n:3d} Siege "
                  f"({anteil:4.1f} %)  {'#' * n}")
        print()
        print(f"  erwartet je Platz: {f['erwartet']:.1f} Siege (20 %)")
        print(f"  staerkster Platz:  {f['staerkster_anteil'] * 100:.1f} %")
        print(f"  verschiedene Zielzeiten: {f['verschiedene_zeiten']} "
              f"von {f['laeufe']}")
        print(f"  ohne Ergebnis verworfen: {f['kaputt']} "
              f"({f['kaputt_anteil'] * 100:.0f} % der Seeds)")
        print()
        if f["kaputt_anteil"] > 0.25:
            print("  ! Zu viele Seeds ohne Ergebnis – pruefen mit --geometrie 60.")
        elif f["staerkster_anteil"] > 0.30:
            print("  ! Ein Startplatz gewinnt zu oft.")
        else:
            print("  in Ordnung: kein Startplatz dominiert")
        return 0

    if a.search:
        print(f"Suche {a.search} brauchbare Seeds ...")
        gefunden = find_seeds(a.search)
        print()
        kopf = f"{'seed':>6}  {'dauer':>6}  {'tore':>4}  {'aufpraelle':>10}"
        if a.verraten:
            kopf += "  reihenfolge"
        print(kopf)
        for seed, r in gefunden:
            zeile = (f"{seed:>6}  {r.duration:>5.1f}s  "
                     f"{len(r.eliminated):>4}  {len(r.hits):>10}")
            if a.verraten:
                zeile += "  " + " > ".join(
                    theme.competitor(i).name for i in r.order)
            print(zeile)
        print()
        print(f"{len(gefunden)} von {a.search} gefunden")
        if not a.verraten:
            print("Der Ausgang steht hier bewusst nicht – sonst waere er "
                  "ausgesucht statt simuliert.")
        return 0

    r = run(a.seed, a.tore)
    print(r.summary())
    probleme = check(r)
    print()
    if probleme:
        print("NICHT veroeffentlichen:")
        for p in probleme:
            print(f"  - {p}")
    else:
        print("brauchbar: alle Annahmekriterien erfuellt")

    if a.json:
        physics.save(r, a.json)
        print(f"gespeichert: {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
