#!/usr/bin/env python3
"""
scatter.py – Disziplin 3: Streuung.

Ein Plinko-Brett. Fuenf Teilnehmer fallen durch ein Stiftfeld und landen in
einem Fach. Gewertet wird nach dem Punktwert des Fachs, nicht nach der Zeit.

Das ist die erste Disziplin, die **kein Rennen** ist. Damit ist sie auch die
erste, in der zwei Teilnehmer dasselbe Ergebnis erzielen koennen – der
Pruefbericht warnt genau davor: „die acht Disziplinen liefern strukturell
unvergleichbare Ergebnisse". Die Saisontabelle braucht aber eine
vollstaendige Rangfolge ueber fuenf Plaetze. Wie der Gleichstand aufgeloest
wird, steht bei `Streuung.rangfolge`.

CLI-Test:
  python -m gravitycup.disciplines.scatter --seed 1
  python -m gravitycup.disciplines.scatter --search 10
  python -m gravitycup.disciplines.scatter --geometrie 200
"""
from __future__ import annotations

import argparse
import random
import sys

from ..core import physics, theme

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NAME = "scatter"

HOOK = ("Where does it land?", "no aim, just gravity")

# ---------------------------------------------------------------------------
# Streckenform
# ---------------------------------------------------------------------------

WALL_LEFT, WALL_RIGHT = 40.0, 1040.0
SEG_RADIUS = theme.TRACK_WIDTH / 2
PEG_RADIUS = float(theme.PEG_RADIUS)

MARBLE_D = 2 * theme.MARBLE_RADIUS            # 64 px
MIN_GAP = MARBLE_D + 10                       # 74 px
CLEARANCE = MARBLE_D + 26                     # 90 px

START_Y = 150.0
START_SPACING = 78.0

#: Punktwerte der Faecher, von links nach rechts.
#:
#: SYMMETRISCH – und das ist keine Geschmacksfrage. Waeren die hohen Werte
#: auf einer Seite, haette die Bildseite einen dauerhaften Vorteil, und die
#: Tabelle maesse wieder die Auslosung statt den Lauf. Dieselbe Lehre wie
#: der gespiegelte Zickzack in B4.
#:
#: INNEN hoch, aussen niedrig – gegen die Erwartung, und zwar gemessen.
#:
#: Ein Plinko-Brett haeuft nur dann in der Mitte, wenn der Zufallslauf die
#: Waende nie erreicht. Bei 1080 px Breite und 62 Reihen erreicht er sie in
#: jedem Lauf, und eine reflektierende Wand kehrt die Verteilung um: die
#: Raender sind der HAEUFIGSTE Ausgang, die Mitte der seltenste.
#:
#: Die erste Fassung hatte die Werte andersherum, mit der Begruendung
#: „durch ein Stiftfeld faellt die Mitte am wahrscheinlichsten". Gemessen
#: landeten damit 31,7 % aller Kugeln in einem 50-Punkte-Fach und 6,6 % im
#: 3-Punkte-Fach: die Disziplin belohnte den haeufigsten Ausgang am
#: hoechsten und nannte ihn „Glueckstreffer".
#:
#: Statt das Brett gegen seine Physik zu biegen, folgen jetzt die Werte der
#: Messung. Belohnt wird, was selten ist – und was selten ist, steht in der
#: Tabelle in docs/baustein-b8.md.
#:
#: Symmetrisch bleibt es: waeren die hohen Werte auf einer Seite, haette
#: die Bildseite einen dauerhaften Vorteil. Dieselbe Lehre wie der
#: gespiegelte Zickzack in B4.
FACH_WERTE: tuple[int, ...] = (3, 6, 12, 24, 50, 24, 12, 6, 3)
FAECHER = len(FACH_WERTE)

#: Stiftfeld. Die Reihen versetzt wie beim echten Plinko-Brett.
#:
#: Die Zeilenzahl ist die Bremse: freier Fall durch ein Brett ist schnell,
#: jeder Aufprall kostet Tempo. Gemessen (siehe unten) braucht es rund 30
#: Reihen fuer das 20–38-Sekunden-Fenster. Die Zahl musste zweimal
#: nachgezogen werden, weil sich das Brett unter der Hand geaendert hat:
#: erst war jeder zweite Stift verworfen worden (durchlaessig, schnell),
#: nach der Reparatur steht das Raster vollstaendig (dicht, langsam).
#: Gemessen ueber je 60 Seeds mit dem heutigen Raster:
#:     62 Reihen  25–31 s, 100 % brauchbar   <- diese
#:     76 Reihen  30–37 s, 100 % brauchbar, zu nah an der 38-s-Grenze
STIFT_REIHEN = 62
#: Spalten in einer geraden Reihe, die beiden Wandspalten eingerechnet.
#:
#: Mehr Spalten heisst engeres Raster. Bei 9 Spalten bleiben 92 px lichte
#: Weite – eine Kugel ist 64, fuenf gleichzeitig verkeilen sich: 35 von 60
#: Seeds erreichten das Ziel nicht. Bei 7 Spalten sind es 132 px und 60 von
#: 60 Seeds laufen durch.
STIFT_SPALTEN = 7
#: Reihenabstand, je Seed gezogen. Feste Werte hiessen: jedes Brett gleich.
STIFT_REIHEN_ABSTAND = (138.0, 162.0)
STIFT_OBEN = 560.0

#: Mindestabstand ZWISCHEN zwei Stiften, als lichte Weite.
#:
#: NICHT CLEARANCE. Hier liegt der Unterschied zwischen einem Plinko-Brett
#: und einem Sieb: zwischen zwei Stiften soll eine Kugel durch, aber knapp.
#: Mit CLEARANCE (90) ergibt sich ein Rasterabstand von 2*14+90 = 118 px,
#: und bei sieben Spalten auf 714 px nutzbarer Breite betrug der Abstand
#: 119 – ein Pixel Reserve. Mit +-5 px Streuung fielen dadurch 66 bis 72 %
#: aller Stifte durch die Pruefung, die aeusserste Spalte in 0 von 2000
#: Seeds. Uebrig blieb an beiden Waenden ein senkrechter Kanal von im
#: Median 152 px – der alte Wandkanal, nur nach innen gewandert.
#:
#: Folge, gemessen ueber 600 Seeds: 31,7 % aller Kugeln landeten in einem
#: 50-Punkte-Fach, nur 6,6 % im 3-Punkte-Fach. Die Disziplin belohnte den
#: HAEUFIGSTEN Ausgang am hoechsten – das Gegenteil dessen, was der
#: Kommentar bei FACH_WERTE behauptet.
STIFT_ABSTAND = MIN_GAP                       # 74 px

#: Streuung jedes Stifts. Sie ersetzt die frueher zufaellige Rasterphase:
#: das Raster spannt jetzt von Wand zu Wand und darf nicht mehr wandern,
#: sonst entsteht am Rand wieder eine Luecke. Die Streuung sorgt dafuer,
#: dass trotzdem kein Brett dem anderen gleicht.
#: Grenze: Rasterabstand (120) minus zweimal Streuung muss ueber der
#: Verwerfungsschwelle 2*PEG_RADIUS + STIFT_ABSTAND (102) bleiben.
STIFT_STREUUNG = 6.0

#: Trennwaende der Faecher.
TRENNER_HOEHE = 300.0

#: Ein Lauf darf nur veroeffentlicht werden, wenn er hier hineinpasst.
MIN_SECONDS = 20.0
MAX_SECONDS = 38.0
SEARCH_CUTOFF = 46.0

#: Landen alle im selben Fach, gibt es nichts zu sehen und die Wertung
#: haengt vollstaendig an der Landezeit.
MAX_GLEICHES_FACH = 3

#: Wie lange nach der ersten Landung auf den Rest gewartet wird.
#:
#: `simulate` wartet standardmaessig 6 Sekunden – das passt zu einem Rennen,
#: bei dem alle ungefaehr gleich schnell unten sind. Auf einem 7500 px hohen
#: Plinko-Brett laufen die Landungen weit auseinander: mit 6 Sekunden endete
#: der Lauf, waehrend vier von fuenf Kugeln noch zehn Reihen ueber dem Boden
#: waren – gemessen an 18 von 40 Seeds. Sie galten dann als „nicht
#: gelandet", obwohl sie bloss noch unterwegs waren.
GEDULD = 22.0


# ---------------------------------------------------------------------------
# Die Siegbedingung
# ---------------------------------------------------------------------------


class Streuung(physics.Regel):
    """Gewertet wird das Landefach, nicht die Zeit."""

    name = "streuung"

    def __init__(self, wert_linie: float, kanten: list[float],
                 werte: tuple[int, ...] = FACH_WERTE):
        if len(kanten) != len(werte) + 1:
            raise ValueError(
                f"{len(werte)} Faecher brauchen {len(werte) + 1} Kanten, "
                f"bekommen {len(kanten)}")
        self.wert_linie = wert_linie
        self.kanten = list(kanten)
        self.werte = tuple(werte)

    def vorbereiten(self, count: int) -> None:
        super().vorbereiten(count)
        self.fach: dict[int, int] = {}

    def fach_von(self, x: float) -> int:
        """In welches Fach faellt diese x-Position?"""
        for k in range(len(self.werte)):
            if self.kanten[k] <= x < self.kanten[k + 1]:
                return k
        # Ausserhalb kann nur landen, wer an der Wand klebt – dann gilt das
        # aeussere Fach. Ein Fach ausserhalb der Liste gaebe es nicht, und
        # ein KeyError mitten im Lauf waere die schlechteste aller Antworten.
        return 0 if x < self.kanten[0] else len(self.werte) - 1

    def schritt(self, zeit_von: float, dt: float,
                y_vorher: list[float], y_jetzt: list[float],
                x_jetzt: list[float] | None = None) -> set[int]:
        for i in range(self.count):
            if i in self.zielzeiten:
                continue
            anteil = physics.linie_gequert(y_vorher[i], y_jetzt[i],
                                           self.wert_linie)
            if anteil is None:
                continue
            self.zielzeiten[i] = zeit_von + anteil * dt
            # Das Fach steht im Moment des Querens fest. Danach darf die
            # Kugel weiter huepfen, ohne dass sich die Wertung aendert –
            # sonst haenge das Ergebnis daran, wann die Simulation aufhoert.
            self.fach[i] = self.fach_von(x_jetzt[i] if x_jetzt else 0.0)
        return set()

    def wert(self, i: int) -> int:
        fach = self.fach.get(i)
        return self.werte[fach] if fach is not None else 0

    def rangfolge(self, letzte) -> list[int]:
        """Nach Punktwert, bei Gleichstand nach Landezeit.

        Zwei Kugeln im selben Fach sind keine Ausnahme, sondern der
        Normalfall – deshalb muss die zweite Stufe taugen. Genommen wird die
        LANDEZEIT: wer frueher unten war, hat den kuerzeren Weg gefunden.
        Das ist eine Tatsache des Laufs, keine Auslosung. Die Startnummer
        kommt hier so wenig vor wie beim Zieleinlauf in B2 – aus demselben
        Grund.

        Wer gar nicht ankommt (Notbremse), wird nach erreichter Tiefe
        gereiht und steht hinter allen Gelandeten.
        """
        gelandet = sorted(
            (i for i in range(self.count) if i in self.zielzeiten),
            key=lambda i: (-self.wert(i), self.zielzeiten[i]))
        rest = sorted((i for i in range(self.count) if i not in self.zielzeiten),
                      key=lambda i: -letzte[i][1])
        return gelandet + rest


# ---------------------------------------------------------------------------
# Geometrie
# ---------------------------------------------------------------------------


def fach_kanten(faecher: int | None = None) -> list[float]:
    """Die x-Grenzen der Faecher, inklusive der beiden Aussenkanten.

    `faecher=None` statt `faecher=FAECHER`: ein Modulwert als Vorgabewert
    wird beim IMPORT eingefroren. theme.py warnt an derselben Stelle vor
    demselben Fehler („nie COMPETITORS als Standardwert in eine Signatur").
    Aufgefallen ist es, weil ein Test die Fachzahl aenderte und die
    Geometriepruefung das nicht bemerkte.
    """
    faecher = FAECHER if faecher is None else faecher
    innen_links = WALL_LEFT + SEG_RADIUS
    innen_rechts = WALL_RIGHT - SEG_RADIUS
    breite = (innen_rechts - innen_links) / faecher
    return [innen_links + k * breite for k in range(faecher + 1)]


def wert_linie(reihen: int = STIFT_REIHEN) -> float:
    """Auf welcher Hoehe das Fach festgestellt wird.

    Knapp UNTER den Oberkanten der Trennwaende: dort ist die Kugel schon
    zwischen zwei Waenden und kann das Fach nicht mehr wechseln. Weiter
    oben gemessen haette sie noch ausweichen koennen, weiter unten muesste
    man warten, bis sie liegen bleibt – und „liegen bleiben" ist bei einer
    huepfenden Kugel keine saubere Bedingung.
    """
    return trenner_oben(reihen) + 90.0


def trenner_oben(reihen: int = STIFT_REIHEN) -> float:
    """Oberkante der Trennwaende."""
    return STIFT_OBEN + (reihen - 1) * max(STIFT_REIHEN_ABSTAND) + 190.0


def build_track(seed: int, reihen: int = STIFT_REIHEN) -> physics.Track:
    """Die Strecke einer Runde. Gleicher Seed, gleiche Strecke."""
    rng = random.Random(seed * 61 + 17)
    segments: list[physics.Segment] = []
    pegs: list[physics.Peg] = []
    mitte = theme.WIDTH / 2

    oben_trenner = trenner_oben(reihen)
    boden = oben_trenner + TRENNER_HOEHE
    finish_y = wert_linie(reihen)

    wand_links = physics.Segment(WALL_LEFT, 0, WALL_LEFT, boden + 40, SEG_RADIUS)
    wand_rechts = physics.Segment(WALL_RIGHT, 0, WALL_RIGHT, boden + 40, SEG_RADIUS)

    # --- Trennwaende und Boden -------------------------------------------
    kanten = fach_kanten()
    for x in kanten[1:-1]:
        segments.append(physics.Segment(x, oben_trenner, x, boden, SEG_RADIUS))
    segments.append(physics.Segment(WALL_LEFT, boden, WALL_RIGHT, boden,
                                    SEG_RADIUS))
    segments.append(wand_links)
    segments.append(wand_rechts)

    # --- Stiftfeld --------------------------------------------------------
    # Die AEUSSERSTEN Spalten sind Teil des Rasters und ueberlappen die Wand.
    #
    # Zwei Anlaeufe sind vorher gescheitert, beide an derselben Sache: das
    # Raster hielt Abstand zur Wand, und in dem Abstand blieb ein
    # senkrechter Kanal. Erst lag er zwischen Wand und Feld (126 px), dann –
    # nach dem Einbau separater Wandstifte – zwischen Wandstift und erster
    # Rasterspalte (114 px). Beide Male fiel eine Kugel dort ungebremst
    # durch, und beide Male war die Fachverteilung U-foermig statt
    # glockenfoermig: 31 bis 33 % aller Kugeln in einem 50-Punkte-Fach,
    # 6,6 % in der Mitte. Die Disziplin belohnte damit den HAEUFIGSTEN
    # Ausgang am hoechsten.
    #
    # Jetzt spannt das Raster von Wand zu Wand. Es gibt keinen Abstand mehr,
    # in dem ein Kanal entstehen koennte.
    spalte_links = WALL_LEFT + SEG_RADIUS + PEG_RADIUS - 4
    spalte_rechts = WALL_RIGHT - SEG_RADIUS - PEG_RADIUS + 4
    schritt = (spalte_rechts - spalte_links) / (STIFT_SPALTEN - 1)

    # Die versetzten Reihen haben KEINEN Wandstift und muessen deshalb
    # selbst Abstand zur Wand halten. Bei einem glatten halben Schritt blieb
    # rechts nur 72 px lichte Weite – unter MIN_GAP, also nach den eigenen
    # Regeln eine Falle. Sie spannen daher ueber ein eigenes, engeres Feld.
    innen_links = (WALL_LEFT + SEG_RADIUS + PEG_RADIUS
                   + STIFT_STREUUNG + MIN_GAP)
    innen_rechts = (WALL_RIGHT - SEG_RADIUS - PEG_RADIUS
                    - STIFT_STREUUNG - MIN_GAP)

    # Das Raster steht fest an den Waenden – es darf nicht mehr wandern,
    # sonst entsteht dort wieder eine Luecke. Damit trotzdem kein Brett dem
    # anderen gleicht, schwanken der REIHENABSTAND und die Lage der
    # versetzten Reihen mit dem Seed. Ohne das lag Startplatz 1 in jedem
    # Lauf auf derselben Spalte: 24,8 % Siege, Chi-Quadrat 10,1.
    reihen_abstand = rng.uniform(*STIFT_REIHEN_ABSTAND)

    for reihe in range(reihen):
        y = STIFT_OBEN + reihe * reihen_abstand
        if reihe % 2 == 0:
            xs = [spalte_links + k * schritt for k in range(STIFT_SPALTEN)]
        else:
            # Versetzte Reihe: ein halber Schritt, eine Spalte weniger. Die
            # aeusseren beiden bleiben innerhalb des engeren Feldes, damit
            # zur Wand MIN_GAP bleibt – ohne Wandstift ist das hier eine
            # Stelle, durch die eine Kugel MUSS.
            xs = [min(max(spalte_links + (k + 0.5) * schritt, innen_links),
                      innen_rechts)
                  for k in range(STIFT_SPALTEN - 1)]
        for k, x in enumerate(xs):
            # Die Randspalten der geraden Reihen sind Teil der WAND. Sie
            # bekommen deshalb keine seitliche Streuung – eine, die sie von
            # der Wand wegschiebt, oeffnet genau den Spalt, den sie
            # schliessen sollen (gemessen: 0 px lichte Weite, also eine
            # Klemmstelle statt einer Dichtung).
            am_rand = reihe % 2 == 0 and k in (0, len(xs) - 1)
            px = x if am_rand else x + rng.uniform(-STIFT_STREUUNG,
                                                   STIFT_STREUUNG)
            pegs.append(physics.Peg(px,
                                    y + rng.uniform(-STIFT_STREUUNG,
                                                    STIFT_STREUUNG),
                                    PEG_RADIUS))

    starts = [(mitte + (i - 2) * START_SPACING, START_Y)
              for i in range(len(theme.competitors()))]

    return physics.Track(segments=segments, pegs=pegs, starts=starts,
                         finish_y=finish_y, name=f"{NAME}-{reihen}")


def pruefe_durchlaesse(track: physics.Track,
                       clearance: float = MIN_GAP) -> list[str]:
    """Engstellen, in denen sich eine Kugel verkeilen kann."""
    maengel = physics.engstellen(track, clearance)

    # Die Faecher: jedes muss eine Kugel aufnehmen koennen.
    kanten = fach_kanten()
    for k in range(len(kanten) - 1):
        luecke = (kanten[k + 1] - kanten[k]) - 2 * SEG_RADIUS
        if luecke < clearance:
            maengel.append(
                f"Fach {k + 1}: nur {luecke:.0f} px lichte Weite "
                f"(Kugel ist {MARBLE_D:.0f} px)")
    return maengel


# ---------------------------------------------------------------------------
# Lauf und Annahme
# ---------------------------------------------------------------------------


def regel_kennung(seed: int, reihen: int = STIFT_REIHEN) -> str:
    """Fingerabdruck der Siegbedingung – fuer den Zwischenspeicher in B5."""
    werte = "-".join(str(w) for w in FACH_WERTE)
    return f"{Streuung.name}:{wert_linie(reihen):.3f}:{werte}"


def _regel(reihen: int = STIFT_REIHEN) -> Streuung:
    return Streuung(wert_linie(reihen), fach_kanten(), FACH_WERTE)


def run(seed: int, reihen: int = STIFT_REIHEN) -> physics.RunResult:
    """Einen Lauf rechnen."""
    track = build_track(seed, reihen)
    regel = _regel(reihen)
    r = physics.simulate(track, seed, regel=regel, marks=[wert_linie(reihen)],
                         patience_seconds=GEDULD)
    # Erst rechnen, DANN die Faecher anhaengen. Als Argument an `simulate`
    # waeren sie ausgewertet worden, bevor ueberhaupt eine Kugel gefallen
    # ist – und `regel.fach` waere leer gewesen.
    kanten = fach_kanten()
    r.extras = {
        "faecher": [[kanten[k], kanten[k + 1], FACH_WERTE[k]]
                    for k in range(FAECHER)],
        "punkte": {str(i): regel.wert(i)
                   for i in range(len(theme.competitors()))},
        "fach": {str(i): f for i, f in regel.fach.items()},
    }
    return r


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

    if len(result.finished) < n:
        fehlend = [theme.competitor(i).name
                   for i in range(n) if i not in result.finished]
        probleme.append(f"nicht gelandet: {', '.join(fehlend)}")

    if len(result.hits) < 60:
        probleme.append(
            f"nur {len(result.hits)} Aufpraelle – die Tonspur bliebe leer")

    faecher = (result.extras or {}).get("fach") or {}
    if faecher:
        from collections import Counter
        haeufig = Counter(faecher.values()).most_common(1)[0][1]
        if haeufig > MAX_GLEICHES_FACH:
            probleme.append(
                f"{haeufig} von {n} landen im selben Fach – die Wertung "
                "haengt dann fast nur an der Landezeit")

    return probleme


def find_seeds(anzahl: int, start: int = 1,
               grenze: int = 400) -> list[tuple[int, physics.RunResult]]:
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
    werte: list[float] = []
    kaputt = 0
    seed = start
    gezaehlt = 0
    n = len(theme.competitors())

    while gezaehlt < laeufe and seed < start + laeufe * 6:
        try:
            r = physics.simulate(build_track(seed), seed, regel=_regel(),
                                 patience_seconds=GEDULD,
                                 max_seconds=SEARCH_CUTOFF)
        except physics.SimulationError:
            kaputt += 1
            seed += 1
            continue
        rng = random.Random(seed)
        plaetze = list(range(n))
        rng.shuffle(plaetze)
        siege[plaetze[r.winner]] += 1
        werte.append(round(min(r.finish_times.values(), default=r.duration), 3))
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
        "verschiedene_zeiten": len(set(werte)),
        "zeit_spanne": (min(werte), max(werte)) if werte else (0, 0),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Einzeltest Disziplin 3")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--reihen", type=int, default=STIFT_REIHEN)
    ap.add_argument("--json")
    ap.add_argument("--search", type=int, metavar="N",
                    help="N brauchbare Seeds suchen (ohne Ausgang)")
    ap.add_argument("--verraten", action="store_true")
    ap.add_argument("--fairness", type=int, metavar="N")
    ap.add_argument("--geometrie", type=int, metavar="N")
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
        stat = physics.startplatz_statistik(f["siege"])
        print(f"  erwartet je Platz: {f['erwartet']:.1f} Siege (20 %)")
        print(f"  staerkster Platz:  {f['staerkster_anteil'] * 100:.1f} %"
              f"   – durch Zufall allein waeren bei {stat['laeufe']} Laeufen"
              f" {stat['zufall_typisch'] * 100:.1f} % typisch,"
              f" bis {stat['zufall_grenze'] * 100:.1f} % unauffaellig")
        print(f"  Chi-Quadrat:       {stat['chi2']:.2f}  (p={stat['p']:.3f}, "
              f"Cramers V {stat['cramers_v']:.3f})  – waechst mit der Laufzahl")
        print(f"  verschiedene Landezeiten: {f['verschiedene_zeiten']} "
              f"von {f['laeufe']}")
        print(f"  ohne Ergebnis verworfen: {f['kaputt']}")
        print()
        ok, grund = physics.fairness_urteil(stat)
        if not ok:
            print(f"  ! {grund}.")
        else:
            print(f"  in Ordnung: {grund}")
        return 0

    if a.search:
        print(f"Suche {a.search} brauchbare Seeds ...")
        gefunden = find_seeds(a.search)
        print()
        kopf = f"{'seed':>6}  {'dauer':>6}  {'gelandet':>8}  {'aufpraelle':>10}"
        if a.verraten:
            kopf += "  faecher            reihenfolge"
        print(kopf)
        for seed, r in gefunden:
            zeile = (f"{seed:>6}  {r.duration:>5.1f}s  "
                     f"{len(r.finished):>4}/{len(theme.competitors())}  "
                     f"{len(r.hits):>10}")
            if a.verraten:
                punkte = (r.extras or {}).get("punkte", {})
                zeile += "  " + " ".join(
                    f"{punkte.get(str(i), 0):>3}" for i in range(5))
                zeile += "  " + " > ".join(
                    theme.competitor(i).name for i in r.order)
            print(zeile)
        print()
        print(f"{len(gefunden)} von {a.search} gefunden")
        if not a.verraten:
            print("Der Ausgang steht hier bewusst nicht – sonst waere er "
                  "ausgesucht statt simuliert.")
        return 0

    r = run(a.seed, a.reihen)
    print(r.summary())
    punkte = (r.extras or {}).get("punkte", {})
    fach = (r.extras or {}).get("fach", {})
    print("faecher=" + ", ".join(
        f"{theme.competitor(i).name} Fach {fach.get(str(i), -1) + 1} "
        f"= {punkte.get(str(i), 0)}"
        for i in r.order))
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
