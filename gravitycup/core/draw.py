#!/usr/bin/env python3
"""
draw.py – Zeichenprimitive, Kamera und Einblendungen.

Alle Masse und Farben kommen aus theme.py; dieses Modul entscheidet nichts
selbst. Es kennt zwei Koordinatensysteme:

  WELT   – die Strecke. y waechst nach unten und laeuft ueber die ganze
           Streckenlaenge. Wird ueber die Kamera ins Bild gerechnet.
  BILD   – das fertige Hochformat 1080x1920. Einblendungen (HUD, Hook,
           Ergebniskarte) leben hier und bewegen sich nicht mit.

Das Supersampling ist gekapselt: nach aussen wird IMMER in Ausgabe-Pixeln
gerechnet, die Klasse skaliert selbst hoch und am Ende wieder herunter.

CLI-Test:  python -m gravitycup.tools.probe_theme
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from . import theme


# ---------------------------------------------------------------------------
# Kamera
# ---------------------------------------------------------------------------


@dataclass
class Camera:
    """Senkrecht mitlaufende Kamera mit Glaettung und Klemmung.

    `top` ist die Weltkoordinate, die gerade am oberen Bildrand steht.
    """

    top: float = 0.0
    anchor: float = theme.CAMERA_ANCHOR
    smoothing: float = theme.CAMERA_SMOOTHING
    limit_bottom: float | None = None

    @classmethod
    def start_at(cls, lead_y: float, **kw) -> "Camera":
        """Kamera so setzen, dass der Fuehrende sofort am Ankerpunkt steht."""
        cam = cls(**kw)
        cam.top = cam._target(lead_y)
        return cam

    def _target(self, lead_y: float) -> float:
        ziel = lead_y - theme.HEIGHT * self.anchor
        if self.limit_bottom is not None:
            ziel = min(ziel, self.limit_bottom - theme.HEIGHT * 0.62)
        return ziel

    def follow(self, lead_y: float) -> float:
        """Ein Bild weiter. Liefert die neue Oberkante."""
        self.top += (self._target(lead_y) - self.top) * self.smoothing
        return self.top

    def to_screen(self, y: float) -> float:
        """Welt-y -> Bild-y."""
        return y - self.top

    def visible(self, y: float, rand: float = 200.0) -> bool:
        s = self.to_screen(y)
        return -rand <= s <= theme.HEIGHT + rand

    def overlaps(self, y_a: float, y_b: float, rand: float = 200.0) -> bool:
        """Ragt die Strecke von y_a bis y_b ins Bild?

        Nicht dasselbe wie „ein Ende ist sichtbar". Die Seitenwaende laufen
        von y=0 bis y=5680 durch die ganze Strecke; bei beiden Enden weit
        ausserhalb des Bildes meldete `visible()` fuer jedes Ende False –
        und die Waende wurden im Grossteil des Rennens nicht gezeichnet.
        Ein Stueck ist sichtbar, wenn es das Sichtband SCHNEIDET.
        """
        oben, unten = (y_a, y_b) if y_a <= y_b else (y_b, y_a)
        return (self.to_screen(unten) >= -rand
                and self.to_screen(oben) <= theme.HEIGHT + rand)


# ---------------------------------------------------------------------------
# Zeichenflaeche
# ---------------------------------------------------------------------------

_gradient_cache: dict[tuple[int, int], Image.Image] = {}


def _gradient(w: int, h: int) -> Image.Image:
    """Senkrechter Verlauf, einmal gebaut und danach nur noch kopiert."""
    key = (w, h)
    if key not in _gradient_cache:
        streifen = Image.new("RGB", (1, h))
        oben, unten = theme.BG_TOP, theme.BG_BOTTOM
        streifen.putdata([
            tuple(
                int(oben[i] + (unten[i] - oben[i]) * (y / max(1, h - 1)))
                for i in range(3)
            )
            for y in range(h)
        ])
        _gradient_cache[key] = streifen.resize((w, h))
    return _gradient_cache[key]


@dataclass
class Canvas:
    """Ein Einzelbild. Alle Angaben in Ausgabe-Pixeln."""

    scale: int = theme.SUPERSAMPLE
    camera: Camera = field(default_factory=Camera)
    image: Image.Image = field(init=False)
    draw: ImageDraw.ImageDraw = field(init=False)

    def __post_init__(self) -> None:
        self.image = _gradient(theme.WIDTH * self.scale,
                               theme.HEIGHT * self.scale).copy()
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    # -- Koordinaten ------------------------------------------------------

    def s(self, v: float) -> float:
        """Ausgabe-Pixel -> interne Pixel."""
        return v * self.scale

    def wx(self, x: float) -> float:
        """Welt-x -> interne Pixel."""
        return x * self.scale

    def wy(self, y: float) -> float:
        """Welt-y -> interne Pixel (ueber die Kamera)."""
        return self.camera.to_screen(y) * self.scale

    def font(self, key: str):
        return theme.font(key, self.scale)

    # -- Grundelemente ----------------------------------------------------

    def grid(self) -> None:
        """Mitlaufendes Raster – gibt dem freien Fall einen Tiefenhinweis."""
        step = theme.GRID_STEP
        y = math.floor(self.camera.top / step) * step
        ende = self.camera.top + theme.HEIGHT + step
        breite = max(1, int(self.s(2)))
        i = 0
        while y < ende:
            # jede fuenfte Linie etwas heller: macht die Geschwindigkeit lesbar
            farbe = theme.GRID_ACCENT if int(y // step) % 5 == 0 else theme.GRID
            self.draw.line(
                [(0, self.wy(y)), (self.image.width, self.wy(y))],
                fill=farbe, width=breite,
            )
            y += step
            i += 1

    def track_segment(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Ein Streckenstueck mit Glanzkante und runden Enden."""
        if not self.camera.overlaps(y1, y2):
            return
        p1 = (self.wx(x1), self.wy(y1))
        p2 = (self.wx(x2), self.wy(y2))
        w = self.s(theme.TRACK_WIDTH)
        self.draw.line([p1, p2], fill=theme.TRACK, width=int(w))
        # runde Enden – PIL kann keine Linienkappen
        r = w / 2
        for (px, py) in (p1, p2):
            self.draw.ellipse([px - r, py - r, px + r, py + r], fill=theme.TRACK)
        # Glanzkante oben drauf
        versatz = self.s(5)
        self.draw.line(
            [(p1[0], p1[1] - versatz), (p2[0], p2[1] - versatz)],
            fill=theme.TRACK_HIGHLIGHT,
            width=int(self.s(theme.TRACK_HIGHLIGHT_WIDTH)),
        )

    def peg(self, x: float, y: float, radius: float | None = None) -> None:
        """Ein Umlenkstift.

        `radius` kommt aus der Physik (physics.Peg.radius). Wird er nicht
        angegeben, gilt der Hausmasstab. Ohne diesen Durchgriff zeichnet das
        Bild einen anderen Stift als den, an dem die Kugel abprallt.
        """
        if not self.camera.visible(y, rand=100):
            return
        r = self.s(theme.PEG_RADIUS if radius is None else radius)
        cx, cy = self.wx(x), self.wy(y)
        self.draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=theme.PEG)
        # kleiner Lichtpunkt, damit die Stifte nicht flach wirken
        hr = r * 0.34
        self.draw.ellipse(
            [cx - r * 0.30 - hr, cy - r * 0.34 - hr,
             cx - r * 0.30 + hr, cy - r * 0.34 + hr],
            fill=(255, 255, 255, 46),
        )

    def finish_line(self, y: float) -> None:
        """Zielband im Schachbrettmuster."""
        if not self.camera.visible(y):
            return
        sy = self.wy(y)
        band = self.s(theme.FINISH_BAND)
        kachel = self.s(theme.FINISH_CHECKER)
        x = 0.0
        i = 0
        while x < self.image.width:
            farbe = theme.FINISH_LIGHT if i % 2 == 0 else theme.FINISH_DARK
            self.draw.rectangle([x, sy - band, x + kachel, sy + band], fill=farbe)
            x += kachel
            i += 1

    def muster(self, comp: theme.Competitor, cx: float, cy: float, r: float,
               angle: float, ein) -> None:
        """Das Muster auf der Kugel, in Ausgabe-Koordinaten.

        Warum es das gibt: 64 unterscheidbare FARBEN gibt es nicht – die
        Stammbesetzung hat unter Rot-Gruen-Schwaeche schon bei fuenf ein
        engstes Paar von 61,7, und ab sechzehn wird es eng. Mit Muster
        reichen sechzehn Farben fuer ueber hundert Kennungen.

        Die Muster DREHEN SICH MIT. Die Rotationsmarke gibt es seit B1,
        weil sichtbar sein soll, dass wirklich gerollt wird; ein
        aufgeklebtes Muster wuerde dem widersprechen.
        """
        if comp.muster == "voll":
            return
        f = ein(comp.color2)
        kasten = [cx - r, cy - r, cx + r, cy + r]
        grad = math.degrees(angle)

        if comp.muster == "ring":
            breite = max(1, int(r * 0.20))
            rr = r * 0.66
            self.draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                              outline=f, width=breite)
        elif comp.muster == "halb":
            self.draw.pieslice(kasten, grad, grad + 180, fill=f)
        elif comp.muster == "keil":
            self.draw.pieslice(kasten, grad - 46, grad + 46, fill=f)
        elif comp.muster == "doppelring":
            breite = max(1, int(r * 0.13))
            for anteil in (0.80, 0.44):
                rr = r * anteil
                self.draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                                  outline=f, width=breite)
        elif comp.muster == "kreuz":
            for versatz in (0, 180):
                self.draw.pieslice(kasten, grad + versatz - 22,
                                   grad + versatz + 22, fill=f)
        elif comp.muster == "punkt":
            # Zwei gegenueberliegende Punkte: einer allein waere bei
            # halber Drehung hinter der Kugel und die Kennung verschwaende.
            pr = r * 0.30
            for versatz in (0.0, math.pi):
                px = cx + math.cos(angle + versatz) * r * 0.48
                py = cy + math.sin(angle + versatz) * r * 0.48
                self.draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=f)

    def marble(self, comp: theme.Competitor, x: float, y: float,
               angle: float = 0.0, trail: list[tuple[float, float]] | None = None,
               alpha: int = 255, radius: float | None = None) -> None:
        """Ein Teilnehmer samt Nachleuchten.

        `alpha` blendet die ganze Kugel aus – gebraucht ab B7, wo
        ausgeschiedene Teilnehmer verschwinden statt einfach stehen zu
        bleiben. `radius` laesst sie dabei zugleich schrumpfen.
        """
        if alpha <= 0:
            return
        r = self.s(theme.MARBLE_RADIUS if radius is None else radius)

        def ein(farbe, a: int = 255):
            return tuple(farbe) + (min(255, a * alpha // 255),)

        if trail:
            n = len(trail)
            for k, (tx, ty) in enumerate(trail):
                anteil = (k + 1) / n
                a = int(16 + 54 * anteil)
                rr = r * (0.30 + 0.42 * anteil)
                px, py = self.wx(tx), self.wy(ty)
                self.draw.ellipse([px - rr, py - rr, px + rr, py + rr],
                                  fill=ein(comp.color, a))

        cx, cy = self.wx(x), self.wy(y)
        self.draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ein(comp.color))
        self.muster(comp, cx, cy, r, angle, ein)
        self.draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                          outline=ein(comp.dark),
                          width=int(self.s(theme.MARBLE_OUTLINE)))

        # Rotationsmarke: macht sichtbar, dass wirklich gerollt wird
        mx = cx + math.cos(angle) * r * 0.5
        my = cy + math.sin(angle) * r * 0.5
        mr = r * theme.MARBLE_MARK
        self.draw.ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=ein(comp.dark))

        # Glanzpunkt
        hr = r * theme.MARBLE_GLOSS
        hx, hy = cx - r * 0.33, cy - r * 0.36
        self.draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr],
                          fill=ein((255, 255, 255), 122))

    def sperre(self, x1: float, y1: float, x2: float, y2: float,
               radius: float, alpha: int = 255) -> None:
        """Eine geschlossene Sperre (Arena).

        Bewusst anders als ein Streckenstueck: die Warnfarbe und eine
        Schraffur. Der Zuschauer muss auf den ersten Blick sehen, dass DAS
        gleich aufgeht – sonst wirkt das aufgestaute Feld wie ein Fehler.
        """
        if alpha <= 0 or not self.camera.overlaps(y1, y2):
            return
        p1 = (self.wx(x1), self.wy(y1))
        p2 = (self.wx(x2), self.wy(y2))
        w = self.s(radius * 2)
        self.draw.line([p1, p2], fill=theme.GATE + (alpha,),
                       width=int(w), joint="curve")
        # Schraffur quer zur Sperre
        laenge = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if laenge < 1:
            return
        ux, uy = (p2[0] - p1[0]) / laenge, (p2[1] - p1[1]) / laenge
        schritt = max(self.s(26), 6)
        n = int(laenge // schritt)
        dunkel = tuple(int(c * 0.45) for c in theme.GATE) + (alpha,)
        for k in range(n + 1):
            mx = p1[0] + ux * k * schritt
            my = p1[1] + uy * k * schritt
            self.draw.line([(mx - uy * w / 2 - ux * w * 0.35,
                             my + ux * w / 2 - uy * w * 0.35),
                            (mx - uy * -w / 2 + ux * w * 0.35,
                             my + ux * -w / 2 + uy * w * 0.35)],
                           fill=dunkel, width=max(1, int(self.s(3))))

    def rotor(self, rot, zeit: float, alpha: int = 255) -> None:
        """Ein drehendes Kreuz.

        Bewusst nicht in der Streckenfarbe: der Zuschauer muss sehen, dass
        sich DAS bewegt und nicht er selbst. Ein Rotor, der aussieht wie
        eine Wand, wirkt wie ein Bildfehler.
        """
        if alpha <= 0 or not self.camera.visible(rot.y):
            return
        mx, my = self.wx(rot.x), self.wy(rot.y)
        w = self.s(rot.radius * 2)
        for ex, ey in rot.enden(zeit):
            self.draw.line([(mx, my), (self.wx(ex), self.wy(ey))],
                           fill=theme.GATE + (alpha,), width=int(w),
                           joint="curve")
        nabe = self.s(rot.radius * 1.6)
        self.draw.ellipse([mx - nabe, my - nabe, mx + nabe, my + nabe],
                          fill=tuple(int(c * 0.5) for c in theme.GATE)
                          + (alpha,))

    def gate_line(self, y: float, alpha: int = 255,
                  label: str | None = None) -> None:
        """Kontrollpunkt der Eliminierung – eine Linie quer durch die Bahn.

        Bewusst anders als die Ziellinie: gestrichelt statt Schachbrett, in
        der Warnfarbe. Wer sie ueberquert, ist durch; wer als Letzter davor
        steht, ist raus. Ohne die Linie sieht der Zuschauer das Ausscheiden,
        versteht aber nicht, wodurch es ausgeloest wurde.
        """
        if alpha <= 0 or not self.camera.visible(y, rand=80):
            return
        sy = self.wy(y)
        dicke = self.s(theme.GATE_WIDTH)
        strich = self.s(theme.GATE_DASH)
        x = 0.0
        an = True
        while x < self.image.width:
            if an:
                self.draw.rectangle([x, sy - dicke / 2, x + strich, sy + dicke / 2],
                                    fill=theme.GATE + (alpha,))
            x += strich
            an = not an
        if label:
            self.text(theme.SAFE_LEFT + 10, self.camera.to_screen(y) - 30,
                      label, "badge", fill=theme.GATE, anchor="lm", alpha=alpha)

    def slot_value(self, x_von: float, x_bis: float, y: float, wert: int,
                   hoch: bool = False, alpha: int = 255) -> None:
        """Punktwert eines Landefachs (B8).

        Steht IM Fach, nicht daneben: der Zuschauer muss beim Aufschlag
        sofort sehen, was die Kugel wert war, ohne den Blick zu wandern.
        Die hohen Faecher am Rand werden hervorgehoben – sie sind der
        Grund, warum man zuschaut.
        """
        if alpha <= 0 or not self.camera.visible(y, rand=260):
            return
        farbe = theme.GATE if hoch else theme.TEXT_MUTED
        self.text((x_von + x_bis) / 2, self.camera.to_screen(y),
                  str(wert), "result_label" if hoch else "card_entry",
                  fill=farbe, anchor="mm", alpha=alpha)

    # -- Einblendungen (Bildkoordinaten, bewegen sich nicht mit) -----------

    def panel(self, box: tuple[float, float, float, float],
              alpha: int = theme.PANEL_ALPHA, radius: float = theme.PANEL_RADIUS) -> None:
        """Abgerundete Unterlegung fuer Text."""
        x1, y1, x2, y2 = box
        self.draw.rounded_rectangle(
            [self.s(x1), self.s(y1), self.s(x2), self.s(y2)],
            radius=self.s(radius), fill=theme.PANEL + (alpha,),
        )

    def text(self, x: float, y: float, inhalt: str, size_key: str,
             fill=theme.TEXT, anchor: str = "lm", alpha: int | None = None) -> None:
        """Text in Ausgabe-Koordinaten."""
        farbe = tuple(fill) + ((alpha,) if alpha is not None else ())
        self.draw.text((self.s(x), self.s(y)), inhalt,
                       font=self.font(size_key), fill=farbe, anchor=anchor)

    def text_centered(self, y: float, inhalt: str, size_key: str,
                      fill=theme.TEXT, alpha: int | None = None) -> None:
        self.text(theme.WIDTH / 2, y, inhalt, size_key, fill, anchor="mm", alpha=alpha)

    def measure(self, inhalt: str, size_key: str) -> tuple[float, float]:
        """Breite und Hoehe eines Textes in AUSGABE-Pixeln."""
        f = self.font(size_key)
        kasten = self.draw.textbbox((0, 0), inhalt, font=f, anchor="lt")
        return ((kasten[2] - kasten[0]) / self.scale,
                (kasten[3] - kasten[1]) / self.scale)

    def scrim(self, alpha: int = theme.SCRIM_ALPHA) -> None:
        """Ganzflaechige Abdunklung – Grundlage der Ergebniskarte."""
        self.draw.rectangle([0, 0, self.image.width, self.image.height],
                            fill=theme.PANEL + (alpha,))

    @staticmethod
    def hud_zeilen(order: list[int]) -> list[tuple[int, int | None]]:
        """Welche Zeilen die Rangliste zeigt: (Rang, Teilnehmer).

        Als eigene Funktion, damit sie ohne Bild pruefbar ist – die
        Rangliste hat schon zweimal etwas verdeckt, was niemand gemessen
        hatte.

        `(k, None)` ist die Trennzeile und sagt, wie viele dazwischen
        ausgelassen sind.
        """
        if len(order) <= theme.HUD_MAX_ROWS:
            return [(r, i) for r, i in enumerate(order)]
        kopf, fuss = theme.HUD_KOPF, theme.HUD_FUSS
        ausgelassen = len(order) - kopf - fuss
        zeilen: list[tuple[int, int | None]] = [
            (r, order[r]) for r in range(kopf)]
        zeilen.append((ausgelassen, None))
        zeilen += [(r, order[r]) for r in range(len(order) - fuss, len(order))]
        return zeilen

    #: Waagrechte Masse der Rangliste, gerechnet ab dem linken Panelrand.
    HUD_PUNKT_X = 34          # Mitte des Farbpunkts
    HUD_RANG_X = 66           # linke Kante der Platzziffer
    HUD_SPALTENLUFT = 16      # zwischen Platzziffer und Name
    HUD_RAND = 28             # rechts neben dem laengsten Namen

    def hud_spalten(self, zeilen, comps) -> tuple[float, float, float]:
        """Wo Platzziffer und Name beginnen, und wie breit der Kasten wird.

        Als eigene Funktion, damit sie ohne Bild pruefbar ist – wie
        `hud_zeilen`, und aus demselben Grund.

        Die Namensspalte stand fest bei 108 px. Das reichte fuer zwei
        Stellen und war nie falsch, solange fuenf oder vierundsechzig
        antraten. Bei HUNDERT schob sich die Platzziffer in den Namen:
        gemessen in der Vorschau vom 31.07.2026 stand dort woertlich
        "100GOLD K".

        Dieselbe Fehlerklasse, die dieses Projekt in der Physik fuenfmal
        getroffen hat – ein Mass, das fuer ein kleineres Feld ausgelegt
        war. Deshalb steht die Spalte jetzt hinter der laengsten wirklich
        vorkommenden Platzziffer, statt hinter einer Zahl.
        """
        ziffern = max(
            (self.measure(f"{rang + 1}", "hud_entry")[0]
             for rang, idx in zeilen if idx is not None),
            default=0,
        )
        namen = max(
            (self.measure(comps[idx].name, "hud_entry")[0]
             for _, idx in zeilen if idx is not None),
            default=0,
        )
        namen_x = self.HUD_RANG_X + ziffern + self.HUD_SPALTENLUFT
        breite = max(theme.HUD_WIDTH, namen_x + namen + self.HUD_RAND)
        return self.HUD_RANG_X, namen_x, breite

    def hud_ranking(self, order: list[int], comps=None,
                    alpha: int = 255, top: float | None = None,
                    raus: set[int] | None = None) -> None:
        """Laufende Rangliste oben links.

        `order` sind Teilnehmer-Indizes, Fuehrender zuerst.
        `raus` sind Ausgeschiedene (B7) – sie stehen weiter in der Liste,
        aber gedaempft. Sie ganz zu streichen waere falsch: der Zuschauer
        soll sehen, WER schon raus ist, nicht nur dass jemand fehlt.
        """
        raus = raus or set()
        if alpha <= 0:
            return
        comps = comps or theme.competitors()
        x = theme.SAFE_LEFT + 4
        y = theme.SAFE_TOP if top is None else top

        # Bei grossem Feld nur Kopf und Fuss zeigen.
        #
        # Fuenf Zeilen passen; sechzehn nicht – bei 62 px je Zeile waeren das
        # 1042 px, mehr als die halbe Bildhoehe, und die Rangliste verdeckt
        # ohnehin schon Kugeln (bekannter offener Punkt).
        #
        # Gezeigt werden die VORDERSTEN und die LETZTEN, nicht die
        # vordersten allein. Bei der Eliminierung faellt die Entscheidung
        # hinten: wer als Letzter am Tor ankommt, ist raus. Eine Liste, die
        # nur die Spitze zeigt, blendet genau das aus, worum es geht.
        zeilen = self.hud_zeilen(order)
        hoehe = theme.HUD_ROW_HEIGHT * len(zeilen) + theme.PANEL_PAD * 2

        rang_x, namen_x, breite = self.hud_spalten(zeilen, comps)
        breite = min(breite, theme.WIDTH - theme.SAFE_RIGHT - x)
        self.panel((x, y, x + breite, y + hoehe),
                   alpha=int(theme.PANEL_ALPHA * alpha / 255))

        for zeile, (rang, idx) in enumerate(zeilen):
            if idx is None:
                # Trennzeile: wie viele dazwischen ausgelassen sind.
                zeile_y = (y + theme.PANEL_PAD
                           + theme.HUD_ROW_HEIGHT * zeile
                           + theme.HUD_ROW_HEIGHT / 2)
                self.text(x + rang_x, zeile_y, f"+{rang}", "hud_entry",
                          fill=theme.TEXT_MUTED, anchor="lm", alpha=alpha // 2)
                continue
            comp = comps[idx]
            draussen = idx in raus
            a = alpha // 3 if draussen else alpha
            zeile_y = y + theme.PANEL_PAD + theme.HUD_ROW_HEIGHT * zeile \
                + theme.HUD_ROW_HEIGHT / 2
            r = theme.HUD_DOT_RADIUS
            cx = x + self.HUD_PUNKT_X
            self.draw.ellipse(
                [self.s(cx - r), self.s(zeile_y - r),
                 self.s(cx + r), self.s(zeile_y + r)],
                fill=comp.color + (a,),
            )
            self.text(x + rang_x, zeile_y, f"{rang + 1}", "hud_entry",
                      fill=theme.TEXT_MUTED, anchor="lm", alpha=a)
            self.text(x + namen_x, zeile_y, comp.name, "hud_entry",
                      fill=theme.TEXT, anchor="lm", alpha=a)
            if draussen:
                # Durchgestrichen. Nur abzudunkeln reicht nicht – auf einem
                # Handy im Hellen sieht gedaempft aus wie „steht hinten".
                breite_name = self.measure(comp.name, "hud_entry")[0]
                self.draw.line(
                    [self.s(x + namen_x - 6), self.s(zeile_y),
                     self.s(x + namen_x + breite_name + 4), self.s(zeile_y)],
                    fill=theme.TEXT_MUTED + (a,), width=max(1, int(self.s(3))))

    def hook_layout(self, titel: str, unterzeile: str = "") -> dict:
        """Rechnet den Aufhaenger aus, ohne ihn zu zeichnen.

        Getrennt vom Zeichnen, damit Tests nachrechnen koennen, dass keine
        Zeile aus ihrem Kasten laeuft. Im Prototyp war der Kasten auf feste
        Werte gesetzt und die zweite Zeile stand halb ausserhalb – genau das
        soll hier nicht wieder passieren.
        """
        zeilen = _wrap(titel, 13)
        _, titel_h = self.measure("Hg", "hook_title")
        sub_h = self.measure("Hg", "hook_sub")[1] if unterzeile else 0.0

        zeilen_abstand = titel_h * 1.06
        block_h = zeilen_abstand * len(zeilen)
        if unterzeile:
            block_h += sub_h * 1.9

        oben, unten = theme.HOOK_ZONE
        mitte = (oben + unten) / 2
        pad_y = 30
        kasten = (
            theme.SAFE_LEFT + 26,
            mitte - block_h / 2 - pad_y,
            theme.WIDTH - theme.SAFE_LEFT - 26,
            mitte + block_h / 2 + pad_y,
        )

        positionen = []
        y = mitte - block_h / 2 + zeilen_abstand / 2
        for zeile in zeilen:
            positionen.append((y, zeile, "hook_title"))
            y += zeilen_abstand
        if unterzeile:
            positionen.append((y + sub_h * 0.45, unterzeile, "hook_sub"))

        return {"box": kasten, "lines": positionen}

    def hook(self, titel: str, unterzeile: str = "", alpha: int = 255) -> dict:
        """Aufhaenger der ersten Sekunden.

        Steht bewusst OBEN im Bild: die Teilnehmer sitzen bei rund 45 % der
        Hoehe, ein Kasten in der Bildmitte wuerde genau sie verdecken.
        """
        layout = self.hook_layout(titel, unterzeile)
        if alpha <= 0:
            return layout
        self.panel(layout["box"], alpha=int(min(alpha, 168)), radius=30)
        for y, text, size_key in layout["lines"]:
            farbe = theme.TEXT if size_key == "hook_title" else theme.TEXT_MUTED
            self.text_centered(y, text, size_key, fill=farbe, alpha=alpha)
        return layout

    @staticmethod
    def endkarte_zeilen(anzahl: int, tabelle_y: float, zeile_h: float,
                        bildhoehe: float) -> tuple[int, bool]:
        """Wie viele Tabellenzeilen der Endkarte ins Bild passen.

        Liefert (gezeigte Zeilen, gekuerzt?). Bei Kuerzung ist eine der
        passenden Zeilen fuer den "+N"-Vermerk reserviert. Als reine
        Funktion herausgeloest, damit die Eigenschaft „die Endkarte
        bleibt im Bild" testbar ist, ohne eine Leinwand zu bauen.
        """
        frei = bildhoehe - 40 - tabelle_y - 2 * theme.PANEL_PAD
        passt = max(2, int(frei // zeile_h))
        if anzahl <= passt:
            return anzahl, False
        return passt - 1, True

    def result_card(self, order: list[int], comps=None,
                    alpha: int = 255, label: str = "WINNER",
                    points: list[int] | None = None) -> None:
        """Endkarte: Sieger gross, darunter die Reihenfolge dieser Runde.

        `points` ist optional – ab Baustein B6 stehen dort die Saisonpunkte,
        bis dahin bleibt die Spalte leer.
        """
        if alpha <= 0 or not order:
            return
        comps = comps or theme.competitors()
        self.scrim(int(theme.RESULT_SCRIM_ALPHA * alpha / 255))
        sieger = comps[order[0]]

        # Die ganze Karte sitzt mittig im sicheren Bereich zwischen der
        # Kopfzeile oben und der Shorts-Bedienleiste unten. Im Hochformat
        # sind das die gewohnten 520 px; im Vollbild (1080 hoch) muss der
        # Kopf hoeher, sonst beginnt die Tabelle unter der Bildmitte.
        kopf_y = min(520.0, theme.HEIGHT * 0.30)
        self.text_centered(kopf_y, label, "result_label",
                           fill=theme.TEXT_MUTED, alpha=alpha)
        self.text_centered(kopf_y + 110, sieger.name, "result_name",
                           fill=sieger.bright, alpha=alpha)

        r = 30
        self.draw.ellipse(
            [self.s(theme.WIDTH / 2 - r), self.s(kopf_y + 196 - r),
             self.s(theme.WIDTH / 2 + r), self.s(kopf_y + 196 + r)],
            fill=sieger.color + (alpha,),
        )

        # Reihenfolge darunter. GEKAPPT auf das, was ins Bild passt: mit
        # 112 Teilnehmern war die Tabelle 8 000 px hoch, und die letzte
        # sichtbare Zeile endete mitten im Buchstaben an der Bildkante –
        # gesehen an SHOW-02 am 03.08.2026, dieselbe Klasse wie die
        # 108-px-Namensspalte („100GOLD K"). Die Fuenfer-Endkarte der
        # Kurzfolgen bleibt unveraendert (Kappung greift erst darueber).
        tabelle_y = kopf_y + 280
        zeile_h = 78
        gezeigt, gekuerzt = self.endkarte_zeilen(len(order), tabelle_y,
                                                 zeile_h, theme.HEIGHT)
        breite = 620
        x = (theme.WIDTH - breite) / 2
        # Deckend genug, dass weder Ziellinie noch eine ausrollende Kugel
        # durch die Tabelle scheint – das Rennen ist an dieser Stelle vorbei.
        #
        # 178 war zu wenig: die Ziellinie ist ein Schachbrett aus
        # FINISH_LIGHT (238,241,248). Hinter Abdunklung (224) und Tabelle
        # (178) blieben davon 9 von 255 uebrig – im fertigen Video als
        # gestrichelte Linie quer durch die letzte Tabellenzeile sichtbar.
        # Bei 236 sind es 2 von 255 und damit nicht mehr zu sehen.
        zeilen_gesamt = gezeigt + (1 if gekuerzt else 0)
        self.panel((x, tabelle_y, x + breite,
                    tabelle_y + zeile_h * zeilen_gesamt + theme.PANEL_PAD * 2),
                   alpha=int(236 * alpha / 255))

        if gekuerzt:
            y = (tabelle_y + theme.PANEL_PAD + zeile_h * gezeigt
                 + zeile_h / 2)
            self.text_centered(y - zeile_h / 2 + 14,
                               f"+{len(order) - gezeigt}", "card_entry",
                               fill=theme.TEXT_MUTED, alpha=alpha)

        for rang, idx in enumerate(order[:gezeigt]):
            comp = comps[idx]
            y = tabelle_y + theme.PANEL_PAD + zeile_h * rang + zeile_h / 2
            self.text(x + 34, y, f"{rang + 1}", "card_entry",
                      fill=theme.TEXT_MUTED, anchor="lm", alpha=alpha)
            dr = 16
            self.draw.ellipse(
                [self.s(x + 98 - dr), self.s(y - dr),
                 self.s(x + 98 + dr), self.s(y + dr)],
                fill=comp.color + (alpha,),
            )
            self.text(x + 138, y, comp.name, "card_entry",
                      fill=theme.TEXT, anchor="lm", alpha=alpha)
            if points is not None:
                self.text(x + breite - 34, y, f"{points[rang]:+d}", "card_points",
                          fill=comp.bright, anchor="rm", alpha=alpha)

    # -- Ausgabe ----------------------------------------------------------

    def finish(self) -> Image.Image:
        """Fertiges Bild in Ausgabegroesse."""
        if self.scale == 1:
            return self.image
        return self.image.resize((theme.WIDTH, theme.HEIGHT), Image.LANCZOS)

    def save(self, pfad) -> None:
        self.finish().save(pfad)


def marble_on(d: ImageDraw.ImageDraw, comp: theme.Competitor,
              cx: float, cy: float, r: float) -> None:
    """Eine Kugel auf eine beliebige Zeichenflaeche.

    Frei von Kamera und Supersampling, damit auch Kanalbanner und
    Profilbild dieselbe Kugel bekommen wie das Video.
    """
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=comp.color)
    d.ellipse([cx - r, cy - r, cx + r, cy + r],
              outline=comp.dark, width=max(1, int(r * 0.16)))
    hr = r * theme.MARBLE_GLOSS
    hx, hy = cx - r * 0.33, cy - r * 0.36
    d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=(255, 255, 255, 122))


def _wrap(text: str, max_zeichen: int) -> list[str]:
    """Sehr einfacher Zeilenumbruch an Wortgrenzen."""
    worte = text.split()
    zeilen: list[str] = []
    aktuell = ""
    for w in worte:
        probe = f"{aktuell} {w}".strip()
        if len(probe) > max_zeichen and aktuell:
            zeilen.append(aktuell)
            aktuell = w
        else:
            aktuell = probe
    if aktuell:
        zeilen.append(aktuell)
    return zeilen


def fade(frame: int, start: int, dauer: int, halten: int, aus: int) -> int:
    """Alpha 0..255 fuer eine Einblendung mit Ein- und Ausblenden."""
    t = frame - start
    if t < 0 or t >= dauer + halten + aus:
        return 0
    if t < dauer:
        return int(255 * t / max(1, dauer))
    if t < dauer + halten:
        return 255
    return int(255 * (1 - (t - dauer - halten) / max(1, aus)))
