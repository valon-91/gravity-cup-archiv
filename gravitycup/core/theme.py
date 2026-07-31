#!/usr/bin/env python3
"""
theme.py – Jede Gestaltungsentscheidung des Kanals an EINER Stelle.

Kein anderes Modul legt Farben, Groessen, Abstaende oder Schriften fest.
Wer hier eine Zahl aendert, aendert sie fuer jedes kuenftige Video – das
ist Absicht: der Wiedererkennungswert des Kanals haengt daran.

CLI-Test:  python -m gravitycup.tools.probe_theme
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, replace
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
# Zwei Ausgabeformate
#
# Bis zum 30.07.2026 gab es nur Hochformat. Die Show laeuft im Vollbild –
# und das ist keine gedrehte Aufloesung, sondern ein anderes Bild: die
# sicheren Zonen oben stammen aus den SHORTS-Bedienelementen, die es in
# einem normalen Video gar nicht gibt, dafuer liegt dort unten die
# Fortschrittsleiste des Abspielers.
#
# Umgeschaltet wird zur Laufzeit wie die Besetzung, nicht ueber eine
# zweite Konstantensammlung. Grund: JEDE Zeichenfunktion liest `theme.WIDTH`
# beim Aufruf, nicht beim Import (geprueft) – zwei parallele Saetze waeren
# eine zweite Wahrheit neben der geprueften.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Format:
    """Ein Ausgabeformat samt seiner sicheren Zonen."""

    name: str
    width: int
    height: int
    safe_top: int
    safe_bottom: int
    safe_left: int
    safe_right: int
    hook_zone: tuple[int, int]
    overlay_floor: int
    hud_max_rows: int

    @property
    def quer(self) -> bool:
        return self.width > self.height


#: Hochformat – die Kurzfolgen. Genau die Werte, mit denen S01 und S02
#: gelaufen sind; hier darf sich nichts aendern.
HOCH = Format(
    name="hoch", width=1080, height=1920,
    safe_top=150, safe_bottom=420, safe_left=40, safe_right=190,
    hook_zone=(210, 470), overlay_floor=520, hud_max_rows=7,
)

#: Vollbild – die Show.
#:
#: Die Raender sind DEUTLICH kleiner, und das ist der eigentliche
#: Unterschied: SAFE_BOTTOM 420 im Hochformat sind die Shorts-Tonzeile und
#: die Knopfleiste. Ein normales Video hat davon nichts, nur unten die
#: Fortschrittsleiste, die zudem ausblendet.
#:
#: `hud_max_rows` faellt von 7 auf 6: sieben Zeilen waeren 470 px und damit
#: fast die halbe Bildhoehe von 1080. Im Hochformat sind dieselben Zeilen
#: ein Viertel.
QUER = Format(
    name="quer", width=1920, height=1080,
    safe_top=60, safe_bottom=120, safe_left=70, safe_right=70,
    hook_zone=(120, 320), overlay_floor=360, hud_max_rows=6,
)

FORMATE = {f.name: f for f in (HOCH, QUER)}

#: Das gerade eingestellte Format.
FORMAT = HOCH


def set_format(fmt: "Format | str") -> None:
    """Ausgabeformat umschalten.

    ACHTUNG beim Bauen einer Folge: das Format geht in den
    Geometrie-Fingerabdruck des Rundenarchivs ein (ueber `theme.WIDTH` in
    `build.lauf_fingerabdruck`). Eine Folge, die im falschen Format
    gerechnet wurde, ist damit als abweichend erkennbar – aber eben erst
    hinterher.
    """
    global FORMAT, WIDTH, HEIGHT, SAFE_TOP, SAFE_BOTTOM, SAFE_LEFT
    global SAFE_RIGHT, HOOK_ZONE, OVERLAY_FLOOR, HUD_MAX_ROWS
    if isinstance(fmt, str):
        if fmt not in FORMATE:
            raise ValueError(
                f"unbekanntes Format {fmt!r}, bekannt: {sorted(FORMATE)}")
        fmt = FORMATE[fmt]
    FORMAT = fmt
    WIDTH, HEIGHT = fmt.width, fmt.height
    SAFE_TOP, SAFE_BOTTOM = fmt.safe_top, fmt.safe_bottom
    SAFE_LEFT, SAFE_RIGHT = fmt.safe_left, fmt.safe_right
    HOOK_ZONE, OVERLAY_FLOOR = fmt.hook_zone, fmt.overlay_floor
    HUD_MAX_ROWS = fmt.hud_max_rows

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


#: Muster auf der Kugel. Sie sind der Grund, warum die Show mehr
#: Teilnehmer haben kann, als es unterscheidbare Farben gibt.
#:
#: Gemessen am 30.07.2026: die Stammbesetzung hat unter Rot-Gruen-Schwaeche
#: ein engstes Paar von 61,7, und schon bei 16 Farben wird es eng. 64 oder
#: 100 unterscheidbare FARBEN gibt es nicht. 64 unterscheidbare KENNUNGEN
#: schon – wenn zur Farbe ein Muster kommt.
#:
#: Die Muster drehen sich mit der Kugel mit. Das ist kein Schmuck: die
#: Rotationsmarke gibt es seit B1, weil sichtbar sein soll, dass wirklich
#: gerollt wird. Ein aufgeklebtes Muster wuerde dem widersprechen.
MUSTER = ("voll", "ring", "halb", "keil", "punkt", "doppelring", "kreuz")

#: Zweitfarben. Bewusst nur zwei, und beide unbunt: gegen einen bunten
#: Grundton sind Hell und Dunkel aus JEDER Blickrichtung verschieden –
#: auch bei Rot-Gruen-Schwaeche, wo zwei Farbtoene zusammenfallen koennen.
MUSTER_HELL = (245, 245, 245)
MUSTER_DUNKEL = (22, 22, 28)


@dataclass(frozen=True)
class Competitor:
    """Ein Teilnehmer: Kennung, Anzeigename, Farbe, Muster."""

    key: str
    name: str
    color: tuple[int, int, int]
    #: Muster aus MUSTER. "voll" ist die Stammbesetzung.
    muster: str = "voll"
    #: Farbe des Musters. Ohne Muster bedeutungslos.
    color2: tuple[int, int, int] = MUSTER_HELL

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
    """Neue Anzeigenamen, Farben UND Muster bleiben (Saison 2 aufwaerts)."""
    namen = list(names)
    if len(namen) != len(COMPETITORS):
        raise ValueError(
            f"{len(COMPETITORS)} Namen erwartet, {len(namen)} bekommen"
        )
    # `replace` statt Neubau: sonst faellt bei jedem Namenswechsel das
    # Muster auf den Vorgabewert zurueck, und zwei Teilnehmer der Show
    # waeren ab da nicht mehr unterscheidbar.
    return tuple(
        replace(c, name=n.strip().upper()[:NAME_MAX])
        for c, n in zip(COMPETITORS, namen)
    )


def set_competitors(comps: tuple[Competitor, ...]) -> None:
    """Besetzung austauschen (Saisonwechsel, Grossfeld der Show).

    Bis zum 30.07.2026 stand hier eine harte Pruefung auf genau fuenf. Sie
    stammte aus der Zeit, in der die Saisontabelle das einzige Format war.
    Die Langform ist eine eigene Show mit groesserem Feld – gemessen liegt
    der Kugel-Kugel-Anteil bei 5 Teilnehmern bei 11–16 %, bei 20 bei 46 %,
    und genau daran haengt, ob ein Rennen nach Gedraenge aussieht.

    Zwei bleibt die Untergrenze: mit einem Teilnehmer gibt es kein Rennen,
    und `rangfolge` waere sinnlos.
    """
    global COMPETITORS
    if len(comps) < 2:
        raise ValueError(
            f"mindestens 2 Teilnehmer noetig, {len(comps)} bekommen")
    if len(set(c.key for c in comps)) != len(comps):
        # Doppelte Kennungen waeren im Rundenarchiv nicht mehr aufloesbar –
        # und das Archiv ist der Beleg, mit dem der Kanal sein Versprechen
        # einloest.
        raise ValueError("Teilnehmerkennungen muessen eindeutig sein")
    COMPETITORS = comps


# ---------------------------------------------------------------------------
# Grossfeld
#
# Die Stammbesetzung ist auf fuenf ausgelegt und von Hand auf
# Unterscheidbarkeit gebaut. Fuer die Show braucht es mehr, und „mehr Farben"
# ist genau die Stelle, an der eine erzeugte Regenbogenpalette
# auseinanderfaellt: benachbarte Farbtoene sehen auf einem Handy im Hellen
# gleich aus, und bei Rot-Gruen-Schwaeche sowieso.
#
# Deshalb steht hier eine ausgeschriebene Liste statt einer Formel, und
# `farbabstand` misst nach, wie dicht die engste Paarung wirklich liegt.
# Die ersten fuenf sind die Stammbesetzung – die Show soll wie GRAVITY CUP
# aussehen, nicht wie ein anderes Format.
# ---------------------------------------------------------------------------

#: Die elf zusaetzlichen Farben sind AUSGERECHNET, nicht ausgesucht: aus
#: einem Farbgitter jeweils die, die den groessten Mindestabstand zu allen
#: schon gewaehlten hat – und zwar gemessen unter Normalsicht UND unter
#: simulierter Rot-Gruen-Schwaeche, der kleinere Wert zaehlt.
#:
#: Der erste Versuch war eine Liste nach Augenmass. `engste_paarung` hat sie
#: sofort zerlegt: GOLD/AMBER lagen bei 108, SAND/PEACH bei 55 – bei einer
#: Stammbesetzung, deren engstes Paar normalsichtig bei 240 liegt. Genau
#: dafuer steht die Messung hier.
GROSSFELD: tuple[Competitor, ...] = COMPETITORS + (
    Competitor("maroon", "MAROON", (140, 0, 0)),
    Competitor("snow", "SNOW", (245, 245, 245)),
    Competitor("navy", "NAVY", (0, 0, 140)),
    Competitor("lime", "LIME", (201, 242, 121)),
    Competitor("moss", "MOSS", (88, 140, 70)),
    Competitor("cobalt", "COBALT", (0, 32, 242)),
    Competitor("rust", "RUST", (191, 50, 0)),
    Competitor("fern", "FERN", (0, 140, 56)),
    Competitor("mauve", "MAUVE", (191, 95, 146)),
    Competitor("teal", "TEAL", (0, 130, 140)),
    Competitor("orchid", "ORCHID", (234, 121, 242)),
)


def farbabstand(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """Grober Wahrnehmungsabstand zweier Farben (Redmean-Naeherung).

    Kein echtes CIE-Delta-E – dafuer braeuchte es eine Farbraumbibliothek,
    und die Naeherung reicht fuer die Frage „sehen diese beiden auf einem
    Handy gleich aus". Wichtig ist, dass ueberhaupt GEMESSEN wird: eine
    Palette nach Augenmass hat niemand geprueft, und auffallen wuerde es
    erst im fertigen Video.
    """
    rm = (a[0] + b[0]) / 2
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return math.sqrt((2 + rm / 256) * dr * dr
                     + 4 * dg * dg
                     + (2 + (255 - rm) / 256) * db * db)


#: Naeherungen fuer Deuteranopie und Protanopie – die beiden Formen der
#: Rot-Gruen-Schwaeche, die zusammen rund acht Prozent der maennlichen
#: Zuschauer betreffen. Lineare Matrizen auf sRGB, keine exakte Simulation,
#: aber sie beantworten die Frage „fallen diese beiden Farben zusammen".
_SEHWEISEN = {
    "normal": (1, 0, 0, 0, 1, 0, 0, 0, 1),
    "deuteranopie": (0.625, 0.375, 0, 0.70, 0.30, 0, 0, 0.30, 0.70),
    "protanopie": (0.567, 0.433, 0, 0.558, 0.442, 0, 0, 0.242, 0.758),
}


def sehweise(farbe: tuple[int, int, int], art: str) -> tuple[float, float, float]:
    """Farbe, wie sie mit der jeweiligen Farbwahrnehmung ankommt."""
    r, g, b = farbe
    m = _SEHWEISEN[art]
    return (m[0] * r + m[1] * g + m[2] * b,
            m[3] * r + m[4] * g + m[5] * b,
            m[6] * r + m[7] * g + m[8] * b)


def unterscheidbarkeit(a: tuple[int, int, int],
                       b: tuple[int, int, int]) -> float:
    """Abstand zweier Farben im UNGUENSTIGSTEN der drei Sehweisen."""
    return min(farbabstand(sehweise(a, art), sehweise(b, art))
               for art in _SEHWEISEN)


def engste_paarung(comps: tuple[Competitor, ...],
                   nur_normalsicht: bool = False) -> tuple[float, str, str]:
    """(Abstand, Name, Name) des am schwersten unterscheidbaren Paares.

    Standardmaessig gegen alle drei Sehweisen. Dabei faellt auf, dass die
    STAMMBESETZUNG selbst nicht besonders gut dasteht: JADE und BLUE liegen
    normalsichtig 251 auseinander, bei Rot-Gruen-Schwaeche nur 62. Das
    tuerkisstichige Gruen aus dem Modulkopf vermeidet den Konflikt mit RED
    und handelt sich dafuer einen mit BLUE ein. Bekannt, nicht behoben –
    S01 und S02 laufen damit, und ein Farbwechsel mitten in einer Saison
    waere schlimmer als das Problem.
    """
    schlechtestes = (float("inf"), "", "")
    for i, a in enumerate(comps):
        for b in comps[i + 1:]:
            d = (farbabstand(a.color, b.color) if nur_normalsicht
                 else unterscheidbarkeit(a.color, b.color))
            if d < schlechtestes[0]:
                schlechtestes = (d, a.name, b.name)
    return schlechtestes


def grossfeld(n: int) -> tuple[Competitor, ...]:
    """Die ersten `n` Teilnehmer des Grossfelds."""
    if not 2 <= n <= len(GROSSFELD):
        raise ValueError(
            f"Grossfeld fasst 2 bis {len(GROSSFELD)} Teilnehmer, {n} verlangt")
    return GROSSFELD[:n]


# ---------------------------------------------------------------------------
# Das Feld der Show
# ---------------------------------------------------------------------------

def kontrastfarbe(grund: tuple[int, int, int]) -> tuple[int, int, int]:
    """Hell oder Dunkel – was sich von `grund` staerker abhebt.

    Feste Musterfarben waren der erste Entwurf, und die Messung hat ihn
    zerlegt: SNOW ist (245,245,245) und die helle Musterfarbe ebenfalls –
    ein weisses Muster auf weisser Kugel, gemessener Abstand 0,0. Der
    Kontrast muss aus der Grundfarbe folgen, nicht aus einer Tabelle.
    """
    return max((MUSTER_HELL, MUSTER_DUNKEL),
               key=lambda z: unterscheidbarkeit(grund, z))


#: Reihenfolge der Muster. Erst alle sechzehn Farben voll – das ist die
#: vertraute Besetzung –, dann dieselben Farben mit Ring, Halb, Keil und so
#: weiter.
#:
#: Musterweise, nicht farbweise: so sind bei JEDER Feldgroesse alle
#: sechzehn Farben im Spiel. Farbweise waeren die ersten sechzehn
#: Teilnehmer alle rot.
_VARIANTEN = MUSTER

#: So viele Kennungen gibt es hoechstens: 7 Muster x 16 Farben. Ausgelegt
#: auf ueber hundert, damit ein spaeterer Sprung von 64 auf 100 Teilnehmer
#: nichts kostet ausser Rechenzeit.
FELD_MAX = len(_VARIANTEN) * len(GROSSFELD)

_MUSTER_KUERZEL = {"voll": "", "ring": "O", "halb": "H", "keil": "K",
                   "punkt": "P", "doppelring": "OO", "kreuz": "X"}


def feld(n: int) -> tuple[Competitor, ...]:
    """`n` unterscheidbare Teilnehmer aus Farbe und Muster.

    Die ersten sechzehn sind die vollen Farben und damit dieselbe
    Besetzung wie bisher – die Show soll wie GRAVITY CUP aussehen.
    """
    if not 2 <= n <= FELD_MAX:
        raise ValueError(f"Feld fasst 2 bis {FELD_MAX} Teilnehmer, {n} verlangt")
    aus: list[Competitor] = []
    for muster in _VARIANTEN:
        for c in GROSSFELD:
            if len(aus) >= n:
                break
            if muster == "voll":
                aus.append(c)
                continue
            aus.append(replace(
                c,
                key=f"{c.key}-{muster}",
                name=f"{c.name} {_MUSTER_KUERZEL[muster]}"[:NAME_MAX].strip(),
                muster=muster, color2=kontrastfarbe(c.color)))
        if len(aus) >= n:
            break
    return tuple(aus[:n])


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

#: So viele Zeilen zeigt die Rangliste hoechstens. Darueber werden nur
#: Kopf und Fuss gezeigt, dazwischen eine Trennzeile mit der Anzahl.
#:
#: Sieben mal 62 px plus Rand sind rund 470 px – dasselbe Budget wie die
#: fuenf Zeilen heute (gemessen 150..496). Mehr ginge nicht, ohne dass die
#: Rangliste noch mehr Kugeln verdeckt, als sie es ohnehin schon tut.
HUD_MAX_ROWS = 7
#: Kopf = die Fuehrenden, Fuss = die, die als Naechstes rausfliegen. Der
#: Fuss ist bei der Eliminierung der wichtigere Teil.
HUD_KOPF = 3
HUD_FUSS = 3
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
