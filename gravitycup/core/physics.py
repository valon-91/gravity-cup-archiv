#!/usr/bin/env python3
"""
physics.py – Gemeinsame Simulationsgrundlage aller Disziplinen.

Eine Disziplin liefert nur zwei Dinge: die **Geometrie** (Rampen, Stifte,
Startplätze) und die **Siegbedingung**. Alles andere – Aufbau des Raums,
Zeitschritte, Kollisionsprotokoll, Bildabtastung, Rangfolge – steht hier
und ist für jede Disziplin dasselbe.

Ergebnis ist ein `RunResult`: reine Daten, kein Bild, kein Ton. Erst
`draw.py` macht daraus Bilder und `audio.py` einen Ton.

CLI-Test:
  python -m gravitycup.core.physics --seed 7
  python -m gravitycup.core.physics --seed 7 --json lauf.json
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass, field, asdict
from typing import Callable

import pymunk

from . import theme

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Physikalische Grundwerte
#
# Diese Zahlen bestimmen, wie sich das Rennen anfuehlt. Sie stehen hier und
# nicht in der Disziplin, damit sich alle Disziplinen gleich anfuehlen.
# ---------------------------------------------------------------------------

GRAVITY = 1500.0
SUBSTEPS = 8                 # Rechenschritte je Bild
MAX_SECONDS = 60.0           # Notbremse

MARBLE_MASS = 1.0
MARBLE_ELASTICITY = 0.42
MARBLE_FRICTION = 0.35

WALL_ELASTICITY = 0.35
WALL_FRICTION = 0.42
PEG_ELASTICITY = 0.55
PEG_FRICTION = 0.30

#: Unter diesem Impuls wird ein Aufprall nicht protokolliert – sonst
#: besteht die Tonspur aus Rollgeraeusch.
MIN_IMPULSE = 60.0

#: Sammelkennungen fuer die Kollisionsauswertung
KIND_MARBLE, KIND_WALL, KIND_PEG = 1, 2, 3


# ---------------------------------------------------------------------------
# Was eine Disziplin liefert
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """Ein gerades Streckenstueck (Rampe, Wand, Trichter)."""

    x1: float
    y1: float
    x2: float
    y2: float
    radius: float = 9.0


@dataclass(frozen=True)
class Peg:
    """Ein runder Umlenkstift."""

    x: float
    y: float
    radius: float = 14.0


@dataclass
class Track:
    """Die Geometrie einer Runde."""

    segments: list[Segment]
    pegs: list[Peg]
    starts: list[tuple[float, float]]
    finish_y: float
    name: str = "track"

    def bounds(self) -> tuple[float, float]:
        """Oberste und unterste Weltkoordinate."""
        ys = [s.y1 for s in self.segments] + [s.y2 for s in self.segments]
        return (min(ys, default=0.0), max(ys, default=self.finish_y))


# ---------------------------------------------------------------------------
# Geometrie
#
# Diese drei Funktionen standen zuerst in descent.py. Sie stehen hier, weil
# jede Disziplin sie braucht: eine Luecke, die schmaler ist als eine Kugel,
# ist eine Falle – und genau daran hingen einmal 94 % aller Laeufe.
# ---------------------------------------------------------------------------


def abstand_zu_segment(x: float, y: float, s: Segment) -> float:
    """Kuerzester Abstand eines Punktes zur Mittellinie eines Segments."""
    dx, dy = s.x2 - s.x1, s.y2 - s.y1
    laenge2 = dx * dx + dy * dy
    if laenge2 == 0.0:
        return math.hypot(x - s.x1, y - s.y1)
    t = max(0.0, min(1.0, ((x - s.x1) * dx + (y - s.y1) * dy) / laenge2))
    return math.hypot(x - (s.x1 + t * dx), y - (s.y1 + t * dy))


def passt_durch(x: float, y: float, radius: float, segments, pegs,
                clearance: float) -> bool:
    """Bleibt neben einem Hindernis an dieser Stelle Platz fuer eine Kugel?

    Ein Stift dicht an einer Rampe ist kein Hindernis, sondern eine Falle:
    die Kugel klemmt sich dazwischen und der Lauf steht.
    """
    for s in segments:
        if abstand_zu_segment(x, y, s) < radius + s.radius + clearance:
            return False
    for p in pegs:
        if math.hypot(x - p.x, y - p.y) < radius + p.radius + clearance:
            return False
    return True


def engstellen(track: "Track", min_gap: float) -> list[str]:
    """Stellen, an denen sich eine Kugel verkeilen kann.

    Der Ersatz fuer „ist ja bisher gutgegangen". Diese Pruefung haette den
    Fehler gefunden, an dem 94 % aller Laeufe des Sturzrennens hingen:
    36 px lichte Weite zwischen Rampenende und Wand, bei 64 px Kugel.
    """
    maengel: list[str] = []
    for i, p in enumerate(track.pegs):
        for s in track.segments:
            luecke = abstand_zu_segment(p.x, p.y, s) - p.radius - s.radius
            if 0.0 < luecke < min_gap:
                maengel.append(
                    f"Stift {i} bei ({p.x:.0f},{p.y:.0f}): nur {luecke:.0f} px "
                    f"zum Segment ({s.x1:.0f},{s.y1:.0f})-({s.x2:.0f},{s.y2:.0f})")
        for j, q in enumerate(track.pegs[i + 1:], start=i + 1):
            luecke = math.hypot(p.x - q.x, p.y - q.y) - p.radius - q.radius
            if 0.0 < luecke < min_gap:
                maengel.append(f"Stifte {i}/{j}: nur {luecke:.0f} px Durchlass")
    return maengel


def linie_gequert(y_vorher: float, y_jetzt: float,
                  linie: float) -> float | None:
    """Anteil des Schrittes, bei dem `linie` nach unten gequert wurde (0..1).

    Wird bei JEDEM Rechenschritt geprueft, nicht je Bild. Zwischen zwei
    Bildern legt eine Kugel bis zu 43 Pixel zurueck – mehr als ihr eigener
    Durchmesser. Im Prototyp waren zwei Kugeln im selben Bild damit
    ununterscheidbar, und entschieden hat die zufaellige Startreihenfolge.
    In einer Liga mit Saisontabelle kippt so ein Fehlurteil die Wertung.
    """
    if y_vorher <= linie < y_jetzt:
        spanne = y_jetzt - y_vorher
        return (linie - y_vorher) / spanne if spanne else 0.0
    return None


class Regel:
    """Die Siegbedingung einer Disziplin.

    Bis B7 stand hier nur „wer zuerst unten ist", fest in `simulate`
    verdrahtet – obwohl die Doku seit B2 behauptet, eine Disziplin liefere
    „Geometrie UND Siegbedingung". Die Naht gab es also nur auf dem Papier.
    Die Eliminierung war der erste Fall, der sie wirklich gebraucht hat.

    Eine Regel bekommt jeden Rechenschritt zu sehen und sagt zwei Dinge:
    wer JETZT aus dem Spiel ist, und wann das Rennen entschieden ist. Die
    Wertung am Ende liefert sie auch – nur sie weiss, was ein Platz in
    dieser Disziplin bedeutet.
    """

    #: Beschriftung fuers Protokoll.
    name = "regel"

    def vorbereiten(self, count: int) -> None:
        self.count = count
        self.zielzeiten: dict[int, float] = {}
        self.ausgeschieden: dict[int, float] = {}

    def schritt(self, zeit_von: float, dt: float,
                y_vorher: list[float], y_jetzt: list[float],
                x_jetzt: list[float] | None = None) -> set[int]:
        """Ein Rechenschritt. Liefert, wer dadurch aus dem Spiel faellt.

        `x_jetzt` kam mit B8 dazu: die Streuung wertet nach dem LANDEFACH,
        und welches das ist, steht in der x-Position. Mit Standardwert,
        damit Regeln, die nur die Hoehe brauchen, unveraendert bleiben.
        """
        return set()

    def erledigt(self) -> bool:
        """Steht das Ergebnis fest?"""
        return len(self.zielzeiten) >= self.count

    def rangfolge(self, letzte: list[tuple[float, float, float]]) -> list[int]:
        """Vollstaendige Wertung. `letzte` ist das letzte Bild."""
        raise NotImplementedError


class RaceToLine(Regel):
    """Siegbedingung „wer zuerst unten ist" – das Sturzrennen."""

    name = "ziellinie"

    def __init__(self, finish_y: float):
        self.finish_y = finish_y

    def crossed(self, y_vorher: float, y_jetzt: float) -> float | None:
        """Beibehalten fuer Bestandstests: Anteil des Schrittes (0..1)."""
        return linie_gequert(y_vorher, y_jetzt, self.finish_y)

    def schritt(self, zeit_von: float, dt: float,
                y_vorher: list[float], y_jetzt: list[float],
                x_jetzt: list[float] | None = None) -> set[int]:
        for i in range(self.count):
            if i in self.zielzeiten:
                continue
            anteil = linie_gequert(y_vorher[i], y_jetzt[i], self.finish_y)
            if anteil is not None:
                self.zielzeiten[i] = zeit_von + anteil * dt
        return set()

    def rangfolge(self, letzte) -> list[int]:
        # Erst die Angekommenen nach exakter Zielzeit, dann der Rest nach
        # erreichter Tiefe. So bleibt die Wertung IMMER vollstaendig – im
        # Prototyp fehlten Nachzuegler einfach in der Liste und haetten in
        # einer Saisontabelle stillschweigend null Punkte bekommen.
        angekommen = sorted(self.zielzeiten, key=lambda i: self.zielzeiten[i])
        rest = sorted((i for i in range(self.count) if i not in self.zielzeiten),
                      key=lambda i: -letzte[i][1])
        return angekommen + rest


# ---------------------------------------------------------------------------
# Was die Simulation liefert
# ---------------------------------------------------------------------------


@dataclass
class Hit:
    """Ein protokollierter Aufprall – Grundlage der Tonspur."""

    frame: int
    impulse: float
    x: float
    y: float
    competitor: int
    kind: str          # "wall" | "peg" | "marble"


@dataclass
class RunResult:
    """Das vollstaendige Ergebnis eines Laufs. Reine Daten."""

    seed: int
    fps: int
    track_name: str
    frames: list[list[tuple[float, float, float]]]   # je Bild: (x, y, winkel)
    hits: list[Hit]
    order: list[int]                 # Rangfolge, IMMER vollstaendig
    finished: list[int]              # wer wirklich im Ziel ankam
    finish_times: dict[int, float]   # Sekunden, nur fuer Angekommene
    finish_frame: int | None         # Bild, in dem der Erste ankam
    segments: list[Segment]
    pegs: list[Peg]
    finish_y: float
    #: Wer wann ausgeschieden ist, in Sekunden. Leer bei Disziplinen ohne
    #: Ausscheiden. Mit Standardwert, damit aeltere state.json weiter laden.
    eliminated: dict[int, float] = field(default_factory=dict)
    #: Waagrechte Linien, die die Disziplin sichtbar machen will
    #: (Kontrollpunkte der Eliminierung). Rein zum Zeichnen.
    marks: list[float] = field(default_factory=list)
    #: Was eine Disziplin sonst noch ins Bild bringen will – bei der
    #: Streuung die Landefaecher samt Punktwert. Absichtlich EIN
    #: allgemeines Feld statt eines je Disziplin: bei acht Disziplinen
    #: waere `RunResult` sonst eine Sammelstelle fuer Sonderfaelle.
    #: Muss JSON-faehig bleiben, weil es durch state.json geht.
    extras: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return len(self.frames) / self.fps

    @property
    def winner(self) -> int:
        return self.order[0]

    def eliminated_frame(self, i: int) -> int | None:
        """Bild, in dem Teilnehmer i ausgeschieden ist."""
        zeit = self.eliminated.get(i)
        return None if zeit is None else int(zeit * self.fps)

    def summary(self) -> str:
        namen = [theme.competitor(i).name for i in self.order]
        fehlend = [theme.competitor(i).name
                   for i in self.order
                   if i not in self.finished and i not in self.eliminated]
        zeilen = [
            f"seed={self.seed}  strecke={self.track_name}",
            f"bilder={len(self.frames)}  dauer={self.duration:.1f}s",
            f"sieger={namen[0]}  ({self.finish_times.get(self.order[0], 0):.2f}s)",
            f"reihenfolge={' > '.join(namen)}",
            f"aufpraelle={len(self.hits)}",
        ]
        if self.eliminated:
            raus = ", ".join(
                f"{theme.competitor(i).name} bei {t:.1f}s"
                for i, t in sorted(self.eliminated.items(), key=lambda kv: kv[1]))
            zeilen.append(f"ausgeschieden: {raus}")
        if fehlend:
            zeilen.append(
                f"nicht im Ziel: {', '.join(fehlend)} "
                f"(nach Position gewertet)"
            )
        return "\n".join(zeilen)


class SimulationError(RuntimeError):
    """Der Lauf ist unbrauchbar – lieber abbrechen als ein kaputtes Video."""


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


def simulate(track: Track, seed: int, *, fps: int = theme.FPS,
             max_seconds: float = MAX_SECONDS,
             tail_seconds: float = 1.6,
             patience_seconds: float = 6.0,
             count: int | None = None,
             regel: Regel | None = None,
             marks: list[float] | None = None,
             extras: dict | None = None) -> RunResult:
    """Rechnet einen kompletten Lauf.

    `seed` ist die EINZIGE Zufallsquelle – Startreihenfolge, Streuung und
    spaeter auch der Ton leiten sich davon ab. Gleicher Seed und gleiche
    Strecke ergeben denselben Lauf.

    `regel` ist die Siegbedingung der Disziplin. Ohne Angabe gilt „wer
    zuerst unten ist" – das Sturzrennen.
    """
    if count is None:
        count = len(theme.competitors())
    if len(track.starts) < count:
        raise SimulationError(
            f"Strecke bietet {len(track.starts)} Startplaetze, "
            f"gebraucht werden {count}"
        )

    rng = random.Random(seed)
    space = pymunk.Space()
    space.gravity = (0.0, GRAVITY)

    static = space.static_body
    for s in track.segments:
        shape = pymunk.Segment(static, (s.x1, s.y1), (s.x2, s.y2), s.radius)
        shape.elasticity, shape.friction = WALL_ELASTICITY, WALL_FRICTION
        shape.collision_type = KIND_WALL
        space.add(shape)
    for p in track.pegs:
        shape = pymunk.Circle(static, p.radius, (p.x, p.y))
        shape.elasticity, shape.friction = PEG_ELASTICITY, PEG_FRICTION
        shape.collision_type = KIND_PEG
        space.add(shape)

    # Startplaetze werden ZUFAELLIG zugelost. Welcher Platz besser ist,
    # entscheidet die Geometrie – niemand soll ihn sich aussuchen koennen.
    plaetze = list(range(count))
    rng.shuffle(plaetze)

    bodies: list[pymunk.Body] = []
    shapes: list[pymunk.Circle] = []
    for teilnehmer, platz in enumerate(plaetze):
        x, y = track.starts[platz]
        body = pymunk.Body(
            MARBLE_MASS,
            pymunk.moment_for_circle(MARBLE_MASS, 0, theme.MARBLE_RADIUS),
        )
        body.position = (x, y)
        shape = pymunk.Circle(body, theme.MARBLE_RADIUS)
        shape.elasticity, shape.friction = MARBLE_ELASTICITY, MARBLE_FRICTION
        shape.collision_type = KIND_MARBLE
        shape.competitor = teilnehmer
        space.add(body, shape)
        bodies.append(body)
        shapes.append(shape)

    hits: list[Hit] = []
    zustand = {"frame": 0}

    def on_hit(arbiter, space_, data):
        if not arbiter.is_first_contact:
            return
        impuls = arbiter.total_impulse.length
        if impuls < MIN_IMPULSE:
            return
        a, b = arbiter.shapes
        arten = {a.collision_type, b.collision_type}
        teilnehmer = getattr(a, "competitor", getattr(b, "competitor", 0))

        # Ort des Aufpralls aus dem KONTAKTPUNKT, nicht aus den
        # Koerpermittelpunkten. Der Prototyp mittelte ueber beide Koerper –
        # bei Wand und Stift ist der zweite Koerper der statische Raum mit
        # Mittelpunkt (0,0), wodurch jede X-Position halbiert wurde. Die
        # rechte Bildhaelfte klappte so in die Mitte, und genau daraus wird
        # das Stereopanorama gerechnet.
        punkte = arbiter.contact_point_set.points
        if punkte:
            px = (punkte[0].point_a.x + punkte[0].point_b.x) / 2
            py = (punkte[0].point_a.y + punkte[0].point_b.y) / 2
        else:
            px, py = a.body.position.x, a.body.position.y

        if arten == {KIND_MARBLE}:
            art = "marble"
        elif KIND_PEG in arten:
            art = "peg"
        else:
            art = "wall"

        hits.append(Hit(zustand["frame"], round(impuls, 1),
                        round(px, 1), round(py, 1), teilnehmer, art))

    space.on_collision(post_solve=on_hit)

    if regel is None:
        regel = RaceToLine(track.finish_y)
    regel.vorbereiten(count)

    dt = 1.0 / (fps * SUBSTEPS)
    frames: list[list[tuple[float, float, float]]] = []
    finish_frame: int | None = None
    schritt = 0
    gesamt_bilder = int(max_seconds * fps)

    for f in range(gesamt_bilder):
        zustand["frame"] = f
        for _ in range(SUBSTEPS):
            vorher = [b.position.y for b in bodies]
            space.step(dt)
            zeit_von = schritt * dt
            schritt += 1
            # Die Regel sieht JEDEN Rechenschritt, nicht nur jedes Bild.
            raus = regel.schritt(zeit_von, dt, vorher,
                                 [b.position.y for b in bodies],
                                 [b.position.x for b in bodies])
            for i in raus:
                # Aus dem Spiel heisst: raus aus dem Raum. Die Kugel bleibt
                # stehen, wo sie war, und stoert die anderen nicht mehr –
                # eine liegengebliebene Kugel mitten auf der Strecke waere
                # ein Hindernis, das der Zuschauer nicht erklaeren kann.
                if shapes[i] in space.shapes:
                    space.remove(shapes[i], bodies[i])

        frames.append([
            (round(b.position.x, 1), round(b.position.y, 1), round(b.angle, 3))
            for b in bodies
        ])

        # `finish_frame` haengt an den ZIELZEITEN, nicht an Ausscheidungen.
        #
        # Die Geduldsuhr laeuft ab dem ersten Zieleinlauf. Zaehlte auch eine
        # Ausscheidung als Startsignal, waere bei der Eliminierung sechs
        # Sekunden nach dem ERSTEN Tor Schluss – gemessen: 26 von 40 Seeds
        # endeten mit einer statt vier Ausscheidungen. Ein Ausscheiden ist
        # kein Zieleinlauf, sondern der Anfang vom Rennen.
        if regel.zielzeiten and finish_frame is None:
            finish_frame = f

        # Nachlauf erst starten, wenn das Ergebnis feststeht – sonst faellt
        # die Wertung der Nachzuegler auf eine Schaetzung nach Position
        # zurueck, und in einer Saisontabelle waeren das echte Punkte aus
        # geratenen Plaetzen. Wer zu lange braucht, wird trotzdem nicht
        # ewig abgewartet.
        if finish_frame is not None:
            geduld_aus = f > finish_frame + int(patience_seconds * fps)
            if regel.erledigt() or geduld_aus:
                letzter = max(
                    (int(t * fps) for t in regel.zielzeiten.values()),
                    default=finish_frame,
                )
                if f > max(letzter, finish_frame) + int(tail_seconds * fps):
                    break

    if not frames:
        raise SimulationError("Kein einziges Bild simuliert")

    finish_times = dict(regel.zielzeiten)

    # Die Wertung macht die REGEL – nur sie weiss, was ein Platz in dieser
    # Disziplin bedeutet. Sie ist immer vollstaendig; im Prototyp fehlten
    # Nachzuegler einfach in der Liste und haetten in einer Saisontabelle
    # stillschweigend null Punkte bekommen.
    letzte = frames[-1]
    order = regel.rangfolge(letzte)
    if sorted(order) != list(range(count)):
        raise SimulationError(
            f"Regel {regel.name!r} liefert eine unvollstaendige Wertung: "
            f"{order} fuer {count} Teilnehmer")

    angekommen = sorted(finish_times, key=lambda i: finish_times[i])

    if not angekommen and not regel.ausgeschieden:
        # Sagen, WO sie haengengeblieben sind – beim Streckenbau ist das
        # die eigentliche Information.
        orte = ", ".join(
            f"{theme.competitor(i).name} bei y={letzte[i][1]:.0f}"
            for i in range(count)
        )
        raise SimulationError(
            f"Nach {len(frames) / fps:.1f}s ist nichts passiert "
            f"(seed={seed}, Regel {regel.name!r}, "
            f"Ziel bei y={track.finish_y:.0f}).\n"
            f"  Letzte Positionen: {orte}"
        )

    return RunResult(
        seed=seed,
        fps=fps,
        track_name=track.name,
        frames=frames,
        hits=hits,
        order=order,
        finished=angekommen,
        finish_times=finish_times,
        finish_frame=finish_frame,
        segments=track.segments,
        pegs=track.pegs,
        finish_y=track.finish_y,
        eliminated=dict(regel.ausgeschieden),
        marks=list(marks or []),
        extras=dict(extras or {}),
    )


# ---------------------------------------------------------------------------
# Speichern und Laden
# ---------------------------------------------------------------------------


def to_dict(r: RunResult) -> dict:
    d = asdict(r)
    d["hits"] = [asdict(h) for h in r.hits]
    d["segments"] = [asdict(s) for s in r.segments]
    d["pegs"] = [asdict(p) for p in r.pegs]
    d["finish_times"] = {str(k): v for k, v in r.finish_times.items()}
    d["eliminated"] = {str(k): v for k, v in r.eliminated.items()}
    return d


def from_dict(d: dict) -> RunResult:
    return RunResult(
        seed=d["seed"],
        fps=d["fps"],
        track_name=d["track_name"],
        frames=[[tuple(p) for p in bild] for bild in d["frames"]],
        hits=[Hit(**h) for h in d["hits"]],
        order=d["order"],
        finished=d["finished"],
        finish_times={int(k): v for k, v in d["finish_times"].items()},
        finish_frame=d["finish_frame"],
        segments=[Segment(**s) for s in d["segments"]],
        pegs=[Peg(**p) for p in d["pegs"]],
        finish_y=d["finish_y"],
        # Mit Standardwerten – aeltere state.json kennen die Felder nicht.
        eliminated={int(k): v for k, v in (d.get("eliminated") or {}).items()},
        marks=list(d.get("marks") or []),
        extras=dict(d.get("extras") or {}),
    )


def save(r: RunResult, pfad) -> None:
    with open(pfad, "w", encoding="utf-8") as fh:
        json.dump(to_dict(r), fh)


def load(pfad) -> RunResult:
    with open(pfad, encoding="utf-8") as fh:
        return from_dict(json.load(fh))


# ---------------------------------------------------------------------------
# Eine Probestrecke, damit dieses Modul allein testbar ist.
# Die richtige Strecke des Sturzrennens kommt in B4.
# ---------------------------------------------------------------------------

WALL_LEFT, WALL_RIGHT = 40.0, 1040.0


def demo_track(seed: int = 7, ramps: int = 12) -> Track:
    """Zickzack-Strecke – bewusst schlicht, nur zum Pruefen dieses Moduls."""
    rng = random.Random(seed * 31 + 5)
    segments: list[Segment] = []
    pegs: list[Peg] = []

    top, gap, drop = 700.0, 430.0, 250.0
    for i in range(ramps):
        y = top + i * gap
        if i % 2 == 0:
            segments.append(Segment(WALL_LEFT + 20, y, 900, y + drop))
        else:
            segments.append(Segment(WALL_RIGHT - 20, y, 180, y + drop))
        for _ in range(2):
            pegs.append(Peg(rng.uniform(220, 860), y + drop + rng.uniform(60, 150)))

    bottom = top + ramps * gap + 120
    mitte = theme.WIDTH / 2
    segments.append(Segment(WALL_LEFT + 20, bottom, mitte - 150, bottom + 260))
    segments.append(Segment(WALL_RIGHT - 20, bottom, mitte + 150, bottom + 260))
    finish_y = bottom + 400
    segments.append(Segment(WALL_LEFT, finish_y + 150, WALL_RIGHT, finish_y + 150))
    segments.append(Segment(WALL_LEFT, 0, WALL_LEFT, finish_y + 160))
    segments.append(Segment(WALL_RIGHT, 0, WALL_RIGHT, finish_y + 160))

    # Startplaetze: ALLE auf gleicher Hoehe, nebeneinander.
    # Im Prototyp standen sie diagonal ueber 312 Pixel gestaffelt – der
    # unterste Platz erreichte die erste Rampe rund 7,6 Bilder frueher.
    # Ausgeglichen wurde das nur im Mittel ueber viele Laeufe; innerhalb
    # EINES Rennens war der Vorteil echt.
    starts = [(mitte + (i - 2) * 78.0, 150.0) for i in range(5)]

    return Track(segments=segments, pegs=pegs, starts=starts,
                 finish_y=finish_y, name=f"demo-{ramps}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Einzeltest Baustein B2")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--ramps", type=int, default=12)
    ap.add_argument("--json", help="Lauf als JSON speichern")
    ap.add_argument("--headless", action="store_true",
                    help="nur rechnen und berichten (Standard)")
    a = ap.parse_args()

    import time
    t0 = time.perf_counter()
    ergebnis = simulate(demo_track(a.seed, a.ramps), a.seed)
    dauer = time.perf_counter() - t0

    print(ergebnis.summary())
    print(f"gerechnet in {dauer:.2f}s")

    if a.json:
        save(ergebnis, a.json)
        print(f"gespeichert: {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
