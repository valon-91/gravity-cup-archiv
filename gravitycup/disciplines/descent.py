#!/usr/bin/env python3
"""
descent.py – Disziplin 1: Sturzrennen.

Fünf Teilnehmer fallen über eine Zickzack-Strecke nach unten, wer zuerst
durch die Ziellinie geht, gewinnt. Die einfachste Disziplin und der
Massstab fuer alle weiteren.

Diese Datei liefert NUR die Geometrie und die Annahmekriterien. Physik,
Kollisionsprotokoll und Rangfolge stehen in core/physics.py.

CLI-Test:
  python -m gravitycup.disciplines.descent --seed 2
  python -m gravitycup.disciplines.descent --search 40    # brauchbare Seeds suchen
"""
from __future__ import annotations

import argparse
import math
import random
import sys

from ..core import physics, theme

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NAME = "descent"

#: Aufhaenger der ersten Sekunden. Englisch, weil der Kanal international ist.
HOOK = ("Which color wins?", "real physics, no cuts")

# ---------------------------------------------------------------------------
# Streckenform
# ---------------------------------------------------------------------------

WALL_LEFT, WALL_RIGHT = 40.0, 1040.0
RAMP_COUNT = 10
RAMP_GAP = 430.0          # senkrechter Abstand zweier Rampenanfaenge
PEGS_PER_RAMP = 3
#: Stiftgroesse kommt aus der Gestaltung, damit Bild und Physik denselben
#: Stift meinen. Waeren sie verschieden, prallte die Kugel im Video sichtbar
#: neben dem Stift ab.
PEG_RADIUS = float(theme.PEG_RADIUS)
SEG_RADIUS = theme.TRACK_WIDTH / 2   # Dicke der Strecke, physics.Segment.radius
START_Y = 150.0
START_SPACING = 78.0

#: DIE beiden wichtigsten Zahlen dieser Datei – beide als lichte Weite,
#: also ohne die Dicke der Begrenzung.
#:
#: Vorher endeten Rampen bis x=1000, die Wand steht bei x=1040. Zwischen
#: Rampenende und Wand blieben 36 px lichte Weite; eine Kugel ist 64 px
#: dick. Die erste Kugel verkeilte sich dort, die anderen vier stauten sich
#: dahinter, und der Lauf stand still: 281 von 300 Seeds erreichten das Ziel
#: nie. Es war NICHT die Reibung – eine einzelne Kugel rollt auch auf 18 %
#: Neigung sauber durch (nachgemessen). Es war immer diese eine Engstelle.
MARBLE_D = 2 * theme.MARBLE_RADIUS            # 64 px

#: Ausschlusskriterium. Enger als das passt keine Kugel mehr sauber
#: hindurch – solche Stellen sind Fallen. `pruefe_durchlaesse` sucht danach.
MIN_GAP = MARBLE_D + 10                       # 74 px

#: Zielwert beim Setzen. Gewuerfelte Stifte halten diesen groesseren
#: Abstand, damit Rundungen und Streuung nicht bis an MIN_GAP heranreichen.
CLEARANCE = MARBLE_D + 26                     # 90 px

#: Rampen schwanken mit dem Seed. Feste Rampen hiessen: jedes Rennen laeuft
#: gleich ab, nur die Farben tauschen die Plaetze – gemessen 3 verschiedene
#: Zielzeiten in 57 Laeufen. Das ist genau das Massenproduktions-Muster,
#: vor dem die Roadmap warnt.
#: Gewuerfelt wird die NEIGUNG, nicht das Gefaelle: beides unabhaengig zu
#: ziehen ergab bei langem Weg und kleinem Gefaelle fast waagerechte Rampen.
RAMP_SLOPE_RANGE = (0.30, 0.48)

#: Wo eine Rampe tief auslaufen darf. Die Obergrenze ist keine gewaehlte
#: Zahl, sondern CLEARANCE: hinter dem Rampenende muss eine Kugel zwischen
#: Rampe und Wand hindurchfallen koennen.
RAMP_END_MIN = 600.0
RAMP_END_MAX = WALL_RIGHT - SEG_RADIUS - CLEARANCE - SEG_RADIUS   # 932.0
RAMP_END_RANGE = (RAMP_END_MIN, RAMP_END_MAX)

#: Gefaelle darf nie so gross werden, dass zwei Rampen einander schneiden.
RAMP_DROP_MAX = RAMP_GAP - 90.0

#: Der Zickzack wird pro Seed GESPIEGELT. Faellt die erste Rampe immer nach
#: rechts, trifft der rechte Startplatz sie weiter unten, rollt kuerzer und
#: liegt sofort vorn – dieser Vorsprung haelt ueber alle zehn Rampen.
#: Gemessen ueber 300 Laeufe: ohne Spiegelung gewinnt der staerkste Platz
#: 32,8 %, mit Spiegelung 24,0 % (Erwartung 20 %, Rauschen +-2,3 %).
MIRROR_ZIGZAG = True

#: Mischzone gleich nach dem Start: versetzte Stiftreihen wie beim
#: Plinko-Brett. Sie entwertet den Startplatz nur schwach (24,3 % ohne,
#: 24,0 % mit), liefert aber die ersten Aufpraelle fuer die Tonspur und
#: streut das Feld, bevor die erste Rampe kommt.
#: Dichter darf sie NICHT werden: fuenf gleichzeitig fallende Kugeln
#: verklemmen sich dann gegenseitig – bei 7 Reihen x 6 Stiften erreichten
#: nur noch 26 % der Laeufe ein brauchbares Ergebnis.
MIX_ROWS = 5
MIX_TOP = 300.0
MIX_ROW_GAP = 78.0
MIX_PER_ROW = 5
MIX_PEG_RADIUS = PEG_RADIUS

#: Ein Lauf darf nur veroeffentlicht werden, wenn er hier hineinpasst.
#: Die Roadmap will 25–40 s je Short; unter 20 s wirkt es abgehackt,
#: ueber 38 s wird es fuer die Bindung zu lang.
MIN_SECONDS = 20.0
MAX_SECONDS = 38.0

#: Beim Durchsuchen vieler Seeds wird frueher abgebrochen – ein Lauf, der
#: laenger braucht, ist ohnehin unbrauchbar, und die volle Notbremse von
#: 60 s macht die Suche unnoetig langsam.
SEARCH_CUTOFF = 44.0


def spiegel_x(x: float) -> float:
    """Punkt an der Mittelachse spiegeln. Wand bleibt Wand."""
    return WALL_LEFT + WALL_RIGHT - x


#: Beide Helfer stehen seit B7 in physics.py – die Eliminierung braucht
#: dieselbe Regel. Hier bleiben die vertrauten Namen stehen.
abstand_zu_segment = physics.abstand_zu_segment


def passt_durch(x: float, y: float, radius: float,
                segments, pegs, clearance: float = CLEARANCE) -> bool:
    """Bleibt neben einem Hindernis an dieser Stelle Platz fuer eine Kugel?"""
    return physics.passt_durch(x, y, radius, segments, pegs, clearance)


def build_track(seed: int, ramps: int = RAMP_COUNT) -> physics.Track:
    """Die Strecke einer Runde. Gleicher Seed, gleiche Strecke."""
    rng = random.Random(seed * 31 + 5)
    segments: list[physics.Segment] = []
    pegs: list[physics.Peg] = []
    mitte = theme.WIDTH / 2

    # Der ganze Zickzack wird pro Seed gespiegelt oder nicht – siehe
    # MIRROR_ZIGZAG. Das ist der Unterschied zwischen 32,8 % und 24,0 %.
    gespiegelt = MIRROR_ZIGZAG and rng.random() < 0.5

    top = 700.0
    bottom = top + ramps * RAMP_GAP + 120
    finish_y = bottom + 400

    # --- Begrenzung ------------------------------------------------------
    # Seitenwaende zuerst, damit die Stiftpruefung sie schon kennt.
    wand_links = physics.Segment(WALL_LEFT, 0, WALL_LEFT, finish_y + 160,
                                 SEG_RADIUS)
    wand_rechts = physics.Segment(WALL_RIGHT, 0, WALL_RIGHT, finish_y + 160,
                                  SEG_RADIUS)

    # --- Rampen ---------------------------------------------------------
    # Rampenanfang sitzt bewusst DICHT an der Wand (2 px lichte Weite):
    # dort soll keine Kugel vorbei. Das Rampenende laesst dafuer genau
    # CLEARANCE zur gegenueberliegenden Wand – dort muss jede Kugel vorbei.
    for i in range(ramps):
        y = top + i * RAMP_GAP
        ende = rng.uniform(*RAMP_END_RANGE)
        nach_rechts = (i % 2 == 0) != gespiegelt
        if nach_rechts:
            x_von, x_bis = WALL_LEFT + 20, ende
        else:
            x_von, x_bis = spiegel_x(WALL_LEFT + 20), spiegel_x(ende)
        drop = min(abs(x_bis - x_von) * rng.uniform(*RAMP_SLOPE_RANGE),
                   RAMP_DROP_MAX)
        segments.append(physics.Segment(x_von, y, x_bis, y + drop, SEG_RADIUS))

    # Trichter ins Ziel: buendelt das Feld, damit der Zieleinlauf eng wird
    segments.append(physics.Segment(WALL_LEFT + 20, bottom,
                                    mitte - 150, bottom + 260, SEG_RADIUS))
    segments.append(physics.Segment(WALL_RIGHT - 20, bottom,
                                    mitte + 150, bottom + 260, SEG_RADIUS))
    # Auffangbecken, damit niemand aus dem Bild faellt
    segments.append(physics.Segment(WALL_LEFT, finish_y + 150,
                                    WALL_RIGHT, finish_y + 150, SEG_RADIUS))
    segments.append(wand_links)
    segments.append(wand_rechts)

    # --- Mischzone: streut das Feld vor der ersten Rampe -----------------
    # Versetzte Stiftreihen wie beim Plinko-Brett. Das Raster bekommt pro
    # Seed eine zufaellige Phase: bei festem Raster stand der mittlere
    # Startplatz immer genau ueber einer Stiftspalte und die Nachbarn immer
    # in der Luecke – gemessen 7 % Siege gegen 33 %.
    links = WALL_LEFT + SEG_RADIUS + CLEARANCE + MIX_PEG_RADIUS
    rechts = WALL_RIGHT - SEG_RADIUS - CLEARANCE - MIX_PEG_RADIUS
    schritt = (rechts - links) / (MIX_PER_ROW - 1) if MIX_PER_ROW > 1 else 0.0
    phase = rng.uniform(-schritt / 2, schritt / 2)
    for reihe in range(MIX_ROWS):
        y = MIX_TOP + reihe * MIX_ROW_GAP
        versatz = schritt / 2 if reihe % 2 else 0.0
        for k in range(-1, MIX_PER_ROW + 1):
            x = links + phase + versatz + k * schritt
            if not links <= x <= rechts:
                continue
            # Streuung bewusst klein: die Reihen stehen diagonal nur
            # ~124 px auseinander, davon gehen 2x15 px Stift ab. Groessere
            # Streuung druecken einzelne Paare unter MIN_GAP.
            pegs.append(physics.Peg(x + rng.uniform(-4, 4),
                                    y + rng.uniform(-4, 4),
                                    MIX_PEG_RADIUS))

    # --- Stifte im freien Fall zwischen den Rampen -----------------------
    # Gewuerfelt und verworfen, bis sie frei stehen. Frueher wurden sie
    # blind gesetzt und landeten auch mal direkt auf der naechsten Rampe.
    for i in range(ramps):
        y_band = top + i * RAMP_GAP + RAMP_GAP * 0.5
        gesetzt = 0
        for _ in range(60):
            if gesetzt >= PEGS_PER_RAMP:
                break
            kx = rng.uniform(200, 880)
            ky = y_band + rng.uniform(-60, 160)
            if passt_durch(kx, ky, PEG_RADIUS, segments, pegs):
                pegs.append(physics.Peg(kx, ky, PEG_RADIUS))
                gesetzt += 1

    # Startplaetze: alle auf gleicher Hoehe, mittig verteilt.
    # Wer welchen bekommt, verlost physics.simulate() aus dem Seed.
    starts = [
        (mitte + (i - 2) * START_SPACING, START_Y)
        for i in range(len(theme.competitors()))
    ]

    return physics.Track(segments=segments, pegs=pegs, starts=starts,
                         finish_y=finish_y, name=f"{NAME}-{ramps}")


def pruefe_durchlaesse(track: physics.Track,
                       clearance: float = MIN_GAP) -> list[str]:
    """Findet Engstellen, in denen sich eine Kugel verkeilen kann.

    Diese Pruefung ist der Ersatz fuer „ist ja bisher gutgegangen". Sie
    haette den Fehler gefunden, an dem 94 % aller Laeufe hingen.
    """
    maengel: list[str] = []

    for i, p in enumerate(track.pegs):
        for s in track.segments:
            d = abstand_zu_segment(p.x, p.y, s)
            luecke = d - p.radius - s.radius
            if 0.0 < luecke < clearance:
                maengel.append(
                    f"Stift {i} bei ({p.x:.0f},{p.y:.0f}): nur {luecke:.0f} px "
                    f"zum Segment ({s.x1:.0f},{s.y1:.0f})-({s.x2:.0f},{s.y2:.0f})")
        for j, q in enumerate(track.pegs[i + 1:], start=i + 1):
            luecke = math.hypot(p.x - q.x, p.y - q.y) - p.radius - q.radius
            if 0.0 < luecke < clearance:
                maengel.append(
                    f"Stifte {i}/{j}: nur {luecke:.0f} px Durchlass")

    # Rampenende gegen die gegenueberliegende Wand – der urspruengliche Fehler
    for s in track.segments:
        if s.y1 == s.y2 or s.x1 == s.x2:
            continue                      # Wand, Boden: kein Rampenende
        x_ende = s.x2 if s.y2 > s.y1 else s.x1
        rechts = (WALL_RIGHT - SEG_RADIUS) - (x_ende + s.radius)
        links = (x_ende - s.radius) - (WALL_LEFT + SEG_RADIUS)
        luecke = rechts if abs(rechts) < abs(links) else links
        if 0.0 < luecke < clearance:
            maengel.append(
                f"Rampenende bei x={x_ende:.0f}: nur {luecke:.0f} px zur Wand")

    return maengel


def regel_kennung(seed: int, ramps: int = RAMP_COUNT) -> str:
    """Fingerabdruck der Siegbedingung – fuer den Zwischenspeicher in B5."""
    return f"{physics.RaceToLine.name}:{build_track(seed, ramps).finish_y:.3f}"


def run(seed: int, ramps: int = RAMP_COUNT) -> physics.RunResult:
    """Einen Lauf rechnen."""
    return physics.simulate(build_track(seed, ramps), seed)


def check(result: physics.RunResult) -> list[str]:
    """Was gegen eine Veroeffentlichung spricht. Leere Liste = brauchbar.

    Die Roadmap nennt ein Laengenfenster, prueft es aber nirgends – ein Lauf,
    der 52 Sekunden dauert oder bei dem drei Teilnehmer haengenbleiben, waere
    sonst unbemerkt hochgeladen worden.
    """
    probleme: list[str] = []

    if result.duration < MIN_SECONDS:
        probleme.append(
            f"zu kurz: {result.duration:.1f}s (Fenster {MIN_SECONDS:.0f}–{MAX_SECONDS:.0f}s)")
    if result.duration > MAX_SECONDS:
        probleme.append(
            f"zu lang: {result.duration:.1f}s (Fenster {MIN_SECONDS:.0f}–{MAX_SECONDS:.0f}s)")

    if len(result.finished) < len(theme.competitors()):
        fehlend = [theme.competitor(i).name
                   for i in range(len(theme.competitors()))
                   if i not in result.finished]
        probleme.append(
            f"nicht im Ziel: {', '.join(fehlend)} – Rennen wirkt unfertig")

    if len(result.hits) < 60:
        probleme.append(
            f"nur {len(result.hits)} Aufpraelle – die Tonspur bliebe leer")

    # Ein Rennen, das nach zwei Sekunden entschieden ist, taugt nicht.
    if len(result.finished) >= 2:
        zeiten = sorted(result.finish_times.values())
        vorsprung = zeiten[1] - zeiten[0]
        if vorsprung > 6.0:
            probleme.append(
                f"Sieger {vorsprung:.1f}s vor dem Zweiten – kein Spannungsbogen")

    return probleme


def fairness(laeufe: int = 60, start: int = 1) -> dict:
    """Misst, ob ein Startplatz strukturell im Vorteil ist.

    Muss VOR jedem Saisonstart laufen. Gewinnt ein Platz deutlich oefter als
    die anderen, ist das Rennen vor dem Start entschieden und die
    Saisontabelle misst nur noch die Auslosung – gemessen wurde genau das:
    96,5 % Siege fuer den rechten Platz, als der Zickzack noch fest war.

    Was „deutlich" heisst, haengt an der Stichprobe: bei 5 Plaetzen und N
    Laeufen liegt der staerkste Platz auch bei perfekt fairer Strecke im
    Mittel ueber 20 %. Bei N=300 ist eine Standardabweichung 2,3 %, der
    Erwartungswert des Maximums rund 24 %. Darum die Grenze bei 30 %.
    """
    from collections import Counter

    siege = Counter()
    zeiten: list[float] = []
    kaputt = 0
    seed = start
    gezaehlt = 0

    while gezaehlt < laeufe and seed < start + laeufe * 6:
        try:
            r = physics.simulate(build_track(seed), seed,
                                 max_seconds=SEARCH_CUTOFF)
        except physics.SimulationError:
            kaputt += 1
            seed += 1
            continue
        rng = random.Random(seed)
        plaetze = list(range(len(theme.competitors())))
        rng.shuffle(plaetze)
        siege[plaetze[r.winner]] += 1
        zeiten.append(round(min(r.finish_times.values()), 3))
        gezaehlt += 1
        seed += 1

    n = len(theme.competitors())
    erwartet = gezaehlt / n if gezaehlt else 0
    groesster = max(siege.values()) if siege else 0
    return {
        "laeufe": gezaehlt,
        "kaputt": kaputt,
        "kaputt_anteil": kaputt / (gezaehlt + kaputt) if (gezaehlt + kaputt) else 0.0,
        "siege": {p: siege.get(p, 0) for p in range(n)},
        "erwartet": erwartet,
        "staerkster_anteil": groesster / gezaehlt if gezaehlt else 0.0,
        "verschiedene_zeiten": len(set(zeiten)),
        "zeit_spanne": (min(zeiten), max(zeiten)) if zeiten else (0, 0),
    }


def find_seeds(anzahl: int, start: int = 1, grenze: int = 400) -> list[tuple[int, physics.RunResult]]:
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Einzeltest Disziplin 1")
    ap.add_argument("--seed", type=int, default=2)
    ap.add_argument("--ramps", type=int, default=RAMP_COUNT)
    ap.add_argument("--json", help="Lauf als JSON speichern")
    ap.add_argument("--search", type=int, metavar="N",
                    help="N brauchbare Seeds suchen und auflisten (ohne Ausgang)")
    ap.add_argument("--verraten", action="store_true",
                    help="bei --search auch Sieger und Reihenfolge zeigen. "
                         "NICHT benutzen, um einen Seed auszuwaehlen.")
    ap.add_argument("--fairness", type=int, metavar="N",
                    help="ueber N Laeufe pruefen, ob ein Startplatz bevorzugt ist")
    ap.add_argument("--geometrie", type=int, metavar="N",
                    help="N Strecken auf Engstellen pruefen (ohne zu rechnen)")
    a = ap.parse_args()

    if a.geometrie:
        print(f"Pruefe {a.geometrie} Strecken auf Engstellen "
              f"(< {MIN_GAP:.0f} px lichte Weite, Kugel ist {MARBLE_D:.0f} px) ...")
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
            print(f"  ! {schlecht} von {a.geometrie} Strecken haben Engstellen, "
                  f"in denen sich Kugeln verkeilen.")
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
              f"von {f['laeufe']}  "
              f"({f['zeit_spanne'][0]:.1f}s .. {f['zeit_spanne'][1]:.1f}s)")
        print(f"  ohne Zieleinlauf verworfen: {f['kaputt']} "
              f"({f['kaputt_anteil'] * 100:.0f} % der Seeds)")
        print()
        if f["kaputt_anteil"] > 0.25:
            print("  ! Zu viele Seeds erreichen das Ziel nie – irgendwo klemmt")
            print("    das Feld. Pruefen mit --geometrie 60.")
        elif f["staerkster_anteil"] > 0.30:
            print("  ! Ein Startplatz gewinnt zu oft – das Rennen ist vor dem")
            print("    Start entschieden. Strecke aendern, nicht veroeffentlichen.")
        elif f["verschiedene_zeiten"] < f["laeufe"] * 0.5:
            print("  ! Zu wenige verschiedene Zielzeiten – die Laeufe aehneln")
            print("    sich zu stark (Massenproduktions-Muster).")
        else:
            print("  in Ordnung: kein Startplatz dominiert, Laeufe unterscheiden sich")
        return 0

    if a.search:
        # Der Ausgang wird hier NICHT angezeigt.
        #
        # Wer sich aus einer Liste den Seed aussucht, bei dem die Lieblings-
        # farbe gewinnt, hat den Ausgang geschrieben und nicht simuliert –
        # und damit genau das Versprechen gebrochen, mit dem der Kanal
        # antritt. Angezeigt wird nur, was ueber die BRAUCHBARKEIT
        # entscheidet: Dauer, Zieleinlaeufe, Aufpraelle, Abstand an der
        # Spitze. Wer den Ausgang danach sehen will, nimmt --verraten oder
        # baut das Video – dann steht der Seed schon fest.
        print(f"Suche {a.search} brauchbare Seeds "
              f"({MIN_SECONDS:.0f}–{MAX_SECONDS:.0f}s, alle im Ziel, Spannung) ...")
        gefunden = find_seeds(a.search)
        print()
        kopf = (f"{'seed':>6}  {'dauer':>6}  {'im Ziel':>7}  "
                f"{'aufpraelle':>10}  {'vorsprung':>9}")
        if a.verraten:
            kopf += "  sieger    reihenfolge"
        print(kopf)
        for seed, r in gefunden:
            zeiten = sorted(r.finish_times.values())
            vor = zeiten[1] - zeiten[0] if len(zeiten) > 1 else 0.0
            zeile = (f"{seed:>6}  {r.duration:>5.1f}s  "
                     f"{len(r.finished):>4}/{len(theme.competitors())}  "
                     f"{len(r.hits):>10}  {vor:>8.2f}s")
            if a.verraten:
                namen = " > ".join(theme.competitor(i).name for i in r.order)
                zeile += f"  {theme.competitor(r.winner).name:<8}  {namen}"
            print(zeile)
        print()
        print(f"{len(gefunden)} von {a.search} gefunden")
        if not a.verraten:
            print("Der Ausgang steht hier bewusst nicht – sonst waere er "
                  "ausgesucht statt simuliert.")
        return 0

    r = run(a.seed, a.ramps)
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
