#!/usr/bin/env python3
"""
probe_arena.py – Kammern EINZELN pruefen, statt einen ganzen Lauf zu rechnen.

Warum es dieses Werkzeug gibt, und zwar genau dieses:

Ein voller Showlauf kostet zwei bis vier Minuten und liefert am Ende eine
Handvoll Zahlen ueber die ganze Folge. Die Fehler der Arena sind aber
OERTLICH – eine einzelne Kammer haelt den Pulk fest, und alles danach
laeuft nur noch auf der Raeumzeit weiter. Am 30. und 31.07.2026 hat das
zweimal dazu gefuehrt, dass "bestanden" gemeldet wurde, waehrend das Video
stand: die Kaskade zaehlt sich zu Ende, auch wenn sich nichts mehr bewegt.

Eine einzelne Kammer laesst sich fuer sich rechnen – Sperre offen, Feld
hinein, Uhr laufen lassen. Das kostet Sekunden statt Minuten und sagt,
WELCHE Kammer klemmt. Damit ist aus einer Vier-Minuten-Frage eine
Fuenf-Sekunden-Frage geworden, und erst dadurch liessen sich Bauarten
ueberhaupt vergleichend messen.

Zwei Proben, weil es zwei verschiedene Fallen gibt:

  --einzeln  EINE Kugel je Kammer. Findet die Falle, die nur den LETZTEN
             trifft. Gemessen am 31.07.2026: das Drehkreuz ueber dem
             Ausgang schlug den Ueberlebenden den Trichter wieder hinauf,
             92 px vor dem Ziel, fuenfundzwanzig Minuten lang. Ein voller
             Lauf zeigt davon nur "0 im Ziel"; diese Probe zeigt die
             Kammer.

  --feld     Das ganze Feld der Kammer. Findet den BOGEN ueber der
             Engstelle – mehrere Kugeln, die sich gegenseitig tragen.
             Gemeldet werden zwei Fehlerbilder, und beide sind toedlich:
             STAU (kommt nicht durch) und STILL (kommt durch, ohne sich zu
             bewegen).

CLI-Test:
  python -m gravitycup.tools.probe_arena --seed 2
  python -m gravitycup.tools.probe_arena --seeds 2,3,7 --kurz
  python -m gravitycup.tools.probe_arena --seed 2 --von 40 --bis 63
"""
from __future__ import annotations

import argparse
import sys

from ..core import physics, theme
from ..disciplines import arena
from . import show

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MARBLE_D = arena.MARBLE_D

#: Geduld je Kammer. Eine gesunde Kammer ist in unter sechs Sekunden leer;
#: gemessen ueber 189 Proben lag die langsamste bei 5,9 s.
GEDULD_EINZELN = 20.0
GEDULD_FELD = 25.0

#: Einwurfstellen der Einzelprobe, als Anteil der Einwurfoeffnung.
#:
#: NIE genau die Mitte: dort sitzt die Spitze des Teilers, und eine Kugel,
#: die senkrecht und ohne Seitwaertsfahrt darauf faellt, balanciert dort.
#: Das ist ein Artefakt der Probe, nicht der Kammer – im Lauf kommt keine
#: Kugel ohne Seitwaertsfahrt an. Die erste Fassung dieser Probe meldete
#: dadurch jede Kammer als Falle.
STELLEN = (-0.36, -0.20, -0.07, 0.07, 0.20, 0.36)


def teilstrecke(track: physics.Track, form: arena.Kammerform):
    """Nur die Bauteile dieser Kammer. Das macht die Probe billig."""
    oben, unten = form.oben - 400, form.unten + 500

    def drin(s: physics.Segment) -> bool:
        return not (max(s.y1, s.y2) < oben or min(s.y1, s.y2) > unten)

    return ([s for s in track.segments if drin(s)],
            [p for p in track.pegs if oben <= p.y <= unten],
            [r for r in track.rotoren if oben <= r.y <= unten])


# ---------------------------------------------------------------------------
# Einzelprobe: kommt der LETZTE durch?
# ---------------------------------------------------------------------------


def einzelprobe(track, form, bauart, grenze: float = GEDULD_EINZELN):
    """Je Einwurfstelle die Zeit bis zum Austritt. `None` = haengengeblieben."""
    seg, pegs, rot = teilstrecke(track, form)
    mitte = theme.WIDTH / 2
    einwurf = bauart.ausgang() * 1.35
    ergebnisse = []
    for anteil in STELLEN:
        start = (mitte + anteil * einwurf, form.oben - 140)
        mini = physics.Track(segments=seg, pegs=pegs, starts=[start],
                             finish_y=form.austritt, rotoren=rot,
                             name="probe")
        try:
            r = physics.simulate(mini, 1, count=1, max_seconds=grenze,
                                 patience_seconds=grenze, tail_seconds=0.1,
                                 iterationen=arena.SOLVER_ITERATIONEN)
        except physics.SimulationError:
            ergebnisse.append(None)
        else:
            ergebnisse.append(r.finish_times.get(0))
    return ergebnisse


# ---------------------------------------------------------------------------
# Feldprobe: kommt der PULK durch, und bewegt er sich dabei?
# ---------------------------------------------------------------------------


def feldplaetze(form, anzahl, seg, pegs):
    """Ein Feld im oberen Teil der Kammer, wie es nach dem Einfallen liegt.

    Ein Platz wird nur genommen, wenn dort wirklich Platz IST. Die erste
    Fassung setzte ein Raster blind und traf damit die Stifte, die ab
    `oben + 150` stehen; pymunk schleudert ueberlappende Koerper
    auseinander, und die Probe mass danach ihr eigenes Artefakt. Dieselbe
    Blindheit hat das Sturzrennen einmal 94 % seiner Laeufe gekostet.
    """
    innen_l = form.links + arena.SEG_RADIUS + theme.MARBLE_RADIUS + 6
    innen_r = form.rechts - arena.SEG_RADIUS - theme.MARBLE_RADIUS - 6
    abstand = MARBLE_D + 10
    je_reihe = max(1, int((innen_r - innen_l) // abstand) + 1)
    plaetze: list[tuple[float, float]] = []
    reihe = 0
    while len(plaetze) < anzahl:
        y = form.oben + 120 + reihe * (MARBLE_D + 8)
        if y > form.unten - 260:
            return None                  # nur noch der Trichter, kein Platz
        for s in range(je_reihe):
            if len(plaetze) >= anzahl:
                break
            x = innen_l + s * abstand
            if physics.passt_durch(x, y, theme.MARBLE_RADIUS, seg, pegs, 6.0):
                plaetze.append((x, y))
        reihe += 1
    return plaetze


class _AlleDurch(physics.RaceToLine):
    """Wie das Sturzrennen, aber nie erledigt – die Uhr laeuft voll durch."""

    def erledigt(self) -> bool:
        return False


def feldprobe(track, form, anzahl: int, grenze: float = GEDULD_FELD):
    """Wie viele durchkommen, wann der Letzte durch ist, und ob es sich bewegt."""
    seg, pegs, rot = teilstrecke(track, form)
    plaetze = feldplaetze(form, anzahl, seg, pegs)
    if plaetze is None:
        return None
    mini = physics.Track(segments=seg, pegs=pegs, starts=plaetze,
                         finish_y=form.austritt, rotoren=rot, name="probe")
    try:
        r = physics.simulate(mini, 1, count=anzahl, max_seconds=grenze,
                             patience_seconds=grenze, tail_seconds=0.0,
                             regel=_AlleDurch(form.austritt),
                             iterationen=arena.SOLVER_ITERATIONEN)
    except physics.SimulationError:
        return {"durch": 0, "t_alle": None, "lebendig": 0.0, "haengen": []}

    durch = len(r.finish_times)
    t_alle = max(r.finish_times.values()) if durch == anzahl else None

    # Bewegt sich, wer noch drin ist? Wer durch ist, zaehlt nicht mehr mit –
    # sonst meldet eine leere Kammer Stillstand.
    fps, bewegt = r.fps, []
    for f in range(1, len(r.frames), 3):
        offen = [i for i in range(anzahl)
                 if r.finish_times.get(i, 1e9) * fps > f]
        if not offen:
            break
        n = sum(1 for i in offen
                if abs(r.frames[f][i][1] - r.frames[f - 1][i][1]) > 3.0
                or abs(r.frames[f][i][0] - r.frames[f - 1][i][0]) > 3.0)
        bewegt.append(n / len(offen))
    lebendig = (sum(1 for x in bewegt if x >= 0.10) / len(bewegt)
                if bewegt else 0.0)

    haengen = [(round(r.frames[-1][i][0]), round(r.frames[-1][i][1]))
               for i in range(anzahl) if i not in r.finish_times]
    return {"durch": durch, "t_alle": t_alle, "lebendig": lebendig,
            "haengen": haengen}


# ---------------------------------------------------------------------------
# Urteil
# ---------------------------------------------------------------------------


def pruefe_kammern(seed: int, teilnehmer: int = 64,
                   bauart: arena.Bauart | None = None,
                   von: int = 1, bis: int = 0,
                   einzeln: bool = True, feld: bool = True,
                   laut: bool = True) -> list[str]:
    """Alle Kammern durchprobieren. Leere Liste = keine Falle gefunden."""
    bauart = bauart or arena.VORGABE
    track = arena.build_track(seed, teilnehmer, bauart)
    formen = arena.kammerformen(teilnehmer, bauart)
    bis = bis or len(formen)
    maengel: list[str] = []
    if laut:
        print(f"{'K':>3} {'drin':>4} {'breite':>6} {'ausg':>5} "
              f"{'einzeln':>8} {'durch':>7} {'t_alle':>7} {'lebendig':>9}"
              f"   Urteil")
    for form in formen:
        if not von <= form.nummer <= bis:
            continue
        drin = teilnehmer - (form.nummer - 1)
        e_text, f_text, urteil = "-", "      -       -", []

        if einzeln:
            zeiten = einzelprobe(track, form, bauart)
            fallen = sum(1 for z in zeiten if z is None)
            e_text = f"{len(zeiten) - fallen}/{len(zeiten)}"
            if fallen:
                urteil.append("FALLE")
                maengel.append(
                    f"Kammer {form.nummer}: {fallen} von {len(zeiten)} "
                    f"Einwuerfen kommen ALLEIN nicht durch")

        if feld:
            e = feldprobe(track, form, drin)
            if e is None:
                f_text = "  (kein Platz zum Aufstellen)"
            else:
                t = "  ---" if e["t_alle"] is None else f"{e['t_alle']:5.1f}"
                f_text = (f"{e['durch']:>3}/{drin:<3} {t:>7} "
                          f"{e['lebendig'] * 100:>8.0f}%")
                if e["t_alle"] is None:
                    urteil.append("STAU")
                    maengel.append(
                        f"Kammer {form.nummer}: nur {e['durch']} von {drin} "
                        f"kommen durch, Rest haengt bei "
                        + ", ".join(f"({x},{y})" for x, y in e["haengen"][:3]))
                if e["lebendig"] < arena.MIN_LEBENDIG:
                    urteil.append("STILL")
                    maengel.append(
                        f"Kammer {form.nummer}: bewegt sich nur "
                        f"{e['lebendig'] * 100:.0f} % ihrer Dauer "
                        f"(mindestens {arena.MIN_LEBENDIG * 100:.0f} %)")

        if laut:
            print(f"{form.nummer:>3} {drin:>4} {form.rechts - form.links:>6.0f} "
                  f"{form.ausgang:>5.0f} {e_text:>8} {f_text}   "
                  f"{' '.join(urteil) if urteil else 'ok'}")
    return maengel


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Kammern der Arena einzeln pruefen")
    ap.add_argument("--seed", type=int, default=2)
    ap.add_argument("--seeds", help="mehrere Seeds, z. B. 2,3,7")
    # Dieselbe Feldgroesse wie die Show – ein Pruefstand mit einem anderen
    # Feld prueft eine andere Geometrie, denn die Kammern schrumpfen mit.
    ap.add_argument("--teilnehmer", type=int, default=show.TEILNEHMER)
    ap.add_argument("--von", type=int, default=1)
    ap.add_argument("--bis", type=int, default=0)
    ap.add_argument("--einzeln", action="store_true",
                    help="nur die Einzelkugel-Probe")
    ap.add_argument("--feld", action="store_true", help="nur die Feldprobe")
    ap.add_argument("--kurz", action="store_true",
                    help="nur das Urteil, keine Tabelle")
    a = ap.parse_args()

    theme.set_format("quer")
    theme.set_competitors(theme.feld(a.teilnehmer))
    seeds = ([int(s) for s in a.seeds.split(",")] if a.seeds else [a.seed])
    einzeln = a.einzeln or not a.feld
    feld = a.feld or not a.einzeln

    schlecht = 0
    for seed in seeds:
        if not a.kurz:
            print(f"seed {seed}, {a.teilnehmer} Teilnehmer  "
                  f"(Kugel {MARBLE_D:.0f} px)")
            print()
        maengel = pruefe_kammern(seed, a.teilnehmer, arena.VORGABE,
                                 a.von, a.bis, einzeln, feld,
                                 laut=not a.kurz)
        if not a.kurz:
            print()
        if maengel:
            schlecht += 1
            print(f"seed {seed}: {len(maengel)} Beanstandungen")
            for m in maengel[:8]:
                print(f"  - {m}")
        else:
            print(f"seed {seed}: in Ordnung – jede Kammer laesst ihr Feld "
                  f"durch, und einen Einzelnen auch")
    return 1 if schlecht else 0


if __name__ == "__main__":
    raise SystemExit(main())
