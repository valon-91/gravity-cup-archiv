#!/usr/bin/env python3
"""
standings.py – Baustein B6: der Punktestand einer Saison.

Der Punktestand wird **nicht gefuehrt, sondern gerechnet**.

Quelle ist immer das Rundenarchiv `runs/*.json`, das B5 je Folge schreibt.
Es gibt keinen mitlaufenden Zaehler, den jemand von Hand korrigieren
koennte, und keine Datei, die stillschweigend von der Wirklichkeit
abweicht: wer die Tabelle anzweifelt, rechnet sie aus denselben Dateien
nach, aus denen auch die Videos entstanden sind.

Ein gespeicherter Stand (`--json`) ist deshalb nur eine Momentaufnahme fuer
Grafik und Community-Posts – niemals die Wahrheit.

CLI:
  python -m gravitycup.season.standings                 # aktuelle Tabelle
  python -m gravitycup.season.standings --saison 1
  python -m gravitycup.season.standings --json data/stand.json
  python -m gravitycup.season.standings --verlauf       # Runde fuer Runde
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..core import theme

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARCHIV = PROJECT_ROOT / "runs"

#: Punkte fuer Platz 1 bis 5.
#:
#: Gemessen an 12 Saisons zu je 24 echten Runden (dieselben Laeufe, nur
#: anders bewertet – sonst vergleicht man Schluessel gegen Zufall):
#:
#:   Schluessel      Fuehrungswechsel   Gleichstand   Vorsprung   Spanne
#:                      je Saison        an Spitze       1./2.     1./5.
#:   5-4-3-2-1              7,7             17 %          5,8      16,1
#:   8-5-3-2-1              6,3              0 %          9,9      28,2
#:   10-6-4-2-1             6,6              8 %         12,2      36,2   <-
#:   12-6-3-1-0             5,9              0 %         15,9      48,8
#:   3-2-1-0-0              8,3              8 %          4,3      13,4
#:
#: Flache Schluessel halten die Tabelle laenger offen, enden aber mit
#: Vorspruengen, die nach Zufall aussehen – bei 5-4-3-2-1 sogar in 17 %
#: der Saisons ohne Sieger. Steile Schluessel geben eine klare Tabelle,
#: kosten aber Fuehrungswechsel, und die sind der Grund zum Wiederkommen.
#:
#: 10-6-4-2-1 liegt bei den Fuehrungswechseln fast auf dem flachen
#: Schluessel (6,6 gegen 7,7), liefert aber einen lesbaren Endstand. Dazu
#: kommt ein inhaltliches Argument: der Kanal fragt „Which color wins?".
#: Bei 5-4-3-2-1 ist ein Sieg genau einen Punkt mehr wert als Platz zwei –
#: das entwertet die Frage, mit der jedes Video anfaengt. Und niemand steht
#: auf null: auch der Letzte nimmt einen Punkt mit.
#:
#: Aendern heisst: diese Zeile. Aber nur zwischen zwei Saisons – mitten in
#: einer Saison waere jede bereits veroeffentlichte Tabelle falsch.
PUNKTE: tuple[int, ...] = (10, 6, 4, 2, 1)

#: Rundenbezeichnung im Archiv, z. B. S01R07.
RUNDE_MUSTER = re.compile(r"^S(\d+)R(\d+)$", re.IGNORECASE)


class ArchivFehler(RuntimeError):
    """Das Archiv ist nicht auswertbar – lieber abbrechen als falsch rechnen."""


@dataclass(frozen=True)
class Runde:
    """Eine gewertete Runde, gelesen aus einem Rundenmanifest."""

    saison: int
    nummer: int
    name: str
    disziplin: str
    seed: int
    reihenfolge: tuple[int, ...]        # Startnummern, Sieger zuerst
    erzeugt: str
    manifest: Path
    #: Was beim Bauen gegen eine Veroeffentlichung sprach. Nicht leer heisst:
    #: die Folge wurde mit --trotzdem gebaut.
    maengel: tuple[str, ...] = ()
    #: Punkteschluessel, mit dem die Folge veroeffentlicht wurde. None bei
    #: aelteren Manifesten, die das Feld noch nicht hatten.
    punkteschluessel: tuple[int, ...] | None = None

    @property
    def sieger(self) -> int:
        return self.reihenfolge[0]


@dataclass
class Eintrag:
    """Eine Zeile der Tabelle."""

    teilnehmer: int
    punkte: int = 0
    runden: int = 0
    #: Wie oft dieser Teilnehmer auf Platz 1, 2, 3 ... war.
    #: Laenge nach der TEILNEHMERZAHL, nicht nach der Laenge des
    #: Punkteschluessels – `berechne()` erlaubt einen abweichenden
    #: Schluessel, und dessen Laenge sagt nichts ueber die Anzahl der
    #: moeglichen Plaetze.
    plaetze: list[int] = field(
        default_factory=lambda: [0] * len(theme.competitors()))
    letzter_platz: int | None = None     # Platz in der juengsten Runde

    @property
    def name(self) -> str:
        return theme.competitor(self.teilnehmer).name

    @property
    def siege(self) -> int:
        return self.plaetze[0]


def lies_manifest(pfad: Path) -> Runde | None:
    """Ein Rundenmanifest einlesen. `None`, wenn es nicht zur Saison gehoert."""
    try:
        m = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ArchivFehler(f"{pfad.name} ist nicht lesbar: {e}") from e

    name = m.get("runde")
    if not name:
        # Ein Probelauf ohne --runde. Zaehlt nicht zur Saison, ist aber auch
        # kein Fehler – deshalb still uebergehen.
        return None
    if m.get("format") == "show":
        # Langform-Manifeste (SHOW-xx) liegen bewusst im Archiv: der
        # Pruefbefehl unter dem Video braucht sie. Zur Saison zaehlen sie
        # nicht – kein SxxRyy-Name, keine Rangfolge ueber die Stammbesetzung.
        # Nur DIESES Merkmal wird still uebergangen; ein verschriebener
        # Saisonname faellt weiterhin unten laut durch. Gemessen am
        # 03.08.2026: SHOW-01.json legte die gesamte Auswertung drei Tage
        # still, waehrend 343 Tests gruen waren – kein Test lief ueber das
        # echte runs/-Verzeichnis.
        return None
    treffer = RUNDE_MUSTER.match(str(name))
    if not treffer:
        raise ArchivFehler(
            f"{pfad.name}: Rundenbezeichnung {name!r} passt nicht auf SxxRyy")

    ergebnis = m.get("ergebnis") or {}
    reihenfolge = ergebnis.get("reihenfolge_index")
    if not reihenfolge:
        raise ArchivFehler(
            f"{pfad.name}: kein Feld ergebnis.reihenfolge_index – "
            "aus diesem Manifest laesst sich keine Wertung ableiten")
    if sorted(reihenfolge) != list(range(len(theme.competitors()))):
        raise ArchivFehler(
            f"{pfad.name}: reihenfolge_index {reihenfolge} ist keine "
            f"vollstaendige Rangfolge ueber {len(theme.competitors())} Teilnehmer")

    return Runde(
        saison=int(treffer.group(1)),
        nummer=int(treffer.group(2)),
        name=str(name).upper(),
        disziplin=m.get("disziplin", "?"),
        seed=m.get("seed", -1),
        reihenfolge=tuple(reihenfolge),
        erzeugt=m.get("erzeugt", ""),
        manifest=pfad,
        maengel=tuple(m.get("annahme") or ()),
        punkteschluessel=(tuple(m["punkteschluessel"])
                          if m.get("punkteschluessel") else None),
    )


def lade_runden(archiv: Path = ARCHIV, saison: int | None = None) -> list[Runde]:
    """Alle gewerteten Runden, aufsteigend nach Saison und Nummer."""
    if not archiv.exists():
        return []

    runden: list[Runde] = []
    for pfad in sorted(archiv.glob("*.json")):
        runde = lies_manifest(pfad)
        if runde is not None:
            runden.append(runde)

    if saison is not None:
        runden = [r for r in runden if r.saison == saison]

    # Doppelte Rundennummern wuerden doppelt zaehlen. Das faellt in der
    # Tabelle nicht auf – deshalb hier abbrechen statt still weiterrechnen.
    gesehen: dict[tuple[int, int], Path] = {}
    for r in runden:
        schluessel = (r.saison, r.nummer)
        if schluessel in gesehen:
            raise ArchivFehler(
                f"Runde {r.name} kommt zweimal vor:\n"
                f"  {gesehen[schluessel].name}\n  {r.manifest.name}\n"
                "Eine davon loeschen – sonst wird sie doppelt gewertet.")
        gesehen[schluessel] = r.manifest

    return sorted(runden, key=lambda r: (r.saison, r.nummer))


def hinweise(runden: list[Runde],
             punkte: tuple[int, ...] = PUNKTE) -> list[str]:
    """Was an einer Tabelle stimmen KANN, aber erklaert gehoert.

    Kein Abbruch – die Zahlen sind ja richtig gerechnet. Aber jeder dieser
    Faelle heisst, dass die Tabelle etwas anderes zeigt, als jemand
    erwartet, der nur die veroeffentlichten Folgen kennt.
    """
    raus: list[str] = []

    # Luecken in der Nummerierung. Eine fehlende Runde faellt in der Tabelle
    # nicht auf – die Punkte sind einfach kleiner, und niemand weiss, warum.
    nach_saison: dict[int, list[int]] = {}
    for r in runden:
        nach_saison.setdefault(r.saison, []).append(r.nummer)
    for saison, nummern in sorted(nach_saison.items()):
        fehlend = sorted(set(range(1, max(nummern) + 1)) - set(nummern))
        if fehlend:
            raus.append(
                f"Saison {saison}: Runde "
                + ", ".join(f"R{n:02d}" for n in fehlend)
                + " fehlt im Archiv – die Tabelle rechnet ohne sie.")

    # Mit --trotzdem gebaute Folgen. Sie zaehlen normal mit, obwohl B5 sie
    # als nicht veroeffentlichungsreif eingestuft hat.
    mangelhaft = [r for r in runden if r.maengel]
    for r in mangelhaft:
        raus.append(
            f"{r.name} wurde trotz Maengeln gebaut ({r.maengel[0]}) "
            "und zaehlt trotzdem voll.")

    # Nachtraeglich geaenderter Punkteschluessel.
    abweichend = {r.punkteschluessel for r in runden
                  if r.punkteschluessel and tuple(r.punkteschluessel) != tuple(punkte)}
    for alt in abweichend:
        raus.append(
            f"Es gibt Runden, die mit {'-'.join(str(p) for p in alt)} "
            f"veroeffentlicht wurden, gerechnet wird mit "
            f"{'-'.join(str(p) for p in punkte)} – die Tabelle weicht von "
            "dem ab, was damals im Video stand.")

    return raus


def sortierschluessel(e: Eintrag) -> tuple:
    """Gleichstandsregel.

    In 8 % der gemessenen Saisons endet die Tabelle nach Punkten
    unentschieden – die Regel ist also kein Zierrat, sondern entscheidet
    regelmaessig den Saisonsieg.

    Der Reihe nach: Punkte, dann Siege, dann zweite Plaetze, dritte, ...,
    zuletzt das Ergebnis der juengsten Runde. Was NICHT vorkommt, ist die
    Startnummer – nach demselben Grundsatz, aus dem B2 den Gleichstand am
    Ziel per Subframe aufloest statt per Auslosung: kein Platz darf einen
    Vorteil haben, den er nicht erlaufen hat.

    Weil in einer Runde nie zwei Teilnehmer denselben Platz belegen,
    loest spaetestens die juengste Runde jeden Gleichstand auf: es gibt
    IMMER einen Ersten, sobald ueberhaupt eine Runde gelaufen ist.
    """
    return (-e.punkte, *[-n for n in e.plaetze],
            e.letzter_platz if e.letzter_platz is not None else len(PUNKTE))


def berechne(runden: list[Runde],
             punkte: tuple[int, ...] = PUNKTE) -> list[Eintrag]:
    """Die Tabelle. Sortiert, Fuehrender zuerst."""
    if len(punkte) < len(theme.competitors()):
        raise ArchivFehler(
            f"Punkteschluessel hat {len(punkte)} Werte, "
            f"es gibt aber {len(theme.competitors())} Teilnehmer")

    eintraege = {i: Eintrag(teilnehmer=i)
                 for i in range(len(theme.competitors()))}
    for runde in runden:
        for platz, i in enumerate(runde.reihenfolge):
            e = eintraege[i]
            e.punkte += punkte[platz]
            e.runden += 1
            e.plaetze[platz] += 1
            e.letzter_platz = platz
    return sorted(eintraege.values(), key=sortierschluessel)


def punktgleich_an_der_spitze(tabelle: list[Eintrag]) -> bool:
    """Haben die ersten beiden dieselbe Punktzahl?

    Gemessen an 12 Saisons passiert das in 8 % der Faelle. Die Tabelle hat
    dann trotzdem eine eindeutige Reihenfolge – `sortierschluessel` loest
    das ueber Siege, Platzverteilung und zuletzt die juengste Runde auf, und
    weil in einer Runde nie zwei Teilnehmer denselben Platz belegen, bleibt
    danach nie ein echtes Unentschieden uebrig. Es gibt also immer einen
    Ersten; die Grafik weist nur darauf hin, dass es nach Punkten knapp ist.
    """
    return len(tabelle) > 1 and tabelle[0].punkte == tabelle[1].punkte


def als_dict(tabelle: list[Eintrag], runden: list[Runde],
             saison: int | None = None) -> dict:
    """Momentaufnahme fuer Grafik und Community-Post.

    Ausdruecklich KEINE Quelle: neu gerechnet wird immer aus `runs/*.json`.
    """
    return {
        "kanal": "GRAVITY CUP",
        "saison": saison,
        "runden": len(runden),
        "letzte_runde": runden[-1].name if runden else None,
        "punkteschluessel": list(PUNKTE),
        "quelle": "gerechnet aus runs/*.json – dieser Stand ist eine "
                  "Momentaufnahme, keine Quelle",
        "punktgleich_an_der_spitze": punktgleich_an_der_spitze(tabelle),
        "tabelle": [
            {
                "platz": platz + 1,
                "teilnehmer": e.teilnehmer,
                "name": e.name,
                "punkte": e.punkte,
                "runden": e.runden,
                "siege": e.siege,
                "plaetze": e.plaetze,
            }
            for platz, e in enumerate(tabelle)
        ],
        "verlauf": [
            {"runde": r.name, "disziplin": r.disziplin, "seed": r.seed,
             "reihenfolge": [theme.competitor(i).name for i in r.reihenfolge]}
            for r in runden
        ],
    }


def punkte_je_platz() -> list[int]:
    """Der Schluessel als Liste – fuer die Ergebniskarte im Video."""
    return list(PUNKTE)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _drucke_tabelle(tabelle: list[Eintrag], runden: list[Runde]) -> None:
    breite = max(len(e.name) for e in tabelle)
    print(f"  {'':>2}  {'':<{breite}}  {'Punkte':>6}  {'Siege':>5}  "
          f"{'Runden':>6}   Plaetze 1-5")
    for platz, e in enumerate(tabelle, start=1):
        verteilung = " ".join(f"{n:>2}" for n in e.plaetze)
        print(f"  {platz:>2}. {e.name:<{breite}}  {e.punkte:>6}  "
              f"{e.siege:>5}  {e.runden:>6}   {verteilung}")
    if punktgleich_an_der_spitze(tabelle):
        print()
        print(f"  Die ersten beiden stehen punktgleich bei {tabelle[0].punkte}.")
        print("  Entschieden ueber Siege, Platzverteilung, juengste Runde.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Baustein B6 – Punktestand")
    ap.add_argument("--saison", type=int, help="nur diese Saison werten")
    ap.add_argument("--archiv", default=str(ARCHIV))
    ap.add_argument("--json", help="Momentaufnahme speichern")
    ap.add_argument("--verlauf", action="store_true",
                    help="jede Runde einzeln auflisten")
    a = ap.parse_args()

    try:
        runden = lade_runden(Path(a.archiv), a.saison)
    except ArchivFehler as e:
        print(f"Archiv nicht auswertbar:\n  {e}")
        return 1

    if not runden:
        print(f"Keine gewerteten Runden in {a.archiv}.")
        print("Eine Runde zaehlt erst, wenn sie mit --runde SxxRyy gebaut wurde:")
        print("  python -m gravitycup.build --seed 1 --runde S01R01 --out folge01.mp4")
        return 0

    saisons = sorted({r.saison for r in runden})
    kopf = (f"Saison {saisons[0]}" if len(saisons) == 1
            else f"Saisons {saisons[0]}-{saisons[-1]}")
    print(f"{kopf} · {len(runden)} Runden · "
          f"Punkte {'-'.join(str(p) for p in PUNKTE)}")
    print()

    if a.verlauf:
        for r in runden:
            namen = " > ".join(theme.competitor(i).name for i in r.reihenfolge)
            print(f"  {r.name}  {r.disziplin:<10} seed={r.seed:<5} {namen}")
        print()

    tabelle = berechne(runden)
    _drucke_tabelle(tabelle, runden)

    warnungen = hinweise(runden)
    if warnungen:
        print()
        for w in warnungen:
            print(f"  ! {w}")

    if a.json:
        ziel = Path(a.json)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(
            json.dumps(als_dict(tabelle, runden,
                                saisons[0] if len(saisons) == 1 else None),
                       indent=2, ensure_ascii=False),
            encoding="utf-8")
        print()
        print(f"gespeichert: {ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
