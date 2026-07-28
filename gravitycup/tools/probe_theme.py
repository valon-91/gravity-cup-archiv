#!/usr/bin/env python3
"""
probe_theme.py – Einzeltest fuer Baustein B1 (theme.py + draw.py).

Baut eine kuenstliche Szene ohne Physik-Bibliothek und rendert daraus die
vier Bildsituationen, die im fertigen Video vorkommen:

  1_hook      die ersten Sekunden mit Aufhaenger
  2_race      laufendes Rennen mit Rangliste
  3_finish    Zieleinlauf
  4_result    Endkarte mit Sieger und Reihenfolge

Damit laesst sich die Gestaltung beurteilen, bevor irgendeine Simulation
existiert. Es wird NICHT geprueft, ob die Physik stimmt – nur das Aussehen.

CLI-Test:
  python -m gravitycup.tools.probe_theme
  python -m gravitycup.tools.probe_theme --out probe --scale 1 --sheet
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path

from PIL import Image

from ..core import draw, theme

if hasattr(sys.stdout, "reconfigure"):          # Windows-Konsole ist cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Kuenstliche Szene – ersetzt spaeter die echte Simulation
# ---------------------------------------------------------------------------

WALL_LEFT, WALL_RIGHT = 40, 1040


def build_scene(seed: int = 7, ramps: int = 6) -> dict:
    """Eine Zickzack-Strecke mit Stiften, rein geometrisch."""
    rng = random.Random(seed)
    segments: list[tuple[float, float, float, float]] = []
    pegs: list[tuple[float, float]] = []

    top, gap, drop = 700, 430, 250
    for i in range(ramps):
        y = top + i * gap
        if i % 2 == 0:
            segments.append((WALL_LEFT + 20, y, 900, y + drop))
        else:
            segments.append((WALL_RIGHT - 20, y, 180, y + drop))
        for _ in range(2):
            pegs.append((rng.uniform(220, 860), y + drop + rng.uniform(60, 150)))

    bottom = top + ramps * gap + 120
    segments.append((WALL_LEFT + 20, bottom, theme.WIDTH / 2 - 150, bottom + 260))
    segments.append((WALL_RIGHT - 20, bottom, theme.WIDTH / 2 + 150, bottom + 260))
    finish_y = bottom + 400
    segments.append((WALL_LEFT, finish_y + 150, WALL_RIGHT, finish_y + 150))
    segments.append((WALL_LEFT, 0, WALL_LEFT, finish_y + 160))
    segments.append((WALL_RIGHT, 0, WALL_RIGHT, finish_y + 160))

    return {"segments": segments, "pegs": pegs, "finish_y": finish_y}


def fake_positions(scene: dict, fortschritt: float, seed: int = 3) -> list[dict]:
    """Fuenf Teilnehmer irgendwo auf der Strecke – nur fuer die Optik."""
    rng = random.Random(seed)
    fin = scene["finish_y"]
    ergebnis = []
    for i in range(len(theme.COMPETITORS)):
        vorsprung = (1.0 - i * 0.055) * fortschritt
        y = 200 + vorsprung * (fin - 200)
        x = theme.WIDTH / 2 + math.sin(y / 260 + i * 1.3) * 300 + rng.uniform(-30, 30)
        x = max(WALL_LEFT + theme.MARBLE_RADIUS + 12,
                min(WALL_RIGHT - theme.MARBLE_RADIUS - 12, x))
        # Nachleuchten entlang der Fallrichtung, mit zunehmendem Abstand –
        # so sieht es aus, wenn eine Kugel beschleunigt.
        spur = []
        for k in range(theme.TRAIL_LENGTH):
            zurueck = (theme.TRAIL_LENGTH - k)
            ty = y - zurueck * 11 * (0.5 + fortschritt)
            tx = x - zurueck * 1.6
            spur.append((tx, ty))
        ergebnis.append({"x": x, "y": y, "angle": y / 90.0, "trail": spur})
    return ergebnis


def draw_scene(canvas: draw.Canvas, scene: dict, marbles: list[dict]) -> None:
    """Hintergrund, Strecke und Teilnehmer – ohne Einblendungen."""
    canvas.grid()
    for (x1, y1, x2, y2) in scene["segments"]:
        canvas.track_segment(x1, y1, x2, y2)
    for (px, py) in scene["pegs"]:
        canvas.peg(px, py)
    canvas.finish_line(scene["finish_y"])
    for i, m in enumerate(marbles):
        canvas.marble(theme.competitor(i), m["x"], m["y"], m["angle"], m["trail"])


def ranking(marbles: list[dict]) -> list[int]:
    """Rangfolge nach Tiefe – wer weiter unten ist, fuehrt."""
    return sorted(range(len(marbles)), key=lambda i: -marbles[i]["y"])


# ---------------------------------------------------------------------------
# Die vier Situationen
# ---------------------------------------------------------------------------


def situation_hook(scene: dict, scale: int) -> draw.Canvas:
    marbles = fake_positions(scene, 0.02)
    cam = draw.Camera.start_at(max(m["y"] for m in marbles),
                               limit_bottom=scene["finish_y"])
    c = draw.Canvas(scale=scale, camera=cam)
    draw_scene(c, scene, marbles)
    c.hook("Which color wins?", "real physics, no cuts")
    return c


def situation_race(scene: dict, scale: int) -> draw.Canvas:
    marbles = fake_positions(scene, 0.46)
    cam = draw.Camera.start_at(max(m["y"] for m in marbles),
                               limit_bottom=scene["finish_y"])
    c = draw.Canvas(scale=scale, camera=cam)
    draw_scene(c, scene, marbles)
    c.hud_ranking(ranking(marbles))
    return c


def situation_finish(scene: dict, scale: int) -> draw.Canvas:
    marbles = fake_positions(scene, 0.985)
    cam = draw.Camera.start_at(max(m["y"] for m in marbles),
                               limit_bottom=scene["finish_y"])
    c = draw.Canvas(scale=scale, camera=cam)
    draw_scene(c, scene, marbles)
    c.hud_ranking(ranking(marbles))
    return c


def situation_result(scene: dict, scale: int) -> draw.Canvas:
    marbles = fake_positions(scene, 1.0)
    cam = draw.Camera.start_at(max(m["y"] for m in marbles),
                               limit_bottom=scene["finish_y"])
    c = draw.Canvas(scale=scale, camera=cam)
    draw_scene(c, scene, marbles)
    reihenfolge = ranking(marbles)
    c.result_card(reihenfolge, points=[5, 4, 3, 2, 1])
    return c


SITUATIONS = {
    "1_hook": situation_hook,
    "2_race": situation_race,
    "3_finish": situation_finish,
    "4_result": situation_result,
}


def contact_sheet(bilder: list[Image.Image], breite: int = 420) -> Image.Image:
    """Alle Situationen nebeneinander – erspart vier Einzelklicks."""
    hoehe = int(breite * theme.HEIGHT / theme.WIDTH)
    luft = 18
    blatt = Image.new(
        "RGB",
        (breite * len(bilder) + luft * (len(bilder) + 1), hoehe + luft * 2),
        (10, 12, 20),
    )
    for i, b in enumerate(bilder):
        blatt.paste(b.resize((breite, hoehe), Image.LANCZOS),
                    (luft + i * (breite + luft), luft))
    return blatt


def main() -> int:
    ap = argparse.ArgumentParser(description="Einzeltest Baustein B1")
    ap.add_argument("--out", default="probe", help="Zielordner (Standard: probe)")
    ap.add_argument("--scale", type=int, default=theme.SUPERSAMPLE,
                    help="Supersampling; 1 ist schnell, 2 ist Endqualitaet")
    ap.add_argument("--seed", type=int, default=7, help="Streckenverlauf")
    ap.add_argument("--only", choices=sorted(SITUATIONS),
                    help="nur eine Situation rendern")
    ap.add_argument("--sheet", action="store_true",
                    help="zusaetzlich ein Kontaktblatt mit allen Situationen")
    ap.add_argument("--names", nargs=5, metavar="NAME",
                    help="eigene Teilnehmernamen ausprobieren (Saison 2)")
    a = ap.parse_args()

    if a.names:
        # Farben bleiben, nur die Namen wechseln – so wie ab Saison 2.
        theme.set_competitors(theme.rename(a.names))

    ziel = Path(a.out)
    ziel.mkdir(parents=True, exist_ok=True)

    print(theme.describe())
    if not theme.font_is_portable():
        print()
        print("  ! Die Schrift liegt NICHT im Projekt, sondern im System.")
        print("    Auf einem anderen Rechner koennen die Videos anders aussehen.")
        print(f"    Abhilfe: Schriftdatei nach {theme.FONT_DIR} legen.")
    print()

    namen = [a.only] if a.only else list(SITUATIONS)
    scene = build_scene(a.seed)
    bilder: list[Image.Image] = []

    import time
    for name in namen:
        t0 = time.perf_counter()
        canvas = SITUATIONS[name](scene, a.scale)
        bild = canvas.finish()
        pfad = ziel / f"{name}.png"
        bild.save(pfad)
        bilder.append(bild)
        dauer = time.perf_counter() - t0
        print(f"  {name:10s} -> {pfad}   ({dauer:.2f} s)")

    if a.sheet and len(bilder) > 1:
        blatt = contact_sheet(bilder)
        pfad = ziel / "0_uebersicht.png"
        blatt.save(pfad)
        print(f"  {'uebersicht':10s} -> {pfad}")

    print()
    print(f"{len(bilder)} Bild(er) in {ziel.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
