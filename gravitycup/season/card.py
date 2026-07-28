#!/usr/bin/env python3
"""
card.py – Baustein B6: die Tabelle als Bild.

Zwei Formate, eine Quelle:

  Videoformat   1080x1920  – Endkarte einer Folge, Community-Post
  Bannerformat  2048x1152  – Kanalbanner mit Saisonstand

Beide holen ihre Zahlen aus `standings.berechne()`, also aus dem
Rundenarchiv. Es gibt keinen zweiten Weg, an die Tabelle zu kommen – eine
Grafik, die etwas anderes zeigt als `--pruefen` nachrechnet, kann so nicht
entstehen.

CLI:
  python -m gravitycup.season.card --saison 1
  python -m gravitycup.season.card --saison 1 --out data/tabelle
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

from ..core import draw, theme
from ..tools import make_branding
from . import standings

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

#: Zeilenhoehe der Tabelle im Videoformat, in Ausgabe-Pixeln.
ZEILE = 148
#: Oberkante der ersten Zeile. Darueber stehen Titel und Unterzeile.
TABELLE_OBEN = 560
#: Linke Kante der Tabelle.
RAND = theme.SAFE_LEFT + 46
#: Rechte Kante. Getrennt gerechnet, NICHT symmetrisch zu RAND: die sichere
#: Zone ist rechts breiter (SAFE_RIGHT 190 gegen SAFE_LEFT 40), weil dort
#: die Shorts-Knopfleiste sitzt. Eine symmetrische Tabelle ragte 104 px
#: darunter, die Punktzahlen 58 px – ausgerechnet die Spalte, auf die es
#: ankommt.
RAND_RECHTS = theme.WIDTH - theme.SAFE_RIGHT


def videokarte(tabelle: list[standings.Eintrag], saison: int | None,
               runden: int, scale: int | None = None) -> Image.Image:
    """Die Tabelle im Hochformat."""
    scale = theme.SUPERSAMPLE if scale is None else scale
    c = draw.Canvas(scale=scale)
    c.grid()

    titel = f"SEASON {saison}" if saison else "STANDINGS"
    c.text_centered(300, titel, "result_name", fill=theme.TEXT)
    c.text_centered(392, f"AFTER {runden} ROUND{'S' if runden != 1 else ''}",
                    "result_label", fill=theme.TEXT_MUTED)

    breite = RAND_RECHTS - RAND
    hoehe = ZEILE * len(tabelle) + theme.PANEL_PAD * 2
    c.panel((RAND, TABELLE_OBEN, RAND + breite, TABELLE_OBEN + hoehe),
            alpha=178)

    knapp = standings.punktgleich_an_der_spitze(tabelle)
    for platz, e in enumerate(tabelle):
        y = TABELLE_OBEN + theme.PANEL_PAD + ZEILE * platz + ZEILE / 2
        comp = theme.competitor(e.teilnehmer)

        # Der Fuehrende bekommt eine eigene Unterlegung. Stehen die
        # ersten beiden punktgleich, bekommen sie BEIDE eine – die Tabelle
        # hat zwar einen Ersten (ueber Siege und juengste Runde), aber nach
        # Punkten ist es offen, und genau das soll man sehen.
        fuehrend = platz == 0 or (knapp and platz == 1)
        if fuehrend:
            c.draw.rounded_rectangle(
                [c.s(RAND + 12), c.s(y - ZEILE / 2 + 6),
                 c.s(RAND + breite - 12), c.s(y + ZEILE / 2 - 6)],
                radius=c.s(16), fill=comp.color + (34,))

        c.text(RAND + 46, y, f"{platz + 1}", "result_label",
               fill=theme.TEXT_MUTED, anchor="lm")
        draw.marble_on(c.draw, comp, c.s(RAND + 148), c.s(y), c.s(30))
        c.text(RAND + 208, y, comp.name, "card_entry",
               fill=comp.bright if fuehrend else theme.TEXT, anchor="lm")

        # Siege als kleine Nebenangabe – sie entscheiden den Gleichstand,
        # also gehoeren sie sichtbar in die Tabelle.
        if e.siege:
            c.text(RAND + breite - 214, y,
                   f"{e.siege} WIN{'S' if e.siege != 1 else ''}", "badge",
                   fill=theme.TEXT_MUTED, anchor="rm")
        c.text(RAND + breite - 46, y, f"{e.punkte}", "result_name",
               fill=comp.bright if fuehrend else theme.TEXT, anchor="rm")

    fuss = TABELLE_OBEN + hoehe + 92
    if knapp:
        c.text_centered(fuss, "LEVEL ON POINTS", "result_label",
                        fill=theme.TEXT_MUTED)
    else:
        c.text_centered(fuss,
                        "  ·  ".join(str(p) for p in standings.PUNKTE),
                        "badge", fill=theme.TEXT_MUTED)
        c.text_centered(fuss + 52, "POINTS PER PLACE", "badge",
                        fill=theme.TEXT_MUTED)

    return c.finish()


def bannerkarte(tabelle: list[standings.Eintrag], saison: int | None,
                runden: int | None = None) -> Image.Image:
    """Die Tabelle im Bannerformat.

    Gezeichnet wird vom Kanalbanner selbst – es kann den Saisonstand schon.
    Ein zweiter Zeichenweg waere ein zweites Aussehen.

    Die REIHENFOLGE wird mitgegeben, nicht nur die Punkte. Sonst sortiert
    das Banner selbst und bricht den Gleichstand nach Startnummer – dann
    steht auf dem Kanalbanner ein anderer Fuehrender als in der Videokarte.
    """
    punkte = [0] * len(theme.competitors())
    for e in tabelle:
        punkte[e.teilnehmer] = e.punkte
    return make_branding.banner(standings=punkte, season=saison,
                                rang=[e.teilnehmer for e in tabelle],
                                runden=runden)


def main() -> int:
    ap = argparse.ArgumentParser(description="Baustein B6 – Tabellengrafik")
    ap.add_argument("--saison", type=int)
    ap.add_argument("--archiv", default=str(standings.ARCHIV))
    ap.add_argument("--out", default="data/tabelle")
    ap.add_argument("--supersample", type=int)
    a = ap.parse_args()

    # Die Saison wird VOR dem Rechnen bestimmt und danach gefiltert.
    #
    # Vorher wurde ohne --saison alles geladen, zu einer Summe addiert und
    # die Saisonnummer erst hinterher aus der letzten Runde abgeleitet – die
    # Grafik zeigte also die Allzeitsumme und beschriftete sie als „SEASON 2".
    # Nachgerechnet mit S01R01-R03 + S02R01: Grafik meldete RED vorn,
    # `standings --saison 2` VIOLET. Genau die Abweichung, die der
    # Modulkopf ausschliesst.
    try:
        alle = standings.lade_runden(Path(a.archiv))
    except standings.ArchivFehler as e:
        print(f"Archiv nicht auswertbar:\n  {e}")
        return 1
    if not alle:
        print(f"Keine gewerteten Runden in {a.archiv}.")
        return 1

    saison = a.saison if a.saison is not None else max(r.saison for r in alle)
    runden = [r for r in alle if r.saison == saison]
    if not runden:
        vorhanden = ", ".join(str(s) for s in sorted({r.saison for r in alle}))
        print(f"Keine Runden fuer Saison {saison}. Vorhanden: {vorhanden}")
        return 1

    tabelle = standings.berechne(runden)
    ziel = Path(a.out)
    ziel.mkdir(parents=True, exist_ok=True)

    video = ziel / f"tabelle-S{saison:02d}-video.png"
    banner = ziel / f"tabelle-S{saison:02d}-banner.png"
    videokarte(tabelle, saison, len(runden), a.supersample).save(video)
    bannerkarte(tabelle, saison, len(runden)).save(banner)

    print(f"Saison {saison}, {len(runden)} Runden")
    for platz, e in enumerate(tabelle, start=1):
        print(f"  {platz}. {e.name:<8} {e.punkte:>3}")
    print()
    print(f"  {video}    {theme.WIDTH}x{theme.HEIGHT}")
    print(f"  {banner}   {make_branding.BANNER_W}x{make_branding.BANNER_H}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
