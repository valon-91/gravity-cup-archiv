#!/usr/bin/env python3
"""
probe_descent.py – Sichtpruefung der Sturzrennen-Strecke.

Zahlen sagen, ob ein Lauf brauchbar ist. Ob die Strecke auch AUSSIEHT wie
eine Strecke, sagt nur ein Bild. Dieses Werkzeug liefert zwei Ansichten:

  --riss     die ganze Strecke auf ein Blatt gestaucht, mit den Startplaetzen
             und den Engstellen. Fuer die Frage „stimmt die Geometrie?"
  --bilder   echte Einzelbilder aus einem Lauf, in Ausgabegroesse.
             Fuer die Frage „sieht das im Video gut aus?"

CLI-Test:
  python -m gravitycup.tools.probe_descent --seed 2
  python -m gravitycup.tools.probe_descent --seed 2 --riss --bilder 4
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from ..core import draw, physics, theme
from ..disciplines import descent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AUSGABE = Path("probe_descent")

#: Breite des Streckenrisses in Pixeln. Die Strecke ist rund 5,7-mal so hoch
#: wie breit, deshalb bleibt sie auch gestaucht noch lesbar.
RISS_BREITE = 620


def riss(seed: int, ramps: int = descent.RAMP_COUNT) -> Image.Image:
    """Die ganze Strecke auf einem Blatt – schlicht, aber massstabsgetreu."""
    track = descent.build_track(seed, ramps)
    hoehe_welt = track.finish_y + 200
    faktor = RISS_BREITE / theme.WIDTH
    bild = Image.new("RGB", (RISS_BREITE, int(hoehe_welt * faktor)), (16, 18, 26))
    d = ImageDraw.Draw(bild, "RGBA")

    def p(x: float, y: float) -> tuple[float, float]:
        return (x * faktor, y * faktor)

    for s in track.segments:
        d.line([p(s.x1, s.y1), p(s.x2, s.y2)],
               fill=(96, 106, 130), width=max(1, int(s.radius * 2 * faktor)))
    for peg in track.pegs:
        r = peg.radius * faktor
        cx, cy = p(peg.x, peg.y)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(150, 160, 185))

    # Startplaetze in Kugelgroesse: zeigt sofort, ob sie ueberhaupt passen
    for i, (sx, sy) in enumerate(track.starts):
        r = theme.MARBLE_RADIUS * faktor
        cx, cy = p(sx, sy)
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  fill=theme.competitor(i).color)

    fy = p(0, track.finish_y)[1]
    d.line([(0, fy), (RISS_BREITE, fy)], fill=(240, 230, 120), width=2)

    # gefundene Engstellen rot markieren – bei heiler Strecke bleibt es leer
    for text in descent.pruefe_durchlaesse(track):
        d.text((6, 6), "ENGSTELLEN – siehe --geometrie", fill=(240, 80, 80))
        break

    return bild


def bilder(seed: int, anzahl: int, ramps: int = descent.RAMP_COUNT) -> list[Image.Image]:
    """Gleichmaessig ueber den Lauf verteilte Einzelbilder in Ausgabegroesse."""
    r = descent.run(seed, ramps)
    schritte = max(1, len(r.frames) // (anzahl + 1))
    raus: list[Image.Image] = []
    for k in range(1, anzahl + 1):
        f = min(len(r.frames) - 1, k * schritte)
        positionen = r.frames[f]
        fuehrend = max(pos[1] for pos in positionen)
        cam = draw.Camera.start_at(fuehrend, limit_bottom=r.finish_y)
        c = draw.Canvas(camera=cam)
        c.grid()
        for s in r.segments:
            c.track_segment(s.x1, s.y1, s.x2, s.y2)
        for peg in r.pegs:
            c.peg(peg.x, peg.y, peg.radius)
        c.finish_line(r.finish_y)
        for i, (x, y, winkel) in enumerate(positionen):
            c.marble(theme.competitor(i), x, y, winkel, [])
        raus.append(c.finish())
    return raus


def main() -> int:
    ap = argparse.ArgumentParser(description="Sichtpruefung Disziplin 1")
    ap.add_argument("--seed", type=int, default=2)
    ap.add_argument("--ramps", type=int, default=descent.RAMP_COUNT)
    ap.add_argument("--riss", action="store_true", help="Streckenriss zeichnen")
    ap.add_argument("--bilder", type=int, default=0, metavar="N",
                    help="N Einzelbilder aus dem Lauf zeichnen")
    ap.add_argument("--out", default=str(AUSGABE))
    a = ap.parse_args()

    if not a.riss and not a.bilder:
        a.riss, a.bilder = True, 3

    ziel = Path(a.out)
    ziel.mkdir(parents=True, exist_ok=True)

    if a.riss:
        pfad = ziel / f"riss-seed{a.seed}.png"
        riss(a.seed, a.ramps).save(pfad)
        print(f"Streckenriss: {pfad}")

    for i, bild in enumerate(bilder(a.seed, a.bilder, a.ramps), start=1):
        pfad = ziel / f"bild-seed{a.seed}-{i}.png"
        bild.save(pfad)
        print(f"Einzelbild:   {pfad}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
