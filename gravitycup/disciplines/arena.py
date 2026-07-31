#!/usr/bin/env python3
"""
arena.py – Disziplin 4: Kammern. Die Langform-Show.

Eine Kette bildschirmgrosser Kammern. In jeder kommen nur die ERSTEN durch
den Ausgang weiter; wer noch drin steht, wenn das Kontingent voll ist, ist
raus. Das Feld schrumpft, die Kammern schrumpfen mit.

Warum es diese Disziplin gibt, und warum sie so aussieht – alles gemessen
am 30.07.2026, nichts davon geraten:

**1. Die drei Schacht-Disziplinen koennen kein Gedraenge.**
In den 19 ausgestrahlten Runden gehen 84 bis 94 % aller Aufpraelle gegen
Wand und Stift. Die Teilnehmer fallen nebeneinander her. Ursache ist der
freie Fall selbst: dort waechst der Geschwindigkeitsunterschied zweier
Kugeln linear mit der Zeit, das Feld MUSS auseinanderziehen.

**2. Kein Streckenprofil haelt ein Feld zusammen.**
Fuenf Bauformen durchgemessen – enger Schacht, dichte Stiftgitter,
periodische Taillen, flache Rampe, Treppe. Alle fuenf zerstreuen. Bei der
flachen Rampe stand das Feld ueber sechs Bildbreiten und passte in 8 % der
Bilder ins Vollbild.

**3. Also nicht bekaempfen, sondern begrenzen.**
Eine geschlossene Kammer kann sich nicht weiter zerstreuen als sie breit
ist. Gemessen, 1700x900, gegen die heutigen 16 %:

      16 Teilnehmer   49 % Kugel-Kugel   81 % Feld im Bild
      40 Teilnehmer   72 %               79 %
      70 Teilnehmer   82 %               99 %
     100 Teilnehmer   85 %               99 %

**4. Der Stau am Ausgang ist der Mechanismus, nicht der Fehler.**
Bei 100 Teilnehmern kamen nur 12 durch den Ausgang. Als „alle muessen
ankommen" gelesen ist das kaputt; als Eliminierung gelesen ist es die
Disziplin.

**5. Die Arena muss mitschrumpfen.**
Bei 8 Teilnehmern faellt der Kugel-Kugel-Anteil in der grossen Kammer auf
18 %, in einer kleinen auf 29 %. Ohne Schrumpfen wird die Show gegen Ende
langweiliger statt spannender – das Gegenteil eines Spannungsbogens.

CLI-Test:
  python -m gravitycup.disciplines.arena --seed 1
  python -m gravitycup.disciplines.arena --search 10
  python -m gravitycup.disciplines.arena --geometrie 40
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from dataclasses import dataclass

from ..core import physics, theme

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NAME = "arena"

HOOK = ("LAST ONE OUT", "{n} enter, one leaves")

MARBLE_D = 2 * theme.MARBLE_RADIUS

#: Wanddicke. DEUTLICH groesser als in den Schacht-Disziplinen (dort 9 px).
#:
#: Gemessen am 30.07.2026: mit 9 px schoss ein Teil des Feldes durch die
#: Waende, Endpositionen bei y = 87 000 000. In einem Schacht liegt nie ein
#: Haufen an einer Wand; in einer Kammer stehen 64 Kugeln als Stapel vor dem
#: Ausgang, und dieser Druck druckt Kugeln in duenne Segmente hinein.
#: Zusammen mit `physics.simulate(iterationen=...)` ist das die Abhilfe.
SEG_RADIUS = 22.0
PEG_RADIUS = float(theme.PEG_RADIUS)

#: Loeserschritte. pymunks Vorgabe von 10 reicht fuer einen 64-Kugel-Stapel
#: nicht; die Schacht-Disziplinen bleiben unberuehrt bei 10.
SOLVER_ITERATIONEN = 40

#: Platz neben einem Hindernis. Wie in B4/B7 abgeleitet, nicht gewaehlt:
#: eine Luecke schmaler als eine Kugel ist eine Falle.
CLEARANCE = MARBLE_D + 16
MIN_GAP = MARBLE_D + 10


# ---------------------------------------------------------------------------
# Die Leiter: wer ueberlebt welche Kammer
# ---------------------------------------------------------------------------

def leiter(teilnehmer: int, block: int = 0) -> list[int]:
    """Wie viele nach jeder Kammer noch im Spiel sind.

    Vorgabe: EINE Ausscheidung je Kammer. Das ist keine Bequemlichkeit,
    sondern folgt aus der Messung – eine Kammer laeuft in 8 bis 10 Sekunden
    leer, egal was man hineinbaut. Die Laenge einer Folge kommt also aus
    der ZAHL der Kammern, und die ist bei einer Ausscheidung je Kammer
    maximal: 64 Teilnehmer ergeben 63 Kammern und damit rund sieben
    Minuten.

    Versucht und verworfen, beides gemessen am 30.07.2026:
      * Massenausscheidungen frueh (64 -> 48 -> 36 ...) sind das staerkere
        Bild, kosten aber zwei Drittel der Kammern und damit zwei Drittel
        der Laufzeit. Ueber `block` weiterhin moeglich.
      * Zwischenboeden sollten Zeit IN der Kammer schaffen. Ein fast
        bildbreiter Boden faengt aber das ganze Feld auf einmal ab, und
        dieser Schlag druckt Kugeln durch das Brett – 19 von 64 verloren.

    `block` groesser 0 laesst die erste Kammer so viele auf einmal
    ausscheiden. Fuer den Auftakt gedacht, nicht fuer die ganze Folge.
    """
    if teilnehmer < 2:
        raise ValueError("mindestens zwei Teilnehmer")
    if not 0 <= block < teilnehmer - 1:
        raise ValueError(
            f"Block {block} passt nicht zu {teilnehmer} Teilnehmern")
    stufen: list[int] = []
    n = teilnehmer
    if block:
        n -= block
        stufen.append(n)
    while n > 1:
        n -= 1
        stufen.append(n)
    return stufen


# ---------------------------------------------------------------------------
# Bauart
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Bauart:
    """Die Masse der Kammern.

    Die Vorgabewerte stammen aus der Messung, nicht aus dem Gefuehl:
    1700x900 ist die groesste Kammer, die sicher in ein 1920x1080-Bild
    passt (gemessen: 1800x950 lag bei 81 % statt 100 %).
    """

    breite_max: float = 1700.0
    breite_min: float = 620.0
    hoehe: float = 900.0
    #: Lichte Weite des Ausgangs, in Kugeldurchmessern.
    #:
    #: Gemessen mit 64 Kugeln in einer Kammer, wie lange bis 48 durch sind:
    #:     2 Kugeln   nie      verklemmt dauerhaft, und zwei Kugeln gehen
    #:                         dabei durch die Wand verloren
    #:     3 Kugeln    8 s     <- gewaehlt
    #:     4 Kugeln    4 s
    #:     6 Kugeln    3 s
    #: Zwei ist eine Falle, ab vier laeuft die Kammer leer, bevor ein
    #: Gedraengel entsteht. Drei ist der Punkt, an dem es acht Sekunden lang
    #: eng zugeht.
    ausgang_kugeln: float = 3.0
    #: Ausgangsweite der KLEINSTEN Kammer, in Kugeldurchmessern.
    #:
    #: Der Ausgang schrumpft mit dem Feld, so wie die Kammer. Ohne das ist
    #: eine Kammer mit fuenf Kugeln sofort leer – drei Kugelbreiten sind
    #: fuer fuenf Kugeln kein Nadeloehr mehr, und genau daran haengt die
    #: Spannung. Gemessen am 30.07.2026: bei festem Ausgang dauerte ein
    #: 64er-Lauf nur 2,3 Minuten, weil die spaeten Kammern in Sekunden
    #: durchliefen.
    #:
    #: Nicht unter 1,6: bei zwei Kugelbreiten verklemmte eine 64er-Kammer
    #: dauerhaft, und der Druck druckte zwei Kugeln durch die Wand. Fuer
    #: ein kleines Feld ist 1,6 dagegen weit genug.
    ausgang_kugeln_min: float = 2.4
    #: Zwischenboeden. AUS, und das ist ein Messergebnis.
    #:
    #: Sie sollten Zeit in der Kammer schaffen: ein Zickzackweg, ohne dass
    #: die Kammer groesser wird. Gemessen am 30.07.2026 richtet ein fast
    #: bildbreiter Boden aber genau das an, was er verhindern soll – er
    #: faengt das ganze Feld im selben Augenblick ab, und dieser Schlag
    #: druckt Kugeln durch das Brett. Bei einer Etage gingen 19 von 64
    #: Kugeln verloren, bei zwei noch 9, und kein einziger Lauf kam durch.
    #:
    #: Der Code bleibt stehen, weil kuerzere, versetzte Simse den Gedanken
    #: retten koennten – aber erst gemessen, dann eingeschaltet.
    etagen: int = 0
    #: Lichte Weite der Durchlaesse zwischen zwei Zwischenboeden.
    etage_lucke_kugeln: float = 3.0
    #: Teiler unter dem Einwurf: ein Dreieck mit der Spitze nach oben.
    #:
    #: Ohne ihn faellt eine Kugel schnurstracks vom Einwurf zum Ausgang und
    #: von dort in die naechste Kammer – der Fuehrende durchquert damit die
    #: ganze Strecke, bevor das erste Tor ueberhaupt entschieden hat.
    #: Gemessen am 30.07.2026 an Seed 4: 21 Kugeln im Ziel, NULL
    #: Ausscheidungen.
    #:
    #: Der Teiler zwingt jede Kugel nach links ODER rechts und staut das
    #: Feld nach jedem Trichter kurz auf. Breite in Kugeldurchmessern.
    teiler_kugeln: float = 2.0
    #: Hoehe des Teilers, im Verhaeltnis zu seiner halben Breite. 1.0 = 45°.
    teiler_neigung: float = 0.9
    #: Stifte je Kammer bei voller Breite; kleinere Kammern anteilig.
    stifte_max: int = 14
    #: Anteil der Stifte, der ein PRELLBOCK ist. AUS, und das ist gemessen.
    #:
    #: Der Gedanke war gut: ein Prellbock wirft die Kugel zurueck, statt sie
    #: durchzulassen, und sollte damit das Feld in der Kammer halten – das
    #: Gegenteil eines Zwischenbodens, der es auffaengt. Gemessen mit
    #: 24 Teilnehmern tut er das Gegenteil:
    #:
    #:     ohne Prellboecke   56 s   32 % Kugel-Kugel
    #:     40 % Prellboecke   48 s   23 %
    #:     80 % Prellboecke   51 s   24 %
    #:
    #: Ein Prellbock ueber dem Trichter schleudert die Kugel AUS dem Pulk
    #: heraus, statt ihn zusammenzuhalten – kuerzere Laeufe, weniger
    #: Kontakt. Nicht ausprobiert und weiterhin offen: ein elastischer
    #: BODEN unter der ganzen Kammer statt verstreuter Boecke, und drehende
    #: Elemente, die nicht nur schleudern, sondern mischen. Letztere
    #: brauchen kinematische Koerper, die es in `physics` noch nicht gibt.
    prell_anteil: float = 0.0
    #: Elastizitaet eines Prellbocks. Ueber 1.0 gibt er mehr Energie zurueck,
    #: als ankam. Der Hauswert eines Stifts ist 0,55.
    prell_elastizitaet: float = 1.15
    #: Senkrechter Abstand zwischen zwei Kammern.
    abstand: float = 520.0
    #: Drehkreuz ueber dem Ausgang. DAS ist die Abhilfe gegen den
    #: verkeilten Haufen: gemessen an SHOW-01 bewegten sich 86 % der
    #: Laufzeit weniger als zehn Prozent der Kugeln - 19,4 von 22,8 Minuten
    #: Stillstand, waehrend die Ausscheidungen nur noch von der Raeumzeit
    #: kamen. Ein Rotor schiebt den Pulk durch die Engstelle, statt darauf
    #: zu warten, dass die Schwerkraft es tut.
    rotor: bool = True
    #: Umdrehungen je Sekunde.
    rotor_drehzahl: float = 0.60
    rotor_fluegel: int = 3
    #: Haltezeit der ERSTEN und der LETZTEN Kammer, in Sekunden.
    #:
    #: DAS bestimmt jetzt die Laufzeit, nicht mehr das Abflussverhalten.
    #: Ohne Sperre dauert eine Kammer so lange, wie ihr Feld zum Abfliessen
    #: braucht: mit 64 Kugeln zehn Sekunden, mit vier unter einer. Der
    #: Spannungsbogen lief dadurch RUECKWAERTS – zum Ende hin immer
    #: schneller und belangloser.
    #:
    #: Die lange Haltezeit gehoert nach VORN, und das ist gemessen: mit
    #: 26 s in den letzten Kammern stand die Totzeit bei 64 Sekunden – dort
    #: sitzen nur noch zwei oder drei Kugeln hinter einer Sperre, und das
    #: ist kein Stau, das ist Warten. Interessant ist der Stau nur, solange
    #: viele Kugeln daran beteiligt sind.
    #:
    #: Der Spannungsbogen entsteht dann anders herum: vorn ein langer,
    #: wuehlender Pulk, hinten kurze, scharfe Duelle durch eine enge Kammer.
    #:
    #: ACHTUNG, das sind OBERGRENZEN, keine festen Wartezeiten. Als fester
    #: Timer waren sie ein Ladebildschirm: bei 64 Kugeln, die nacheinander
    #: durch die Rutsche einfallen, sind 22 s ein wuehlender Haufen – bei
    #: 12 sitzen sie nach vier Sekunden unten und warten achtzehn Sekunden,
    #: dass etwas passiert. Die Sperre geht deshalb auf, sobald ALLE da
    #: sind, plus `halt_beat`; die Zahlen hier greifen nur, wenn jemand
    #: haengenbleibt.
    halt_erste: float = 22.0
    halt_letzte: float = 8.0
    #: Ruhemoment, nachdem der Letzte angekommen ist. Kurz genug, dass es
    #: nicht zieht, lang genug, dass man den vollen Pulk einmal sieht.
    halt_beat: float = 1.6

    def breite(self, teilnehmer: int, hoechste: int) -> float:
        """Kammerbreite fuer ein Feld dieser Groesse.

        Die Flaeche faellt mit der Teilnehmerzahl, damit die DICHTE
        ungefaehr gleich bleibt. Ohne das faellt der Kugel-Kugel-Anteil
        von 49 % bei 16 auf 18 % bei 8 – die Show wuerde zum Ende hin
        ruhiger, und das ist genau verkehrt.
        """
        if hoechste <= 1:
            return self.breite_max
        anteil = max(0.0, min(1.0, (teilnehmer - 1) / (hoechste - 1)))
        return self.breite_min + (self.breite_max - self.breite_min) * anteil

    def ausgang(self, teilnehmer: int | None = None,
                hoechste: int | None = None) -> float:
        """Ausgangsweite fuer ein Feld dieser Groesse.

        Ohne Angabe die weiteste – so bleibt `pruefen()` eine Aussage ueber
        den ungenstigsten Fall.
        """
        if teilnehmer is None or hoechste is None or hoechste <= 1:
            return self.ausgang_kugeln * MARBLE_D
        anteil = max(0.0, min(1.0, (teilnehmer - 1) / (hoechste - 1)))
        kugeln = (self.ausgang_kugeln_min
                  + (self.ausgang_kugeln - self.ausgang_kugeln_min) * anteil)
        return kugeln * MARBLE_D

    def pruefen(self) -> None:
        if self.ausgang_kugeln_min * MARBLE_D < MARBLE_D + 8:
            raise ValueError(
                f"kleinster Ausgang {self.ausgang_kugeln_min:.1f} Kugeln – "
                f"eine Kugel passt nicht sicher durch")
        if self.breite_min < self.ausgang() + 2 * (SEG_RADIUS + MARBLE_D):
            raise ValueError(
                f"kleinste Kammer {self.breite_min:.0f} px ist zu schmal "
                f"fuer einen Ausgang von {self.ausgang():.0f} px")
        if self.ausgang() < MARBLE_D + 8:
            raise ValueError(
                f"Ausgang {self.ausgang():.0f} px, Kugel ist {MARBLE_D:.0f}")
        if self.hoehe < 4 * MARBLE_D:
            raise ValueError("Kammer zu flach")
        # Abstand zweier Zwischenboeden. ABGELEITET, nicht gewaehlt: zwischen
        # zwei Boeden muss eine Kugel hindurchpassen, sonst steht das ganze
        # Feld. Gemessen: bei 93 px Abstand und 44 px Bodendicke blieben
        # 49 px fuer eine 64-px-Kugel, und kein einziger Lauf kam durch.
        if self.etagen:
            nutz = self.hoehe - 220.0
            spalt = nutz / (self.etagen + 1) - 2 * SEG_RADIUS
            if spalt < MARBLE_D + 20:
                raise ValueError(
                    f"{self.etagen} Zwischenboeden lassen nur {spalt:.0f} px "
                    f"lichte Weite (Kugel ist {MARBLE_D:.0f} px) – "
                    f"hoechstens {int(nutz / (MARBLE_D + 20 + 2 * SEG_RADIUS)) - 1} "
                    f"Etagen bei {self.hoehe:.0f} px Kammerhoehe")


VORGABE = Bauart()


# ---------------------------------------------------------------------------
# Geometrie
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Kammerform:
    """Wo eine Kammer liegt und wie viele sie durchlaesst."""

    nummer: int
    oben: float
    unten: float
    links: float
    rechts: float
    weiter: int          # so viele kommen durch
    austritt: float      # y-Linie, unter der man durch ist
    ausgang: float       # lichte Weite des Ausgangs
    halt: float          # so lange bleibt die Sperre zu


def kammerformen(teilnehmer: int, bauart: Bauart = VORGABE) -> list[Kammerform]:
    """Die Kette der Kammern, von oben nach unten."""
    mitte = theme.WIDTH / 2
    formen: list[Kammerform] = []
    y = 0.0
    drin = teilnehmer
    stufen = leiter(teilnehmer)
    for k, weiter in enumerate(stufen):
        breite = bauart.breite(drin, teilnehmer)
        formen.append(Kammerform(
            nummer=k + 1, oben=y, unten=y + bauart.hoehe,
            links=mitte - breite / 2, rechts=mitte + breite / 2,
            weiter=weiter, ausgang=bauart.ausgang(drin, teilnehmer),
            halt=bauart.halt_erste + (bauart.halt_letzte - bauart.halt_erste)
            * (k / max(1, len(stufen) - 1)),
            # Die Austrittslinie liegt UNTER dem Trichtermund. Wer sie
            # quert, ist durch. Sie darf nicht in der Kammer liegen, sonst
            # zaehlt eine Kugel als durch, die nur tief steht.
            austritt=y + bauart.hoehe + 40.0))
        y += bauart.hoehe + bauart.abstand
        drin = weiter
    return formen


def build_track(seed: int, teilnehmer: int,
                bauart: Bauart = VORGABE) -> physics.Track:
    """Die Strecke einer Folge. Gleicher Seed, gleiche Strecke."""
    bauart.pruefen()
    rng = random.Random(seed * 7919 + 11)
    formen = kammerformen(teilnehmer, bauart)
    segments: list[physics.Segment] = []
    pegs: list[physics.Peg] = []
    tore: list[list[physics.Segment]] = []
    rotoren: list[physics.Rotor] = []
    mitte = theme.WIDTH / 2
    #: Einwurfoeffnung in der Decke. Fest und weit genug fuer den
    #: groessten Ausgang – die Rutsche von oben fuehrt genau dorthin.
    einwurf = bauart.ausgang() * 1.35
    letzte = formen[-1]
    finish_y = letzte.unten + 520.0
    finish_oben = finish_y - 400.0

    # Startkammer ueber der ersten Kammer.
    #
    # Der erste Entwurf stellte die Kugeln IN die erste Kammer. Zwei Fehler
    # auf einmal, beide gemessen am 30.07.2026: 64 Kugeln brauchen drei
    # Startreihen bis y = 236 und standen damit im ersten Zwischenboden bei
    # y = 227 – pymunk schleuderte neun Kugeln auseinander. Und selbst ohne
    # Ueberlappung frass die Aufstellung 308 der 680 nutzbaren Pixel, sodass
    # die Zwischenboeden nur noch 93 px auseinanderlagen: bei 44 px
    # Bodendicke bleiben 49 px lichte Weite fuer eine 64-px-Kugel.
    #
    # Jetzt faellt das Feld von oben ein wie in jede andere Kammer auch.
    start_hoehe = starthoehe(teilnehmer, formen[0], bauart)

    for form in formen:
        # Seitenwaende. Die erste reicht ueber die Startkammer hinauf.
        wand_oben = form.oben - 60 - (start_hoehe if form.nummer == 1 else 0)
        segments.append(physics.Segment(form.links, wand_oben,
                                        form.links, form.unten - 220,
                                        SEG_RADIUS))
        segments.append(physics.Segment(form.rechts, wand_oben,
                                        form.rechts, form.unten - 220,
                                        SEG_RADIUS))
        # Trichter auf den Ausgang zu. Der Versatz wechselt mit dem Seed,
        # sonst begaenstigt eine feste Seite immer dieselbe Bildhaelfte –
        # die Lehre aus B4.
        versatz = rng.uniform(-0.16, 0.16) * (form.rechts - form.links)
        tor_links = mitte + versatz - form.ausgang / 2
        tor_rechts = mitte + versatz + form.ausgang / 2
        segments.append(physics.Segment(form.links, form.unten - 220,
                                        tor_links, form.unten, SEG_RADIUS))
        segments.append(physics.Segment(form.rechts, form.unten - 220,
                                        tor_rechts, form.unten, SEG_RADIUS))

        # Zwischenboeden: abwechselnd links und rechts angesetzt, mit einer
        # Luecke am freien Ende. Die Kugeln muessen jede Etage queren, bevor
        # sie fallen duerfen – das ist die Zeit, die eine Kammer ueberhaupt
        # dauert. Sie liegen bewusst leicht schraeg, sonst bleibt ein Pulk
        # auf einem waagrechten Brett einfach liegen.
        luecke = bauart.etage_lucke_kugeln * MARBLE_D
        nutzhoehe = (form.unten - 220) - form.oben
        for e in range(bauart.etagen):
            ey = form.oben + nutzhoehe * (e + 1) / (bauart.etagen + 1)
            nach_rechts = (e + form.nummer) % 2 == 0
            if nach_rechts:
                x_von, x_bis = form.links, form.rechts - luecke
            else:
                x_von, x_bis = form.rechts, form.links + luecke
            if abs(x_bis - x_von) < MARBLE_D * 2:
                continue
            gefaelle = min(90.0, nutzhoehe / (bauart.etagen + 1) * 0.35)
            segments.append(physics.Segment(x_von, ey, x_bis, ey + gefaelle,
                                            SEG_RADIUS))

        # Decke mit Einwurfoeffnung in der MITTE. Die Oeffnung sitzt fest
        # zentriert, weil die Rutsche von oben genau dorthin fuehrt.
        if form.nummer > 1:
            for von, bis in ((form.links, mitte - einwurf / 2),
                             (mitte + einwurf / 2, form.rechts)):
                if bis - von > MARBLE_D:
                    segments.append(physics.Segment(von, form.oben - 60,
                                                    bis, form.oben - 60,
                                                    SEG_RADIUS))

        # Teiler unter dem Einwurf: Spitze nach oben, die Kugel muss sich
        # entscheiden. Er sitzt so tief, dass darueber eine Kugel Platz hat,
        # und ist nie breiter als die Kammer neben ihm durchlaesst.
        if bauart.teiler_kugeln > 0:
            halb = bauart.teiler_kugeln * MARBLE_D / 2
            frei = (form.rechts - form.links) / 2 - halb - SEG_RADIUS
            if frei >= MARBLE_D + 20:
                spitze_y = form.oben + MARBLE_D + 40
                fuss_y = spitze_y + halb * bauart.teiler_neigung
                segments.append(physics.Segment(mitte, spitze_y,
                                                mitte - halb, fuss_y,
                                                SEG_RADIUS))
                segments.append(physics.Segment(mitte, spitze_y,
                                                mitte + halb, fuss_y,
                                                SEG_RADIUS))

        # Drehkreuz dicht ueber dem Trichtermund, wo sich der Haufen
        # verkeilt. Die Fluegel duerfen die Waende nicht beruehren, sonst
        # klemmt eine Kugel zwischen Fluegel und Wand.
        if bauart.rotor:
            frei = min(mitte - form.links, form.rechts - mitte) - SEG_RADIUS
            laenge = min(form.ausgang * 0.9, frei - MARBLE_D - 30)
            if laenge > MARBLE_D * 0.8:
                rotoren.append(physics.Rotor(
                    x=mitte + versatz, y=form.unten - 250,
                    laenge=laenge,
                    drehzahl=bauart.rotor_drehzahl
                    * (1 if form.nummer % 2 else -1),
                    fluegel=bauart.rotor_fluegel,
                    winkel0=rng.uniform(0, 6.283)))

        # Die SPERRE: sie schliesst den Ausgang, bis die Regel sie oeffnet.
        # Bewusst etwas unter dem Trichtermund, damit der Pulk davor liegt
        # und nicht darin klemmt.
        tore.append([physics.Segment(tor_links - SEG_RADIUS, form.unten + 30,
                                     tor_rechts + SEG_RADIUS, form.unten + 30,
                                     SEG_RADIUS)])

        # Rutsche vom Ausgang dieser Kammer in die naechste.
        #
        # OHNE sie faellt ein Teil des Feldes ins Nichts, und der Lauf sieht
        # dabei nicht kaputt aus – er hat nur immer weniger Teilnehmer.
        # Gemessen am 30.07.2026 im ersten vollen Lauf: 43 von 64 Kugeln
        # verloren, 21 statt 63 Ausscheidungen.
        #
        # Ursache: der Ausgang wird je Seed um bis zu 272 px aus der Mitte
        # geruckt, die Kammern werden nach unten aber immer SCHMALER. Ein
        # Ausgang weit aussen zeigt damit an der naechsten Kammer vorbei.
        # Der Versatz bleibt – er ist die Abwechslung, die B4 gelehrt hat –,
        # aber die Rutsche faengt ihn ab.
        naechste = formen[form.nummer] if form.nummer < len(formen) else None
        unten_ziel = (naechste.oben - 60) if naechste else (finish_oben)
        for x_von, x_zu in ((tor_links, mitte - einwurf / 2),
                            (tor_rechts, mitte + einwurf / 2)):
            segments.append(physics.Segment(x_von, form.unten,
                                            x_zu, unten_ziel, SEG_RADIUS))

    # Auslauf hinter der letzten Kammer
    segments.append(physics.Segment(mitte - 700, finish_y + 200,
                                    mitte + 700, finish_y + 200, SEG_RADIUS))
    segments.append(physics.Segment(mitte - 700, finish_oben,
                                    mitte - 700, finish_y + 210, SEG_RADIUS))
    segments.append(physics.Segment(mitte + 700, finish_oben,
                                    mitte + 700, finish_y + 210, SEG_RADIUS))

    # --- Stifte, jeder gegen alles bisherige geprueft --------------------
    # Erst wenn ALLE Segmente stehen. Die Blindheit dabei hat das
    # Sturzrennen einmal 94 % seiner Laeufe gekostet.
    for form in formen:
        breite = form.rechts - form.links
        wieviele = max(4, int(bauart.stifte_max * breite / bauart.breite_max))
        versuche = 0
        gesetzt = 0
        while gesetzt < wieviele and versuche < wieviele * 60:
            versuche += 1
            px = rng.uniform(form.links + 130, form.rechts - 130)
            py = rng.uniform(form.oben + 150, form.unten - 380)
            if physics.passt_durch(px, py, PEG_RADIUS, segments, pegs,
                                   CLEARANCE):
                # Prellboecke sitzen im UNTEREN Drittel der Kammer, direkt
                # ueber dem Trichter. Dort halten sie das Feld zurueck; oben
                # wuerden sie es nur schneller nach unten schleudern.
                unten_drittel = py > form.oben + (form.unten - form.oben) * 0.55
                prellt = (bauart.prell_anteil > 0 and unten_drittel
                          and rng.random() < bauart.prell_anteil)
                pegs.append(physics.Peg(
                    px, py, PEG_RADIUS,
                    bauart.prell_elastizitaet if prellt else None))
                gesetzt += 1

    starts = startplaetze(teilnehmer, formen[0], bauart)

    return physics.Track(segments=segments, pegs=pegs, starts=starts,
                         finish_y=finish_y, tore=tore, rotoren=rotoren,
                         name=f"{NAME}-{teilnehmer}")


def _startraster(anzahl: int, erste: Kammerform,
                 bauart: Bauart) -> tuple[float, float, int, float]:
    innen_links = erste.links + SEG_RADIUS + theme.MARBLE_RADIUS + 6
    innen_rechts = erste.rechts - SEG_RADIUS - theme.MARBLE_RADIUS - 6
    abstand = MARBLE_D + 10
    je_reihe = max(1, int((innen_rechts - innen_links) // abstand) + 1)
    return innen_links, innen_rechts, je_reihe, abstand


def starthoehe(anzahl: int, erste: Kammerform,
               bauart: Bauart = VORGABE) -> float:
    """Wie hoch die Startkammer ueber der ersten Kammer sein muss."""
    _, _, je_reihe, _ = _startraster(anzahl, erste, bauart)
    reihen = math.ceil(anzahl / je_reihe)
    return reihen * (MARBLE_D + 8) + 60.0


def startplaetze(anzahl: int, erste: Kammerform,
                 bauart: Bauart = VORGABE) -> list[tuple[float, float]]:
    """Startplaetze in der Startkammer UEBER der ersten Kammer.

    Bei vierundsechzig Kugeln gibt es keine einzelne Reihe mehr; die
    Aufstellung ist zwangslaeufig gestaffelt. Das ist hier unbedenklich,
    weil `simulate` die Zuordnung Teilnehmer→Platz je Seed auslost – ein
    Reihenvorteil trifft also keine Kennung systematisch.
    """
    innen_links, _, je_reihe, abstand = _startraster(anzahl, erste, bauart)
    hoehe = starthoehe(anzahl, erste, bauart)
    plaetze = []
    for i in range(anzahl):
        r, s = divmod(i, je_reihe)
        plaetze.append((innen_links + s * abstand,
                        erste.oben - hoehe + 40.0 + r * (MARBLE_D + 8)))
    return plaetze


def pruefe_durchlaesse(track: physics.Track, teilnehmer: int,
                       bauart: Bauart = VORGABE) -> list[str]:
    """Engstellen, in denen sich eine Kugel verkeilen kann.

    Der Ausgang MUSS eng sein – er ist der Mechanismus. Geprueft wird
    deshalb nur, dass er nie enger als eine Kugel wird, und dass sonst
    nirgends eine Falle entsteht.
    """
    maengel = physics.engstellen(track, MIN_GAP)
    for form in kammerformen(teilnehmer, bauart):
        if form.ausgang < MARBLE_D + 8:
            maengel.append(
                f"Kammer {form.nummer}: Ausgang {form.ausgang:.0f} px, "
                f"Kugel ist {MARBLE_D:.0f} px")
        breite = form.rechts - form.links
        if breite < form.ausgang + 2 * (SEG_RADIUS + MARBLE_D):
            maengel.append(
                f"Kammer {form.nummer}: {breite:.0f} px breit, zu schmal "
                f"neben dem Ausgang")
    return maengel


# ---------------------------------------------------------------------------
# Die Siegbedingung
# ---------------------------------------------------------------------------


class Kammern(physics.Regel):
    """In jeder Kammer kommen nur die ERSTEN durch.

    Gezaehlt wird ueber die POSITION, nicht ueber das Querungsereignis.
    Das ist die Lehre vom selben Tag: die Eliminierung zaehlte Querungen
    als Ereignis und schaute dabei auf genau ein Tor – wer frueher
    passierte, wurde nie gezaehlt, und die Regel wartete fuer immer. Bei
    fuenf Teilnehmern faellt das nie auf, bei dreissig sofort.
    """

    name = "kammern"

    #: Laengste Dauer einer Kammer. Danach fliegt raus, wer hinten liegt –
    #: auch wenn das Kontingent noch nicht voll ist.
    #:
    #: DAS ist der Kern, und er hat gefehlt. Ohne Uhr wartet eine Kammer,
    #: bis `weiter` Kugeln durch sind, und EINE haengengebliebene Kugel
    #: blockiert damit die gesamte Kaskade: kein Tor feuert mehr, waehrend
    #: alle anderen bis ins Ziel durchlaufen. Gemessen am 30.07.2026 ueber
    #: sechs Seeds mit 64 Teilnehmern: 3 von 6 Laeufen brachen so ab, mit
    #: bis zu 30 Kugeln im Ziel und NULL Ausscheidungen.
    #:
    #: Bei fuenf Teilnehmern und vier Toren kommt das nie vor – deshalb
    #: braucht die Eliminierung keine Uhr. Bei 63 Kammern fast immer.
    #:
    #: Die Uhr deckelt nebenbei die Laufzeit: 63 Kammern mal hoechstens
    #: diese Zeit.
    STAGE_ZEIT = 7.0

    def __init__(self, formen: list[Kammerform], finish_y: float,
                 raeumzeit: float = STAGE_ZEIT, halt_beat: float = 1.6):
        if not formen:
            raise ValueError("Arena ohne Kammern")
        self.formen = list(formen)
        self.finish_y = finish_y
        self.raeumzeit = raeumzeit
        self.halt_beat = halt_beat

    def vorbereiten(self, count: int) -> None:
        super().vorbereiten(count)
        if self.formen[-1].weiter != 1:
            raise ValueError(
                f"die letzte Kammer laesst {self.formen[-1].weiter} durch, "
                f"es muss genau einer uebrig bleiben")
        self.aktiv = set(range(count))
        self.kammer = 0
        #: Wann die laufende Kammer begonnen hat – fuer die Haltezeit.
        self.kammer_seit = 0.0
        #: Wann die Sperre der laufenden Kammer aufging.
        self._auf_seit = 0.0
        #: Seit wann ALLE Aktiven in der laufenden Kammer sind.
        self._voll_seit: float | None = None
        #: Welche Sperren offen sind. `physics.simulate` fragt das ab.
        self._offen: set[int] = set()
        self.reihenfolge_raus: list[int] = []
        #: Fuers Bild: (Zeit, Kammer, wer raus ist)
        self.ereignisse: list[tuple[float, int, int]] = []
        #: Wer wann durch welchen Ausgang kam.
        self.durch: dict[int, float] = {}

    def offene_tore(self) -> set[int]:
        return self._offen

    def schritt(self, zeit_von: float, dt: float,
                y_vorher: list[float], y_jetzt: list[float],
                x_jetzt: list[float] | None = None) -> set[int]:
        # Die Ziellinie wird IMMER mitgeschrieben, nicht erst wenn alle
        # Kammern abgehakt sind. Der Ueberlebende raest den letzten Kammern
        # davon; bis der Kammerzaehler ankam, lag er 146 px HINTER der Linie
        # und wurde nie als angekommen gewertet.
        for i in self.aktiv:
            if i in self.zielzeiten:
                continue
            if y_jetzt[i] > self.finish_y:
                anteil = physics.linie_gequert(y_vorher[i], y_jetzt[i],
                                               self.finish_y)
                self.zielzeiten[i] = zeit_von + (
                    anteil if anteil is not None else 1.0) * dt

        if self.kammer >= len(self.formen):
            return set()

        form = self.formen[self.kammer]
        zeit = zeit_von + dt

        # --- Phase 1: die Sperre ist zu, das Feld sammelt sich ------------
        #
        # Das ist der Kern der Disziplin. Ohne Sperre ist eine Kammer ein
        # ABFLUSS und dauert so lange, wie ihr Feld zum Durchlaufen
        # braucht – bei vier Kugeln unter einer Sekunde.
        #
        # Die Sperre geht auf, sobald ALLE angekommen sind, plus ein kurzer
        # Ruhemoment. `form.halt` ist nur die Obergrenze fuer den Fall,
        # dass jemand haengenbleibt. Als fester Timer war das ein
        # Ladebildschirm: bei zwoelf Kugeln sassen alle nach vier Sekunden
        # unten und warteten achtzehn weitere.
        if self.kammer not in self._offen:
            drin = sum(1 for i in self.aktiv if y_jetzt[i] > form.oben)
            if drin >= len(self.aktiv):
                if self._voll_seit is None:
                    self._voll_seit = zeit
            else:
                self._voll_seit = None
            fertig = (self._voll_seit is not None
                      and zeit - self._voll_seit >= self.halt_beat)
            if not fertig and zeit - self.kammer_seit < form.halt:
                return set()
            self._offen.add(self.kammer)
            self._auf_seit = zeit
            self._voll_seit = None
            return set()

        # --- Phase 2: das Tor ist offen, es wird gerannt ------------------
        drunter = {i for i in self.aktiv if y_jetzt[i] > form.austritt}
        for i in drunter:
            self.durch.setdefault(i, zeit)

        # Notausgang: bleibt eine Kugel haengen, wartet die Kammer sonst
        # ewig und blockiert die ganze Kaskade. Gemessen ohne diese Grenze:
        # 3 von 6 Laeufen mit bis zu 30 Kugeln im Ziel und NULL
        # Ausscheidungen.
        abgelaufen = zeit - self._auf_seit >= self.raeumzeit

        if len(drunter) < form.weiter and not abgelaufen:
            return set()

        if len(drunter) >= form.weiter:
            raus = sorted(self.aktiv - drunter, key=lambda i: y_jetzt[i])
        else:
            wieviele = len(self.aktiv) - form.weiter
            raus = sorted(self.aktiv, key=lambda i: y_jetzt[i])[:max(0, wieviele)]

        for i in raus:
            self.ausgeschieden[i] = zeit
            self.reihenfolge_raus.append(i)
            self.ereignisse.append((zeit, form.nummer, i))
            self.aktiv.discard(i)
        self.kammer += 1
        self.kammer_seit = zeit
        self.durch = {}
        return set(raus)

    def erledigt(self) -> bool:
        return (self.kammer >= len(self.formen)
                and all(i in self.zielzeiten for i in self.aktiv))

    def rangfolge(self, letzte) -> list[int]:
        """Der Ueberlebende zuerst, dann rueckwaerts nach Ausscheiden."""
        mit_ziel = sorted((i for i in self.aktiv if i in self.zielzeiten),
                          key=lambda i: self.zielzeiten[i])
        ohne_ziel = sorted((i for i in self.aktiv if i not in self.zielzeiten),
                           key=lambda i: -letzte[i][1])
        return mit_ziel + ohne_ziel + list(reversed(self.reihenfolge_raus))


# ---------------------------------------------------------------------------
# Lauf und Annahme
# ---------------------------------------------------------------------------

#: Zeitbudget je Kammer fuer die Notbremse.
NOTBREMSE_JE_KAMMER = 25.0


def notbremse(teilnehmer: int, bauart: "Bauart | None" = None) -> float:
    """Wie lange ein Lauf hoechstens rechnen darf.

    Rechnet aus den HALTEZEITEN, nicht aus einer festen Zahl je Kammer –
    seit die Sperren die Dauer bestimmen, waere jede feste Zahl entweder zu
    knapp oder sinnlos gross.
    """
    b = bauart or VORGABE
    formen = kammerformen(teilnehmer, b)
    halten = sum(f.halt for f in formen)
    return max(physics.MAX_SECONDS,
               halten + len(formen) * NOTBREMSE_JE_KAMMER)


def regel_kennung(seed: int, teilnehmer: int = 64,
                  bauart: Bauart = VORGABE) -> str:
    """Fingerabdruck der Siegbedingung – fuer den Zwischenspeicher in B5."""
    formen = kammerformen(teilnehmer, bauart)
    teile = ",".join(f"{f.austritt:.3f}:{f.weiter}" for f in formen)
    return f"{Kammern.name}:{teile}"


def run(seed: int, teilnehmer: int = 64,
        bauart: Bauart = VORGABE) -> physics.RunResult:
    """Einen Lauf rechnen."""
    track = build_track(seed, teilnehmer, bauart)
    formen = kammerformen(teilnehmer, bauart)
    return physics.simulate(
        track, seed,
        regel=Kammern(formen, track.finish_y, halt_beat=bauart.halt_beat),
        marks=[f.austritt for f in formen],
        count=teilnehmer,
        max_seconds=notbremse(teilnehmer, bauart),
        # Geduldsuhr praktisch aus. Sie beendet einen Lauf, sobald der
        # Erste im Ziel ist – gedacht fuer ein 30-Sekunden-Rennen, in dem
        # danach nur noch Nachzuegler ausrollen. Hier laufen zu dem
        # Zeitpunkt noch Dutzende Kammern, und der Lauf wurde mitten
        # hineingeschnitten: gemessen 34 von 63 Ausscheidungen, obwohl die
        # Stage-Uhr sauber lief. Die Laenge deckelt jetzt die Stage-Uhr,
        # nicht die Geduld.
        patience_seconds=notbremse(teilnehmer, bauart),
        iterationen=SOLVER_ITERATIONEN,
        extras={"mark_label": "STAGE",
                "kammern": [[f.links, f.oben, f.rechts, f.unten, f.weiter]
                            for f in formen]})


# ---------------------------------------------------------------------------
# Annahmekriterien
#
# NEU gegenueber B4/B7/B8: hier stehen von Anfang an SPANNUNGS-Kriterien.
# Bis heute prueft das Projekt nur Korrektheit – Dauer, Torzahl,
# Aufprallzahl, Engstellen. Gemessen an den 19 ausgestrahlten Runden
# besteht ein Lauf mit 17 Sekunden Stillstand alle Pruefungen und wird
# gebaut. Von 120 Seeds bestehen 97 bis 100 % die Pruefung; sie filtert
# also praktisch nichts.
# ---------------------------------------------------------------------------

#: Zeitfenster fuer eine Langform. Ohne Sperren lagen Laeufe bei 2,8 min
#: und waren damit kein Video, sondern ein langer Short. Mit Sperren
#: bestimmt die Haltezeit die Dauer: 64 Teilnehmer und 2-8 s Halt ergaben
#: gemessen 12,4 min, die vorgesehenen 6-26 s ergeben ueber zwanzig.
MIN_SECONDS = 300.0
MAX_SECONDS = 3600.0
#: Laengste Strecke ohne jede Ausscheidung. Gemessen liegt die Totzeit der
#: Schacht-Disziplinen im Median bei 12 bis 17 s; das ist der Wert, den
#: dieses Format unterbieten soll.
#: Laengste Strecke ohne Ausscheidung.
#:
#: Seit es Sperren gibt, ist ein Teil davon ABSICHT: waehrend die Sperre zu
#: ist, faellt keine Entscheidung, aber das Feld staut sich sichtbar auf –
#: das ist Spannungsaufbau, keine tote Luft. Der Wert deckelt deshalb nur,
#: dass eine Kammer nicht ZUSAETZLICH haengenbleibt. Gerechnet aus der
#: laengsten Haltezeit plus der Raeumzeit.
MAX_TOTZEIT = 45.0
#: Anteil Kugel-Kugel-Aufpraelle. Die ausgestrahlten Folgen liegen bei
#: 16 %, die fertige Arena bei 30 bis 35 %. Unter 25 % heisst, dass die
#: Kammer ihr Feld nicht zusammengehalten hat – gemessen lagen genau die
#: kaputten Laeufe bei 18 bis 22 %.
MIN_KUGEL_KUGEL = 0.25

#: Anteil der Laufzeit, in dem sich mindestens jede zehnte Kugel bewegt.
#:
#: Ohne dieses Kriterium ist ein Lauf "brauchbar", der 19 von 23 Minuten
#: stillsteht - genau so ist SHOW-01 durch alle Pruefungen gekommen. Es ist
#: das einzige Kriterium, das den Unterschied zwischen einem Rennen und
#: einem Standbild misst.
MIN_LEBENDIG = 0.75


def kennzahlen(result: physics.RunResult) -> dict:
    """Die Zahlen, an denen dieser Lauf gemessen wird."""
    from collections import Counter

    arten = Counter(h.kind for h in result.hits)
    gesamt = sum(arten.values()) or 1

    zeiten = sorted(result.eliminated.values())
    luecken = []
    vorher = 0.0
    for t in zeiten:
        luecken.append(t - vorher)
        vorher = t
    luecken.append(result.duration - vorher)

    # Anteil der Zeit, in dem sich ueberhaupt etwas bewegt.
    #
    # DIE Kennzahl, die gefehlt hat. SHOW-01 bestand jedes Kriterium -
    # 63/63 Ausscheidungen, Totzeit im Rahmen - und stand trotzdem 19,4 von
    # 22,8 Minuten still: der Haufen verkeilte sich, und die Ausscheidungen
    # kamen nur noch von der Raeumzeit. Gemessen wurde, DASS Kugeln
    # ausscheiden, nie OB sie sich bewegen.
    fps = result.fps
    bewegt = []
    for f in range(1, len(result.frames), 3):
        raus = {i for i, t in result.eliminated.items() if t * fps <= f}
        aktiv = [i for i in range(len(result.frames[f])) if i not in raus]
        if not aktiv:
            continue
        n = sum(1 for i in aktiv
                if abs(result.frames[f][i][1] - result.frames[f - 1][i][1]) > 3.0
                or abs(result.frames[f][i][0] - result.frames[f - 1][i][0]) > 3.0)
        bewegt.append(n / len(aktiv))
    lebendig = (sum(1 for x in bewegt if x >= 0.10) / len(bewegt)
                if bewegt else 0.0)

    return {
        "dauer": result.duration,
        "bewegt_mittel": sum(bewegt) / len(bewegt) if bewegt else 0.0,
        "lebendig": lebendig,
        "kugel_kugel": arten.get("marble", 0) / gesamt,
        "hits_je_s": len(result.hits) / max(0.001, result.duration),
        "ausgeschieden": len(result.eliminated),
        "totzeit": max(luecken) if luecken else result.duration,
        "kammern": len(result.marks),
    }


def check(result: physics.RunResult) -> list[str]:
    """Was gegen eine Veroeffentlichung spricht. Leere Liste = brauchbar."""
    probleme: list[str] = []
    k = kennzahlen(result)
    teilnehmer = len(result.frames[0]) if result.frames else 0

    if k["dauer"] < MIN_SECONDS:
        probleme.append(f"zu kurz: {k['dauer']:.0f}s "
                        f"(Fenster {MIN_SECONDS:.0f}-{MAX_SECONDS:.0f}s)")
    if k["dauer"] > MAX_SECONDS:
        probleme.append(f"zu lang: {k['dauer']:.0f}s")

    if k["ausgeschieden"] != teilnehmer - 1:
        probleme.append(
            f"{k['ausgeschieden']} statt {teilnehmer - 1} Ausscheidungen – "
            "das Format ist nicht aufgegangen")

    if not result.finished:
        probleme.append("der Ueberlebende hat das Ziel nicht erreicht")

    if k["totzeit"] > MAX_TOTZEIT:
        probleme.append(
            f"{k['totzeit']:.0f}s am Stueck ohne Ausscheidung "
            f"(hoechstens {MAX_TOTZEIT:.0f}s)")

    if k["lebendig"] < MIN_LEBENDIG:
        probleme.append(
            f"nur {k['lebendig'] * 100:.0f} % der Laufzeit bewegt sich "
            f"ueberhaupt etwas (mindestens {MIN_LEBENDIG * 100:.0f} %) – "
            f"der Pulk steht, statt zu laufen")

    if k["kugel_kugel"] < MIN_KUGEL_KUGEL:
        probleme.append(
            f"nur {k['kugel_kugel'] * 100:.0f} % Kugel-Kugel-Aufpraelle "
            f"(mindestens {MIN_KUGEL_KUGEL * 100:.0f} %) – das Feld ist "
            "auseinandergezogen")

    return probleme


def find_seeds(anzahl: int, teilnehmer: int = 64, start: int = 1,
               grenze: int = 200) -> list[tuple[int, dict]]:
    """Seeds, die alle Annahmekriterien erfuellen. Zeigt den Ausgang NICHT."""
    treffer = []
    for seed in range(start, grenze):
        try:
            r = run(seed, teilnehmer)
        except physics.SimulationError:
            continue
        if not check(r):
            treffer.append((seed, kennzahlen(r)))
            if len(treffer) >= anzahl:
                break
    return treffer


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Disziplin 4 – Kammern")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--teilnehmer", type=int, default=64)
    ap.add_argument("--search", type=int, metavar="N")
    ap.add_argument("--verraten", action="store_true",
                    help="bei --search auch den Ausgang zeigen. NICHT "
                         "benutzen, um einen Seed auszuwaehlen.")
    ap.add_argument("--geometrie", type=int, metavar="N",
                    help="N Strecken auf Engstellen pruefen")
    ap.add_argument("--leiter", action="store_true",
                    help="nur die Kammerleiter zeigen")
    a = ap.parse_args()

    if a.leiter:
        stufen = leiter(a.teilnehmer)
        print(f"{a.teilnehmer} Teilnehmer, {len(stufen)} Kammern:")
        drin = a.teilnehmer
        for k, weiter in enumerate(stufen, start=1):
            breite = VORGABE.breite(drin, a.teilnehmer)
            print(f"  Kammer {k:>2}: {drin:>3} rein, {weiter:>3} weiter "
                  f"({drin - weiter:>2} raus)   Breite {breite:.0f} px")
            drin = weiter
        return 0

    if a.geometrie:
        print(f"Pruefe {a.geometrie} Strecken (Kugel {MARBLE_D:.0f} px) ...")
        schlecht = 0
        for seed in range(1, a.geometrie + 1):
            track = build_track(seed, a.teilnehmer)
            maengel = pruefe_durchlaesse(track, a.teilnehmer)
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

    if a.search:
        print(f"Suche {a.search} brauchbare Seeds ({a.teilnehmer} Teilnehmer) ...")
        gefunden = find_seeds(a.search, a.teilnehmer)
        print()
        print(f"{'seed':>6}  {'dauer':>7}  {'Kugel-Kugel':>12}  "
              f"{'Totzeit':>8}  {'Treffer/s':>10}")
        for seed, k in gefunden:
            print(f"{seed:>6}  {k['dauer']:>6.0f}s  "
                  f"{k['kugel_kugel'] * 100:>11.0f}%  {k['totzeit']:>7.1f}s  "
                  f"{k['hits_je_s']:>10.0f}")
        print()
        print(f"{len(gefunden)} von {a.search} gefunden")
        if not a.verraten:
            print("Der Ausgang steht hier bewusst nicht – sonst waere er "
                  "ausgesucht statt simuliert.")
        return 0

    r = run(a.seed, a.teilnehmer)
    k = kennzahlen(r)
    print(f"seed={a.seed}  {a.teilnehmer} Teilnehmer  "
          f"{k['kammern']} Kammern")
    print(f"dauer={r.duration:.0f}s  bilder={len(r.frames)}")
    print(f"ausgeschieden={k['ausgeschieden']}  im Ziel={len(r.finished)}")
    print(f"kugel-kugel={k['kugel_kugel'] * 100:.0f} %  "
          f"treffer/s={k['hits_je_s']:.0f}  totzeit={k['totzeit']:.1f}s")
    print(f"sieger={theme.competitor(r.winner).name}")
    probleme = check(r)
    print()
    if probleme:
        print("NICHT veroeffentlichen:")
        for p in probleme:
            print(f"  - {p}")
    else:
        print("brauchbar: alle Annahmekriterien erfuellt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
