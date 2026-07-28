#!/usr/bin/env python3
"""
theme.py – Jede Gestaltungsentscheidung des Kanals an EINER Stelle.

Kein anderes Modul legt Farben, Groessen, Abstaende oder Schriften fest.
Wer hier eine Zahl aendert, aendert sie fuer jedes kuenftige Video – das
ist Absicht: der Wiedererkennungswert des Kanals haengt daran.

CLI-Test:  python -m gravitycup.tools.probe_theme
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import ImageFont

# ---------------------------------------------------------------------------
# Ausgabeformat
# ---------------------------------------------------------------------------

WIDTH = 1080
HEIGHT = 1920
FPS = 30

#: Intern wird mit diesem Faktor groesser gezeichnet und am Schluss
#: heruntergerechnet. 2 = 2160x3840 je Bild. Der Wert kostet Rechenzeit
#: quadratisch, darum fuer Probelaeufe auf 1 stellen.
SUPERSAMPLE = 2

# ---------------------------------------------------------------------------
# Sichere Zonen (YouTube-Shorts-Bedienelemente)
#
# Shorts blendet ueber das Video eigene Bedienelemente: unten Kanalname,
# Titel und Tonzeile, rechts die Knopfleiste, oben je nach Client eine
# Kopfzeile. Was dort liegt, ist im Zweifel verdeckt. Alle Einblendungen
# halten sich an diese Raender.
# ---------------------------------------------------------------------------

SAFE_TOP = 150
SAFE_BOTTOM = 420
SAFE_LEFT = 40
SAFE_RIGHT = 190

#: Waagrechtes Band, in dem der Hook steht. Bewusst OBEN: das Renngeschehen
#: sitzt bei rund 45 % der Bildhoehe (siehe CAMERA_ANCHOR), und ein Hook in
#: der Bildmitte verdeckt genau die Teilnehmer, um die es geht.
HOOK_ZONE = (210, 470)

#: Ab hier abwaerts darf keine dauerhafte Einblendung mehr stehen, sonst
#: verdeckt sie das Rennen.
OVERLAY_FLOOR = 520

# ---------------------------------------------------------------------------
# Kamera
# ---------------------------------------------------------------------------

#: Der Fuehrende sitzt auf dieser Bildhoehe (0 = oben, 1 = unten). Darunter
#: bleibt Platz, damit man sieht, wohin die Strecke fuehrt.
CAMERA_ANCHOR = 0.45

#: Glaettung der Kamerabewegung je Bild. Klein = traege, gross = nervoes.
CAMERA_SMOOTHING = 0.16

# ---------------------------------------------------------------------------
# Farben
#
# Grundton bewusst kuehl und technisch, nicht spielzeughaft: buntes,
# kindliches Material zieht bei YouTube die Einstufung "fuer Kinder gemacht"
# nach sich, und die kostet Kommentare, Personalisierung und Erloese.
# ---------------------------------------------------------------------------

BG_TOP = (13, 16, 26)
BG_BOTTOM = (24, 21, 40)

GRID = (32, 36, 54)
GRID_ACCENT = (44, 50, 74)

TRACK = (74, 88, 120)
TRACK_HIGHLIGHT = (128, 148, 192)
PEG = (94, 80, 132)

FINISH_LIGHT = (238, 241, 248)
FINISH_DARK = (58, 64, 86)

#: Kontrollpunkt der Eliminierung (B7). Bewusst NICHT die Zielfarbe: eine
#: Kontrolllinie ist keine Ziellinie, und wer beides gleich zeichnet, macht
#: aus zwei Regeln eine. Bernstein liest sich als Warnung, ohne in die
#: Teilnehmerpalette zu fallen.
GATE = (255, 176, 59)
GATE_WIDTH = 8
GATE_DASH = 34

TEXT = (243, 245, 250)
TEXT_MUTED = (168, 178, 200)
PANEL = (0, 0, 0)
PANEL_ALPHA = 122

#: Leichte Abdunklung, wenn nur etwas Ruhe hinter den Text soll.
SCRIM_ALPHA = 118

#: Endkarte: das Rennen ist vorbei, hier darf kraeftig abgedunkelt werden.
#: Zu schwach, und eine vorbeirollende Kugel scheint durch die Tabelle.
RESULT_SCRIM_ALPHA = 224

# ---------------------------------------------------------------------------
# Teilnehmer
#
# Farbe und Name sind bewusst GETRENNT: ab Saison 2 kommen die Namen aus
# den Kommentaren, die Farbe bleibt.
#
# Die Palette ist auf Unterscheidbarkeit gebaut, nicht auf Buntheit. Rund
# acht Prozent der maennlichen Zuschauer haben eine Rot-Gruen-Schwaeche –
# ein sattes Gruen neben einem satten Rot ist fuer sie derselbe Farbklecks.
# Darum steht hier ein tuerkisstichiges Gruen statt eines Wiesengruens, und
# die fuenf Farben unterscheiden sich zusaetzlich in der Helligkeit.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Competitor:
    """Ein Teilnehmer: Kennung, Anzeigename, Farbe."""

    key: str
    name: str
    color: tuple[int, int, int]

    @property
    def dark(self) -> tuple[int, int, int]:
        """Abgedunkelte Fassung – fuer Rand und Rotationsmarke."""
        return tuple(int(c * 0.52) for c in self.color)

    @property
    def bright(self) -> tuple[int, int, int]:
        """Aufgehellte Fassung – fuer Schrift auf dunklem Grund."""
        return tuple(min(255, int(c * 1.18 + 26)) for c in self.color)


#: Die Stammbesetzung. Reihenfolge = Startnummer, nicht Rangfolge.
COMPETITORS: tuple[Competitor, ...] = (
    Competitor("red", "RED", (255, 59, 48)),
    Competitor("gold", "GOLD", (255, 179, 0)),
    Competitor("jade", "JADE", (0, 217, 163)),
    Competitor("blue", "BLUE", (46, 125, 255)),
    Competitor("violet", "VIOLET", (193, 92, 255)),
)


def competitors() -> tuple[Competitor, ...]:
    """Die aktuelle Besetzung. IMMER hierueber lesen, nie COMPETITORS
    als Standardwert in eine Funktionssignatur schreiben – der wuerde beim
    Import eingefroren und ein spaeterer Namenswechsel ginge ins Leere."""
    return COMPETITORS


def competitor(index: int) -> Competitor:
    """Teilnehmer nach Startnummer."""
    return COMPETITORS[index % len(COMPETITORS)]


#: So viele Zeichen passen sicher in die Rangliste, ohne dass der Kasten
#: ueber die halbe Bildbreite waechst.
NAME_MAX = 12


def rename(names: Iterable[str]) -> tuple[Competitor, ...]:
    """Neue Anzeigenamen, Farben bleiben (Saison 2 aufwaerts)."""
    namen = list(names)
    if len(namen) != len(COMPETITORS):
        raise ValueError(
            f"{len(COMPETITORS)} Namen erwartet, {len(namen)} bekommen"
        )
    return tuple(
        Competitor(c.key, n.strip().upper()[:NAME_MAX], c.color)
        for c, n in zip(COMPETITORS, namen)
    )


def set_competitors(comps: tuple[Competitor, ...]) -> None:
    """Besetzung austauschen (Saisonwechsel)."""
    global COMPETITORS
    if len(comps) != 5:
        raise ValueError(f"5 Teilnehmer erwartet, {len(comps)} bekommen")
    COMPETITORS = comps


# ---------------------------------------------------------------------------
# Masse der Spielfiguren und der Strecke
# ---------------------------------------------------------------------------

MARBLE_RADIUS = 32
MARBLE_OUTLINE = 5
MARBLE_MARK = 0.19        # Rotationsmarke, Anteil des Radius
MARBLE_GLOSS = 0.26       # Glanzpunkt, Anteil des Radius
TRAIL_LENGTH = 9          # Bilder Nachleuchten

TRACK_WIDTH = 18
TRACK_HIGHLIGHT_WIDTH = 4
PEG_RADIUS = 14
GRID_STEP = 160
FINISH_BAND = 14
FINISH_CHECKER = 60

# ---------------------------------------------------------------------------
# Schrift
#
# EINE Schrift fuer den ganzen Kanal. Bahnschrift ist die Windows-Fassung
# der DIN 1451 – technisch, schmal, auf kleinen Displays gut lesbar und
# nicht verspielt.
#
# ACHTUNG Wiedererkennungswert: Bahnschrift gehoert Microsoft und liegt
# nur auf Windows. Zieht die Produktion je auf eine Linux-VM um, sieht
# jedes danach gebaute Video anders aus. Wer das ausschliessen will, legt
# eine frei lizenzierte Schrift unter assets/fonts/GravityCup.ttf ab –
# die wird bevorzugt genommen, ohne dass hier etwas geaendert werden muss.
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = PROJECT_ROOT / "assets" / "fonts"
_WINDOWS_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

#: In dieser Reihenfolge gesucht. Erster Treffer gewinnt.
FONT_CANDIDATES = (
    FONT_DIR / "GravityCup.ttf",
    _WINDOWS_FONTS / "bahnschrift.ttf",
    _WINDOWS_FONTS / "seguibl.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
)

#: Nur bei Variable Fonts wirksam (Bahnschrift kann es, die meisten nicht).
FONT_VARIATION = "Bold SemiCondensed"

#: Schriftgroessen in AUSGABE-Pixeln. Das Supersampling rechnet selbst hoch.
SIZES = {
    "hook_title": 100,
    "hook_sub": 42,
    "hud_entry": 38,
    "hud_head": 28,
    "result_label": 46,
    "result_name": 116,
    "card_title": 64,
    "card_entry": 44,
    "card_points": 44,
    "badge": 30,
    # Kanalbanner und Profilbild
    "brand_title": 150,
    "brand_claim": 38,
    "brand_entry": 44,
    "brand_label": 28,
}

# Abstaende und Radien
PANEL_RADIUS = 22
PANEL_PAD = 18
HUD_ROW_HEIGHT = 62
HUD_WIDTH = 320
HUD_DOT_RADIUS = 17

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
_font_path: Path | None = None
_font_warned = False


def font_path() -> Path:
    """Pfad der tatsaechlich verwendeten Schriftdatei."""
    global _font_path, _font_warned
    if _font_path is not None:
        return _font_path
    for kandidat in FONT_CANDIDATES:
        if kandidat.exists():
            _font_path = kandidat
            if kandidat is not FONT_CANDIDATES[0] and not _font_warned:
                _font_warned = True
            return _font_path
    raise FileNotFoundError(
        "Keine Schrift gefunden. Gesucht wurde:\n  "
        + "\n  ".join(str(k) for k in FONT_CANDIDATES)
    )


def font_is_portable() -> bool:
    """True, wenn die Schrift im Projekt liegt und damit ueberall gleich ist."""
    return font_path() == FONT_CANDIDATES[0]


def font(size_key: str, scale: int = 1) -> ImageFont.FreeTypeFont:
    """Schrift in der Groesse `size_key`, bereits mit Supersampling skaliert."""
    if size_key not in SIZES:
        raise KeyError(
            f"Unbekannte Schriftgroesse {size_key!r}. Bekannt: {sorted(SIZES)}"
        )
    px = SIZES[size_key] * scale
    schluessel = (size_key, px)
    if schluessel not in _font_cache:
        f = ImageFont.truetype(str(font_path()), px)
        try:
            f.set_variation_by_name(FONT_VARIATION)
        except Exception:
            # Keine Variable Font oder Variante unbekannt – dann eben nicht.
            pass
        _font_cache[schluessel] = f
    return _font_cache[schluessel]


def describe() -> str:
    """Kurzfassung der aktiven Gestaltung – fuer Protokolle und Tests."""
    zeilen = [
        f"Ausgabe      {WIDTH}x{HEIGHT} @ {FPS} fps, Supersampling {SUPERSAMPLE}x",
        f"Schrift      {font_path()}"
        + ("" if font_is_portable() else "   [nicht im Projekt – siehe theme.py]"),
        f"Variante     {FONT_VARIATION}",
        f"Teilnehmer   " + ", ".join(f"{c.name}" for c in COMPETITORS),
        f"Sichere Zone oben {SAFE_TOP}, unten {SAFE_BOTTOM}, "
        f"links {SAFE_LEFT}, rechts {SAFE_RIGHT}",
    ]
    return "\n".join(zeilen)
