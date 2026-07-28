#!/usr/bin/env python3
"""
make_branding.py – Kanalbanner und Profilbild fuer YouTube.

Benutzt dieselben Farben, dieselbe Schrift und denselben Hintergrund wie die
Videos (aus core/theme.py) – der Kanal soll aussehen wie das, was er zeigt.

YouTube-Masse:
  Banner       2048 x 1152. Auf dem Handy sieht man nur die mittleren
               1235 x 338 – alles Wichtige muss dort hinein.
  Profilbild   800 x 800, wird RUND beschnitten und in Kommentaren auf
               etwa 32 Pixel verkleinert. Es muss also auch winzig noch
               erkennbar sein.

CLI-Test:
  python -m gravitycup.tools.make_branding
  python -m gravitycup.tools.make_branding --standings 12 9 7 5 3 --season 1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from ..core import draw, theme

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BANNER_W, BANNER_H = 2048, 1152
SAFE_W, SAFE_H = 1235, 338          # nur das sieht man auf jedem Geraet
AVATAR = 800

CLAIM = "SIMULATED RACES  ·  NOBODY SCRIPTS THE WINNER"


def _hintergrund(w: int, h: int, raster: int = 96) -> Image.Image:
    """Verlauf plus Raster – dieselbe Bildsprache wie im Video."""
    streifen = Image.new("RGB", (1, h))
    oben, unten = theme.BG_TOP, theme.BG_BOTTOM
    streifen.putdata([
        tuple(int(oben[i] + (unten[i] - oben[i]) * (y / max(1, h - 1)))
              for i in range(3))
        for y in range(h)
    ])
    bild = streifen.resize((w, h))
    d = ImageDraw.Draw(bild, "RGBA")
    for y in range(0, h, raster):
        farbe = theme.GRID_ACCENT if (y // raster) % 5 == 0 else theme.GRID
        d.line([(0, y), (w, y)], fill=farbe, width=2)
    return bild


def banner(standings: list[int] | None = None, season: int | None = None,
           rang: list[int] | None = None, runden: int | None = None) -> Image.Image:
    """Kanalbanner. Mit `standings` zeigt es den Saisonstand statt des Claims.

    `standings` ist nach STARTNUMMER indiziert, `rang` gibt die Reihenfolge
    der Tabelle an (Fuehrender zuerst).

    Warum `rang` sein muss: frueher sortierte diese Funktion selbst nach
    Punkten. Bei Punktgleichheit entschied dann die Startnummer – ein
    stabiler Sort laesst die kleinere Nummer vorn. Genau das schliesst
    `season.standings.sortierschluessel()` aus, und B2 hat dieselbe Falle am
    Ziel beseitigt. Gemessen: Videokarte zeigte GOLD als Fuehrenden, das
    Banner RED, ohne jede Fehlermeldung – und das Banner ist das
    oeffentlichste Stueck des Kanals.
    """
    bild = _hintergrund(BANNER_W, BANNER_H)
    d = ImageDraw.Draw(bild, "RGBA")

    mitte_x, mitte_y = BANNER_W // 2, BANNER_H // 2
    safe_oben = mitte_y - SAFE_H // 2

    # Fuenf Kugeln mit Nachleuchten, als kaeme das Feld ins Bild gefahren
    r = 30
    abstand = 96
    start_x = mitte_x - abstand * 2
    kugel_y = safe_oben + 52
    for i, comp in enumerate(theme.competitors()):
        cx = start_x + i * abstand
        for k in range(7):
            a = int(14 + 40 * (k / 7))
            rr = r * (0.32 + 0.42 * (k / 7))
            tx = cx - (7 - k) * 13
            d.ellipse([tx - rr, kugel_y - rr, tx + rr, kugel_y + rr],
                      fill=comp.color + (a,))
        draw.marble_on(d, comp, cx, kugel_y, r)

    # ACHTUNG: immer theme.font() nehmen, nie font_variant() – das erzeugt
    # eine neue Schriftinstanz OHNE die eingestellte Variante, der Schriftzug
    # kommt dann duenn statt fett heraus.
    d.text((mitte_x, kugel_y + 118), "GRAVITY CUP", font=theme.font("brand_title"),
           fill=theme.TEXT, anchor="mm")

    unterzeile = theme.font("brand_claim")
    if standings:
        # Saisonstand: Name und Punkte nebeneinander, mittig
        beschriftung = f"SEASON {season} · STANDINGS" if season else "STANDINGS"
        if runden is not None:
            beschriftung += f" · {runden} ROUND{'S' if runden != 1 else ''}"
        d.text((mitte_x, kugel_y + 208), beschriftung, font=unterzeile,
               fill=theme.TEXT_MUTED, anchor="mm")
        # Reihenfolge kommt von aussen. Der Ersatzweg sortiert nur nach
        # Punkten und ist damit bei Gleichstand willkuerlich – er steht hier
        # nur, damit make_branding allein aufrufbar bleibt.
        if rang is None:
            rang = sorted(range(len(standings)), key=lambda i: -standings[i])
        eintrag = theme.font("brand_entry")
        spalte = 232
        x0 = mitte_x - spalte * 2
        for platz, i in enumerate(rang):
            comp = theme.competitor(i)
            x = x0 + platz * spalte
            y = kugel_y + 282
            draw.marble_on(d, comp, x - 68, y, 15)
            # Name und Punkte untereinander statt nebeneinander: nebeneinander
            # stehen fuer beides 193 px zur Verfuegung, ein 12-Zeichen-Name
            # aus den Kommentaren braucht bei 44 px Schrift schon allein
            # mehr als das und lief in den Nachbareintrag hinein.
            d.text((x - 44, y - 20), comp.name, font=eintrag,
                   fill=theme.TEXT if platz else comp.bright, anchor="lm")
            d.text((x - 44, y + 26), str(standings[i]), font=eintrag,
                   fill=comp.bright if platz == 0 else theme.TEXT_MUTED,
                   anchor="lm")
    else:
        d.text((mitte_x, kugel_y + 212), CLAIM, font=unterzeile,
               fill=theme.TEXT_MUTED, anchor="mm")

    return bild


def avatar() -> Image.Image:
    """Profilbild: fuenf Kugeln im Kreis. Auch bei 32 Pixel noch als
    farbiger Ring erkennbar – ein Schriftzug waere dort laengst Matsch."""
    import math

    bild = _hintergrund(AVATAR, AVATAR, raster=64)
    d = ImageDraw.Draw(bild, "RGBA")
    mitte = AVATAR // 2

    # dezenter Ring als Bahn
    bahn = 232
    d.ellipse([mitte - bahn, mitte - bahn, mitte + bahn, mitte + bahn],
              outline=theme.GRID_ACCENT, width=6)

    r = 78
    for i, comp in enumerate(theme.competitors()):
        winkel = -math.pi / 2 + i * (2 * math.pi / 5)
        cx = mitte + math.cos(winkel) * bahn
        cy = mitte + math.sin(winkel) * bahn
        draw.marble_on(d, comp, cx, cy, r)

    return bild


def _rund_vorschau(bild: Image.Image) -> Image.Image:
    """So sieht YouTube das Profilbild: rund beschnitten."""
    maske = Image.new("L", bild.size, 0)
    ImageDraw.Draw(maske).ellipse([0, 0, bild.width - 1, bild.height - 1], fill=255)
    aus = Image.new("RGBA", bild.size, (0, 0, 0, 0))
    aus.paste(bild, (0, 0), maske)
    return aus


def _banner_vorschau(bild: Image.Image) -> Image.Image:
    """Zeigt, was auf dem Handy uebrig bleibt: nur die sichere Zone."""
    kopie = bild.convert("RGBA")
    schleier = Image.new("RGBA", kopie.size, (0, 0, 0, 150))
    x1 = (BANNER_W - SAFE_W) // 2
    y1 = (BANNER_H - SAFE_H) // 2
    ImageDraw.Draw(schleier).rectangle([x1, y1, x1 + SAFE_W, y1 + SAFE_H],
                                       fill=(0, 0, 0, 0))
    kopie.alpha_composite(schleier)
    d = ImageDraw.Draw(kopie)
    d.rectangle([x1, y1, x1 + SAFE_W, y1 + SAFE_H],
                outline=(255, 90, 90, 220), width=4)
    d.text((x1 + 12, y1 - 34), "sichtbar auf jedem Geraet",
           font=theme.font("brand_label"), fill=(255, 120, 120))
    return kopie


def main() -> int:
    ap = argparse.ArgumentParser(description="Kanalbanner und Profilbild bauen")
    ap.add_argument("--out", default="branding", help="Zielordner")
    ap.add_argument("--standings", nargs=5, type=int, metavar="P",
                    help="Punkte je Teilnehmer (Reihenfolge wie in theme.COMPETITORS)")
    ap.add_argument("--season", type=int, help="Saisonnummer fuers Banner")
    a = ap.parse_args()

    ziel = Path(a.out)
    ziel.mkdir(parents=True, exist_ok=True)

    # Die Hilfsbilder kommen bewusst in einen EIGENEN Ordner. Lagen sie
    # neben den echten Dateien, wurde schon einmal die Vorschau mit den
    # roten Hilfslinien auf YouTube hochgeladen.
    hilf = ziel / "nicht-hochladen"
    hilf.mkdir(exist_ok=True)

    b = banner(a.standings, a.season)
    b.save(ziel / "banner.png")
    _banner_vorschau(b).save(hilf / "banner-sichere-zone.png")

    av = avatar()
    av.save(ziel / "profilbild.png")
    _rund_vorschau(av).save(hilf / "profilbild-so-schneidet-youtube.png")
    av.resize((32, 32), Image.LANCZOS).resize((256, 256), Image.NEAREST).save(
        hilf / "profilbild-in-kommentaren.png")

    print("HOCHLADEN:")
    print(f"  {ziel / 'banner.png'}       {BANNER_W}x{BANNER_H}")
    print(f"  {ziel / 'profilbild.png'}   {AVATAR}x{AVATAR}")
    print()
    print("NUR ZUM ANSCHAUEN (nicht hochladen):")
    for p in sorted(hilf.iterdir()):
        print(f"  {p}")
    if not theme.font_is_portable():
        print()
        print("  ! Schrift kommt aus dem System (Bahnschrift), nicht aus dem Projekt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
