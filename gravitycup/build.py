#!/usr/bin/env python3
"""
build.py – Baustein B5: Disziplin und Seed rein, fertige MP4 raus.

Der Ablauf in fuenf Schritten:

  1. Lauf rechnen (oder aus dem Zwischenspeicher holen)   -> state.json
  2. Annahmekriterien pruefen                             -> Abbruch statt Schrott
  3. Ton rechnen (oder aus dem Zwischenspeicher holen)    -> race.wav
  4. Bilder zeichnen und roh an ffmpeg schieben           -> out.mp4
  5. Rundenarchiv schreiben                               -> runs/*.json

Der Ton kommt VOR den Bildern, weil ffmpeg die WAV-Datei als zweite Quelle
schon beim Start braucht.

Das Rundenarchiv ist kein Beiwerk. Der Kanal verspricht „der Ausgang wird
simuliert, nicht geschrieben" – nachpruefbar ist das nur, wenn zu jeder Folge
Seed, Codestand, Bibliotheksversionen und Ergebnis festgehalten sind. Genau
das macht `--pruefen` nachrechenbar.

CLI:
  python -m gravitycup.build --seed 2 --out out.mp4
  python -m gravitycup.build --seed 2 --runde S01R01 --out out.mp4
  python -m gravitycup.build --seed 2 --vorschau            # klein und schnell
  python -m gravitycup.build --pruefen runs/S01R01.json     # nachrechnen
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

from .core import audio, draw, physics, theme
from .disciplines import descent, elimination, scatter
from .season import standings

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Rundenarchiv. Gehoert ins Git – im Gegensatz zu data/ und den MP4s.
#: Aus diesen Dateien laesst sich jede veroeffentlichte Runde nachrechnen,
#: ohne dass jemand Gigabyte an Videos aufheben muss.
ARCHIV = PROJECT_ROOT / "runs"

#: Zwischenspeicher. Gross, wegwerfbar, deshalb unter data/ (gitignoriert).
CACHE = PROJECT_ROOT / "data" / "cache"

DISZIPLINEN = {d.NAME: d for d in (descent, elimination, scatter)}

# ---------------------------------------------------------------------------
# Zeitablauf der Einblendungen, in Bildern bei theme.FPS
#
# Der Hook steht ganz vorn: die ersten zwei Sekunden entscheiden, ob jemand
# weiterschaut. Danach uebernimmt die Rangliste, und kurz vor Schluss die
# Ergebniskarte.
# ---------------------------------------------------------------------------

#: Der Aufhaenger steht 6..62, voll deckend 16..50 – gut eine Sekunde zum
#: Lesen. Laenger geht nicht: das Feld zieht sich auseinander und waechst
#: dem Kasten entgegen (siehe HOOK_KAMERA_VERSATZ).
HOOK_START, HOOK_EIN, HOOK_HALT, HOOK_AUS = 6, 10, 34, 12
HOOK_ENDE = HOOK_START + HOOK_EIN + HOOK_HALT + HOOK_AUS   # 62
HUD_START = HOOK_ENDE
HUD_EIN = 12

#: So viele Sekunden vor dem letzten Rennbild beginnt die Ergebniskarte.
KARTE_VORLAUF = 1.0
KARTE_EIN = 12

#: Kamera-Versatz waehrend des Aufhaengers, in Weltpixeln nach unten.
#:
#: Die Kamera haengt am FUEHRENDEN (theme.CAMERA_ANCHOR = 45 % Bildhoehe).
#: Sobald sich das Feld auseinanderzieht, wandern die Hinteren nach oben –
#: gemessen an seed 2 standen von Bild 30 bis 78 bis zu DREI von fuenf
#: Kugeln hinter dem Aufhaengerkasten. Genau in den Sekunden, in denen der
#: Kasten fragt „welche Farbe gewinnt?", war ein Teil der Antwort verdeckt.
#:
#: Statt den Kasten zu verkleinern wird das Bild waehrend des Aufhaengers
#: tiefer gelegt und danach weich zurueckgefahren. Der Zuschauer sieht das
#: als beabsichtigte Kamerafahrt: erst das ganze Feld, dann der Fuehrende.
#:
#: Gemessen ueber 30 brauchbare Seeds, Kugelmittelpunkte hinter dem Kasten:
#:     ohne Versatz            461
#:     240 px                   26
#:     320 px                    0     <- diese Einstellung
#: Die tiefste Kugel steht dabei bei y=1387 von 1920 – niemand faellt
#: unten aus dem Bild.
HOOK_KAMERA_VERSATZ = 320.0
HOOK_KAMERA_ZURUECK = 30        # Bilder, in denen der Versatz ausblendet

#: So weit unter der Bildoberkante bleibt die HINTERSTE Kugel mindestens.
#:
#: Gemessen ueber 20 Eliminierungslaeufe – der Wert kostet nichts, solange
#: er nicht zu gross wird:
#:     Rand   Ausscheidungen im Bild   Bilder ohne den Fuehrenden
#:      240            100 %                     0,0 %
#:      420            100 %                     0,0 %      <- diese
#:      520            100 %                     0,9 %
#: Bei 420 ist die hinterste Kugel klar unter der Rangliste (150..496) und
#: der Fuehrende bleibt trotzdem in jedem Bild drin.
KAMERA_RAND_OBEN = 420.0

#: Nachlauf: die Karte bleibt stehen, damit sie lesbar ist. Die Laenge ist
#: an audio.TAIL_SECONDS gekoppelt – sonst laufen Bild und Ton auseinander,
#: und zwar genau um die Differenz der beiden Zahlen.
def outro_frames(fps: int = theme.FPS) -> int:
    return int(round(audio.TAIL_SECONDS * fps))


# ---------------------------------------------------------------------------
# Werkzeug
# ---------------------------------------------------------------------------


def sha256(pfad: Path) -> str:
    h = hashlib.sha256()
    with open(pfad, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ffmpeg_pfad() -> str:
    """ffmpeg finden. Erst das mitgelieferte, dann das System.

    `imageio-ffmpeg` bringt eine eigene ffmpeg.exe mit. Das ist Absicht:
    nichts ausserhalb des Projekts wird veraendert, und die Fassung haengt
    an der Paketversion – damit steht sie im Rundenarchiv wie jede andere
    Version auch.
    """
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    system = shutil.which("ffmpeg")
    if system:
        return system
    raise SystemExit(
        "ffmpeg nicht gefunden.\n"
        "  pip install imageio-ffmpeg      (bringt ffmpeg mit, nichts systemweit)\n"
        "  oder: winget install Gyan.FFmpeg"
    )


def ffmpeg_version(exe: str | None) -> str:
    if exe is None:
        return "nicht vorhanden"
    try:
        aus = subprocess.run([exe, "-version"], capture_output=True, text=True,
                             timeout=30)
        return aus.stdout.splitlines()[0].strip() if aus.stdout else "unbekannt"
    except Exception:
        return "unbekannt"


def versionen(exe: str | None) -> dict:
    """Alles, was das Ergebnis beeinflussen kann.

    Ohne diese Liste ist „gleicher Seed, gleiches Rennen" eine Behauptung:
    pymunk rechnet in Gleitkomma und kann zwischen Fassungen anders loesen,
    Pillow rastert Schrift anders, x264 codiert anders.
    """
    import numpy
    import PIL
    import pymunk
    daten = {
        "python": platform.python_version(),
        "system": f"{platform.system()} {platform.release()}",
        "pymunk": pymunk.version,
        "numpy": numpy.__version__,
        "pillow": PIL.__version__,
        "ffmpeg": ffmpeg_version(exe),
    }
    try:
        import scipy
        daten["scipy"] = scipy.__version__
    except ImportError:
        daten["scipy"] = "fehlt"
    return daten


def codestand() -> dict:
    """git-Commit und ob der Baum sauber war."""
    def git(*args) -> str | None:
        try:
            aus = subprocess.run(["git", *args], cwd=PROJECT_ROOT,
                                 capture_output=True, text=True, timeout=20)
            return aus.stdout.strip() if aus.returncode == 0 else None
        except Exception:
            return None

    commit = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    return {
        "commit": commit or "unbekannt",
        # Ein unsauberer Baum heisst: der Codestand im Archiv ist NICHT der,
        # mit dem gerechnet wurde. Fuer eine Veroeffentlichung ist das ein
        # Mangel, deshalb steht es ausdruecklich drin.
        "sauber": status == "" if status is not None else None,
    }


# ---------------------------------------------------------------------------
# Schritt 1 – Lauf
# ---------------------------------------------------------------------------


def lauf_fingerabdruck(disziplin, seed: int) -> str:
    """Alles, was den Ausgang eines Laufs bestimmt, zu einem Hash.

    DIE Sicherung des Zwischenspeichers. Ohne sie reicht „gleicher Seed,
    gleiche Disziplin" als Treffer – und genau das geht schief, sobald an
    der Strecke oder an der Physik etwas geaendert wird. Die Streckenform
    in descent.py wurde an einem einzigen Tag mehrfach umgebaut; ein Video,
    das danach aus einem alten state.json entstanden waere, haette einen
    Ausgang gezeigt, den der veroeffentlichte Seed nicht mehr ergibt. Damit
    waere das Versprechen des Kanals gebrochen, ohne dass es jemand merkt.

    Deshalb geht hier die tatsaechliche Geometrie ein, nicht ihr Name.
    """
    track = disziplin.build_track(seed)
    # Die SIEGBEDINGUNG gehoert dazu, nicht nur die Geometrie.
    #
    # Bis B6 waren beide dasselbe – die Regel stand fest in `simulate`.
    # Seit B7 bringt jede Disziplin ihre eigene mit. Ohne sie im
    # Fingerabdruck haelt der Zwischenspeicher einen alten `state.json`
    # fuer passend, obwohl eine geaenderte Regel inzwischen ein anderes
    # Rennen ergibt – und `check()` merkt nichts, weil sie auf dem alten,
    # in sich gueltigen Lauf laeuft.
    kennung = getattr(disziplin, "regel_kennung", None)

    # Elastizitaet gehoert in den Fingerabdruck – ein Trampolin ergibt ein
    # anderes Rennen als eine Wand, auch wenn es an derselben Stelle steht.
    #
    # Sie steht aber NUR dort, wo sie vom Hauswert abweicht. Wuerde sie
    # immer mitgeschrieben, aenderte sich der Fingerabdruck jeder bereits
    # ausgestrahlten Folge, und `--pruefen` meldete fuer alle 19 „die
    # Strecke hat sich seither geaendert" – ohne dass sich ein einziger
    # Wert geaendert haette. Dieselbe Falle wie beim Wechsel von `0` auf
    # `0.0` in der Wandkoordinate, nur teurer.
    def masse(werte, elast):
        return list(werte) if elast is None else list(werte) + [elast]

    roh = json.dumps({
        "disziplin": disziplin.NAME,
        "regel": kennung(seed) if kennung else disziplin.NAME,
        "seed": seed,
        "segments": [masse([s.x1, s.y1, s.x2, s.y2, s.radius], s.elastizitaet)
                     for s in track.segments],
        "pegs": [masse([p.x, p.y, p.radius], p.elastizitaet)
                 for p in track.pegs],
        "starts": [list(s) for s in track.starts],
        "finish_y": track.finish_y,
        "physik": [physics.GRAVITY, physics.SUBSTEPS, physics.MARBLE_MASS,
                   physics.MARBLE_ELASTICITY, physics.MARBLE_FRICTION,
                   physics.WALL_ELASTICITY, physics.WALL_FRICTION,
                   physics.PEG_ELASTICITY, physics.PEG_FRICTION,
                   physics.MIN_IMPULSE],
        "kugel": theme.MARBLE_RADIUS,
        "fps": theme.FPS,
    }, sort_keys=True).encode("utf-8")
    return hashlib.sha256(roh).hexdigest()


#: Oeffentliche Adresse des Rundenarchivs. Leer, solange es kein Remote
#: gibt – die Beschreibung laesst den Abschnitt dann weg, statt auf eine
#: Adresse zu verweisen, die niemand aufrufen kann.
#:
#: Das Archiv ist ein gespiegelter Ausschnitt dieses Repos; der Abgleich
#: selbst liegt im Entwicklungsrepo. Wer hier etwas aendert, muss abgleichen,
#: BEVOR die Folge hochgeht – sonst laeuft der Pruefbefehl unter dem Video
#: ins Leere.
ARCHIV_URL = "https://github.com/valon-91/gravity-cup-archiv"

#: Anzeigenamen der Disziplinen fuer Titel und Beschreibung.
DISZIPLIN_TITEL = {
    "descent": "Fall Race",
    "elimination": "Elimination",
    "scatter": "Scatter",
}

#: YouTube weist Beschreibungen mit spitzen Klammern zurueck – "Spitze
#: Klammern sind nicht zulaessig", und das Formular laesst sich dann nicht
#: mehr absenden. Gefunden beim ersten Testupload am 28.07.2026: die
#: Rangfolge stand als "VIOLET > GOLD > ..." da und blockierte den Upload.
KLAMMER_ERSATZ = {"<": "‹", ">": "›"}

#: Trennt die Plaetze in der Rangfolge. Frueher " > ", siehe oben.
RANG_PFEIL = " → "


def ohne_spitze_klammern(text: str) -> str:
    """Macht die Beschreibung uploadfaehig, egal was hineingeflossen ist.

    Den Pfeil an einer Stelle zu setzen reicht nicht: in die Beschreibung
    fliessen Teilnehmernamen und Disziplinbezeichnungen – Werte, die spaeter
    jemand aendert, ohne an YouTube zu denken. Der Ersatz greift deshalb am
    Ende, wo kein Weg daran vorbeifuehrt.
    """
    for zeichen, ersatz in KLAMMER_ERSATZ.items():
        text = text.replace(zeichen, ersatz)
    return text


def beschreibung(manifest: dict, tabelle=None, runden=None) -> str:
    """Die fertige Videobeschreibung, aus dem Manifest erzeugt.

    Warum aus dem Manifest und nicht von Hand: die Beschreibung ist der Ort,
    an dem der Kanal sein Versprechen einloest. Steht dort ein anderer Seed
    als im Archiv, ist das Versprechen wertlos – und von Hand abgetippte
    Zahlen weichen irgendwann ab. Hier koennen sie es nicht.
    """
    e = manifest["ergebnis"]
    disziplin = manifest["disziplin"]
    titel = DISZIPLIN_TITEL.get(disziplin, disziplin.title())
    runde = manifest.get("runde")

    zeilen = []
    if runde:
        m = standings.RUNDE_MUSTER.match(runde)
        if m:
            zeilen.append(f"GRAVITY CUP · Season {int(m.group(1))}, "
                          f"Round {int(m.group(2))} · {titel}")
        else:
            zeilen.append(f"GRAVITY CUP · {runde} · {titel}")
    else:
        zeilen.append(f"GRAVITY CUP · {titel}")

    zeilen += [
        "",
        f"Winner: {e['sieger']}",
        RANG_PFEIL.join(e["reihenfolge"]),
        "",
        "The outcome is simulated, not written.",
        "",
        "Check it yourself:",
        f"  seed        {manifest['seed']}",
        f"  discipline  {disziplin}",
        f"  code        {manifest['codestand']['commit'][:12]}",
        f"  python      {manifest['versionen']['python']}"
        f"  ·  pymunk {manifest['versionen']['pymunk']}",
    ]
    if ARCHIV_URL:
        zeilen += [
            f"  archive     {ARCHIV_URL}",
            f"  verify      python -m gravitycup.build --pruefen "
            f"runs/{runde or disziplin}.json",
        ]
    else:
        zeilen.append("  (run archive goes public with the first upload)")

    if tabelle and runden:
        zeilen += ["", f"Standings after {len(runden)} round"
                       f"{'s' if len(runden) != 1 else ''}:"]
        for platz, eintrag in enumerate(tabelle, start=1):
            zeilen.append(f"  {platz}. {eintrag.name:<8} {eintrag.punkte:>3}")
        zeilen.append("  " + " · ".join(str(p) for p in standings.PUNKTE)
                      + "  points per place")

    zeilen += [
        "",
        "No music, no stock sound: every click is computed from the "
        "collision it belongs to.",
        "",
        "#marblerace #physics #simulation #shorts",
    ]
    return ohne_spitze_klammern("\n".join(zeilen) + "\n")


def ausgestrahlt(runde: str, youtube_id: str, archiv: Path = ARCHIV) -> int:
    """Eine Runde als gesendet vermerken.

    Das ist mehr als Buchhaltung. Das oeffentliche Archiv spiegelt NUR
    Runden, die gelaufen sind – ohne diesen Vermerk stuende der Sieger einer
    noch nicht gesendeten Folge oeffentlich lesbar da, bevor sie laeuft. Der
    Kanal wuerde seinen eigenen Ausgang verraten, und zwar an genau der
    Stelle, die sein Versprechen einloesen soll.

    Der Vermerk ist zugleich die Zuordnung Video → Seed → Disziplin, ohne
    die spaeter keine Auswertung moeglich ist.
    """
    pfad = archiv / f"{runde}.json"
    if not pfad.exists():
        print(f"Kein Manifest {pfad}")
        return 2
    m = json.loads(pfad.read_text(encoding="utf-8"))
    vorher = m.get("youtube_id")
    if vorher and vorher != youtube_id:
        print(f"{runde} ist bereits als {vorher} vermerkt.")
        print("Ein zweiter Vermerk waere ein Hinweis darauf, dass dieselbe")
        print("Runde zweimal hochgeladen wurde. Erst klaeren, dann von Hand.")
        return 1
    m["youtube_id"] = youtube_id
    pfad.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    print(f"{runde}: youtube_id = {youtube_id}")
    print("Jetzt committen und abgleichen – erst danach ist der Pruefbefehl")
    print("unter dem Video einloesbar.")
    return 0


def stand_bis(runde: str | None, archiv: Path = ARCHIV):
    """Tabelle und Runden, wie sie zum Zeitpunkt DIESER Runde galten.

    NUR bis zu dieser Runde: das Archiv enthaelt beim Neubau einer alten
    Folge auch die spaeteren – die Beschreibung von Runde 1 zeigte sonst den
    Stand nach Runde 3, also ein Ergebnis, das damals noch nicht feststand.

    Bricht LAUT ab, wenn das Archiv nicht auswertbar ist. Bis zum
    03.08.2026 wurde der ArchivFehler hier verschluckt und (None, None)
    geliefert – jede Beschreibung waere still ohne Punktestand geschrieben
    worden, waehrend alle Tests gruen waren.
    """
    treffer = standings.RUNDE_MUSTER.match(runde) if runde else None
    if not treffer:
        return None, None
    try:
        saison, nummer = int(treffer.group(1)), int(treffer.group(2))
        runden_bisher = [r for r in standings.lade_runden(archiv, saison)
                         if r.nummer <= nummer]
        return standings.berechne(runden_bisher), runden_bisher
    except standings.ArchivFehler as e:
        raise SystemExit(
            f"Archiv nicht auswertbar: {e}\n"
            "Die Beschreibung braucht den Punktestand; ohne diesen Abbruch\n"
            "wuerde sie still ohne Tabelle geschrieben. Erst das Archiv\n"
            "reparieren, dann bauen."
        ) from e


def _rundenmarke(runde: str | None) -> str | None:
    """`S01R07` -> `S01 · R07`. Alles andere bleibt, wie es ist."""
    if not runde:
        return None
    treffer = standings.RUNDE_MUSTER.match(runde)
    if not treffer:
        return runde.upper()
    return f"S{int(treffer.group(1)):02d} · R{int(treffer.group(2)):02d}"


def ton_samples(result: physics.RunResult) -> int:
    """Wie viele Samples die Tonspur zu diesem Lauf haben MUSS.

    Dieselbe Rechnung wie in audio.build(). Sie steht hier ein zweites Mal,
    weil sie hier als PRUEFUNG dient: eine zwischengespeicherte WAV wurde
    frueher allein deshalb genommen, weil die Datei da war.
    """
    return int((len(result.frames) / result.fps + audio.TAIL_SECONDS) * audio.SR)


def wav_passt(pfad: Path, result: physics.RunResult) -> bool:
    """Gehoert diese WAV wirklich zu diesem Lauf?

    Ein abgebrochenes `write_wav` (Strg+C, volle Platte) hinterlaesst eine
    kurze, gueltig aussehende Datei. Frueher hat der naechste Aufbau sie
    kommentarlos genommen; ffmpeg schnitt das Video auf die Tonlaenge zu,
    endete mit Code 0, und das Rundenarchiv beglaubigte ein Video, in dem
    das Rennen fehlte.
    """
    try:
        with wave.open(str(pfad)) as w:
            return (w.getnchannels() == 2
                    and w.getframerate() == audio.SR
                    and w.getnframes() == ton_samples(result))
    except Exception:
        return False


def lauf_holen(disziplin, seed: int, cache: Path | None,
               neu: bool = False) -> tuple[physics.RunResult, Path | None, str]:
    """Lauf rechnen oder aus dem Zwischenspeicher holen."""
    abdruck = lauf_fingerabdruck(disziplin, seed)
    if cache is None:
        return disziplin.run(seed), None, abdruck

    cache.mkdir(parents=True, exist_ok=True)
    pfad = cache / "state.json"
    marke = cache / "fingerabdruck.txt"
    passend = (marke.exists()
               and marke.read_text(encoding="utf-8").strip() == abdruck)

    if pfad.exists() and passend and not neu:
        r = physics.load(pfad)
        if r.seed == seed:
            return r, pfad, abdruck

    r = disziplin.run(seed)
    physics.save(r, pfad)
    marke.write_text(abdruck, encoding="utf-8")
    # Der Ton haengt am Lauf – bei neuer Geometrie ist die alte WAV falsch.
    (cache / "race.wav").unlink(missing_ok=True)
    return r, pfad, abdruck


# ---------------------------------------------------------------------------
# Schritt 3 – Bilder
# ---------------------------------------------------------------------------


def kammerkamera(result: physics.RunResult) -> list[float] | None:
    """Feste Kamera je Kammer – für die Arena.

    Die Verfolgerkamera aus dem Hochformat ist hier schlicht falsch: eine
    Kammer passt GANZ ins Bild, es gibt nichts zu verfolgen. Eine Kamera,
    die dem Führenden hinterherläuft, wackelt stattdessen im Takt der
    Kugeln, und alle anderen wandern durchs Bild, obwohl sich am
    Bildausschnitt nichts ändern müsste.

    Gewechselt wird, wenn die MEHRHEIT der noch aktiven Kugeln in der
    nächsten Kammer ist – nicht wenn die erste dort ankommt. Sonst springt
    das Bild weiter, während der Pulk noch oben steht.

    Liefert `None`, wenn der Lauf keine Kammern hat; dann gilt die normale
    Kamerafahrt.
    """
    kammern = (result.extras or {}).get("kammern")
    if not kammern:
        return None

    # Sichtfenster je Kammer: die Kammer mittig, mit Luft für die Rutsche.
    fenster = []
    for links, oben, rechts, unten, _ in kammern:
        mitte_y = (oben + unten) / 2
        fenster.append(mitte_y - theme.HEIGHT / 2)

    fps = result.fps
    ziele: list[float] = []
    aktuell = 0
    for f, bild in enumerate(result.frames):
        raus = {i for i, t in result.eliminated.items() if t * fps <= f}
        aktiv = [p[1] for i, p in enumerate(bild) if i not in raus]
        if not aktiv:
            aktiv = [p[1] for p in bild]
        # Wie viele stehen unterhalb der aktuellen Kammer?
        while aktuell + 1 < len(kammern):
            grenze = kammern[aktuell][3]          # unten
            drunter = sum(1 for y in aktiv if y > grenze)
            if drunter * 2 <= len(aktiv):
                break
            aktuell += 1
        ziele.append(fenster[aktuell])

    # Weich nachziehen, damit der Wechsel eine Fahrt ist und kein Schnitt.
    top = ziele[0]
    tops = []
    for ziel in ziele:
        top += (ziel - top) * theme.CAMERA_SMOOTHING
        tops.append(top)
    return tops


def kamerafahrt(result: physics.RunResult) -> list[float]:
    """Oberkante je Bild, im Voraus gerechnet.

    Die Kamera ist GESCHICHTET: ihre Lage im Bild f haengt an allen Bildern
    davor. Wer Bilder einzeln oder parallel zeichnet, ohne die Fahrt vorher
    zu rechnen, bekommt eine springende Kamera. Deshalb steht sie hier als
    reine Liste – danach ist jedes Bild unabhaengig zeichenbar.
    """
    # Disziplinen mit Kammern bekommen eine feste Kamera je Kammer.
    fest = kammerkamera(result)
    if fest is not None:
        return fest

    def aktive(f: int) -> list[float]:
        """Die y-Werte aller Kugeln, die im Bild f noch im Rennen sind.

        `is None` ausdruecklich, nicht `or`: ein Ausscheiden im Bild 0
        ergaebe die Zahl 0, und die ist in Python falsy – die Kugel gaelte
        dann als noch im Rennen.
        """
        bild = result.frames[f]
        aktiv = [p[1] for i, p in enumerate(bild)
                 if result.eliminated_frame(i) is None
                 or result.eliminated_frame(i) > f]
        return aktiv or [p[1] for p in bild]

    cam = draw.Camera(limit_bottom=result.finish_y)

    def ziel(f: int) -> float:
        """Wo die Kamera in diesem Bild hinwill.

        Zwei Bedingungen, und die zweite ist der Grund fuer B7:
        1. Der Fuehrende sitzt auf theme.CAMERA_ANCHOR (45 % Bildhoehe).
        2. Der LETZTE bleibt im Bild.
        Von beiden gewinnt der kleinere Wert, also die Kamera weiter oben.

        Ohne (2) hing die Kamera allein am Fuehrenden – und bei der
        Eliminierung scheidet immer der Letzte aus, also der, der am
        weitesten oben steht. Gemessen ueber 20 Laeufe waren nur 64 % der
        Ausscheidungen ueberhaupt im Bild; der Zuschauer sah bloss, wie in
        der Rangliste ein Name durchgestrichen wurde. Genau die
        Entscheidung, um die es in der Disziplin geht, fehlte im Bild.

        Dass beides zugleich geht, ist gemessen und keine Annahme: die
        Feldspreizung liegt im Median bei 255 px und maximal bei 1474 –
        bei 1920 Bildhoehe bleibt der Fuehrende also drin.
        """
        werte = aktive(f)
        nach_fuehrendem = cam._target(max(werte))
        nach_letztem = min(werte) - KAMERA_RAND_OBEN
        return min(nach_fuehrendem, nach_letztem)

    top = ziel(0)
    tops = []
    for f in range(len(result.frames)):
        top += (ziel(f) - top) * theme.CAMERA_SMOOTHING
        tops.append(top)
    cam.top = top

    # Waehrend des Aufhaengers tiefer legen – siehe HOOK_KAMERA_VERSATZ.
    # Kleineres `top` heisst: die Welt rutscht im Bild nach unten.
    #
    # Zurueckgefahren wird mit einer S-Kurve, nicht linear. Linear endet der
    # Versatz mit einem Ruck: die Kamera laeuft mit 10,7 px/Bild Zusatz und
    # steht im naechsten Bild schlagartig still – gemessen ein Sprung von
    # 16 auf 5 px/Bild. Die S-Kurve faengt an beiden Enden auf null ab.
    for f in range(min(len(tops), HOOK_ENDE + HOOK_KAMERA_ZURUECK)):
        if f <= HOOK_ENDE:
            anteil = 1.0
        else:
            t = (f - HOOK_ENDE) / HOOK_KAMERA_ZURUECK      # 0 .. 1
            anteil = 1.0 - t * t * (3.0 - 2.0 * t)         # smoothstep
        tops[f] -= HOOK_KAMERA_VERSATZ * anteil
    return tops


def rangfolge_bei(result: physics.RunResult, f: int) -> list[int]:
    """Rangliste, wie sie im Bild f ehrlich aussieht.

    Wer schon im Ziel ist, steht nach Zielzeit; der Rest nach erreichter
    Tiefe. Eine reine Tiefensortierung waere nach dem Zieleinlauf falsch:
    die Ausrollenden sinken weiter und wuerden sich gegenseitig ueberholen,
    obwohl das Rennen fuer sie vorbei ist.
    """
    grenze = f / result.fps
    bild = result.frames[min(f, len(result.frames) - 1)]

    # Ausgeschiedene stehen hinten, in umgekehrter Reihenfolge ihres
    # Ausscheidens – wer zuletzt rausflog, steht vor dem, der zuerst
    # rausflog. Das ist dieselbe Regel, nach der die Disziplin am Ende
    # wertet. Ohne sie wuerden sie nach ihrer eingefrorenen Tiefe sortiert
    # und die Rangliste widerspraeche der Endkarte.
    raus = sorted((i for i, t in result.eliminated.items() if t <= grenze),
                  key=lambda i: -result.eliminated[i])

    # Wer schon fertig ist, wird nach dem Massstab der DISZIPLIN gereiht.
    #
    # Bis B8 war das immer die Zeit. Die Streuung wertet aber nach dem
    # Landefach: gemessen ueber 39 Laeufe zeigte die Rangliste in 92 % der
    # Faelle eine andere Reihenfolge als die Ergebniskarte, in 44 % einen
    # anderen Fuehrenden. Der Zuschauer sah eine Wertung nach einem
    # Kriterium, das die Disziplin ausdruecklich nicht benutzt – und am
    # Ende sprang die Karte ohne sichtbaren Anlass um.
    punkte = (result.extras or {}).get("punkte") or {}
    da = sorted((i for i in result.finished
                 if result.finish_times[i] <= grenze and i not in raus),
                key=lambda i: (-punkte.get(str(i), 0), result.finish_times[i]))
    rest = sorted((i for i in range(len(bild)) if i not in da and i not in raus),
                  key=lambda i: -bild[i][1])
    return da + rest + raus


def ausgeschieden_bei(result: physics.RunResult, f: int) -> set[int]:
    """Wer im Bild f schon ausgeschieden ist."""
    return {i for i, t in result.eliminated.items() if t * result.fps <= f}


def spur(result: physics.RunResult, f: int, i: int) -> list[tuple[float, float]]:
    """Nachleuchten eines Teilnehmers: seine letzten Positionen."""
    von = max(0, f - theme.TRAIL_LENGTH)
    return [(result.frames[k][i][0], result.frames[k][i][1]) for k in range(von, f)]


def zeichne_bild(result: physics.RunResult, f: int, top: float,
                 hook: tuple[str, str], scale: int, karte_start: int,
                 comps=None, runde: str | None = None,
                 punkte: list[int] | None = None, seed: int | None = None):
    """Ein Einzelbild. Reine Funktion – haengt nur an den Argumenten."""
    comps = comps or theme.competitors()
    rennbild = min(f, len(result.frames) - 1)
    positionen = result.frames[rennbild]

    cam = draw.Camera(top=top, limit_bottom=result.finish_y)
    c = draw.Canvas(scale=scale, camera=cam)
    c.grid()
    for s in result.segments:
        c.track_segment(s.x1, s.y1, s.x2, s.y2)
    for p in result.pegs:
        c.peg(p.x, p.y, p.radius)

    # Sperren, solange sie zu sind.
    #
    # Ohne das steht im Video eine Wand, durch die die Kugeln spaeter
    # rollen – oder, schlimmer, gar keine: dann staut sich das Feld
    # sichtbar an nichts auf, und der Zuschauer haelt es fuer einen Fehler.
    # `tore_auf` kommt aus der Simulation und sagt, wann welche aufging.
    auf = (result.extras or {}).get("tore_auf") or {}
    for nummer, gruppe in enumerate(result.tore):
        zeit = auf.get(str(nummer))
        if zeit is not None and rennbild >= zeit * result.fps:
            continue
        for s in gruppe:
            c.sperre(s.x1, s.y1, s.x2, s.y2, s.radius)

    # Drehkreuze. Ihr Winkel wird gerechnet, nicht gespeichert: ein
    # kinematischer Koerper mit fester Drehzahl steht zur Zeit t bei
    # winkel0 + omega*t, und genau das macht ihn deterministisch.
    for rot in result.rotoren:
        c.rotor(rot, rennbild / result.fps)

    c.finish_line(result.finish_y)

    # Waagrechte Marken der Disziplin. Bei der Eliminierung sind das die
    # Kontrollpunkte; sie erloeschen, sobald sie ausgeloest haben – eine
    # Linie, die schon entschieden hat, lenkt danach nur noch ab. Die
    # Beschriftung kommt aus den Daten, nicht aus build.py: bei der
    # Streuung markiert dieselbe Linie, wo das Fach feststeht, und „GATE 1"
    # waere dort schlicht falsch.
    marke = (result.extras or {}).get("mark_label")
    erledigt = sum(1 for t in result.eliminated.values()
                   if t * result.fps <= rennbild)
    for nummer, mark in enumerate(result.marks, start=1):
        vorbei = nummer <= erledigt
        c.gate_line(mark, alpha=90 if vorbei else 255,
                    label=None if (vorbei or not marke) else f"{marke} {nummer}")

    # Landefaecher der Streuung samt Punktwert.
    faecher = (result.extras or {}).get("faecher") or []
    if faecher:
        hoechster = max(w for _, _, w in faecher)
        for x_von, x_bis, wert in faecher:
            c.slot_value(x_von, x_bis, result.finish_y + 150, wert,
                         hoch=wert == hoechster)

    for i, (x, y, winkel) in enumerate(positionen):
        # Ausgeschiedene blenden ueber eine halbe Sekunde aus und
        # schrumpfen dabei. Einfach stehenlassen sah aus wie ein Fehler,
        # sofort verschwinden wie ein Bildfehler.
        raus_bild = result.eliminated_frame(i)
        alpha, radius = 255, None
        if raus_bild is not None and rennbild >= raus_bild:
            t = min(1.0, (rennbild - raus_bild) / (theme.FPS * 0.5))
            alpha = int(255 * (1.0 - t))
            radius = theme.MARBLE_RADIUS * (1.0 - 0.45 * t)
        c.marble(comps[i], x, y, winkel,
                 spur(result, rennbild, i) if alpha == 255 else None,
                 alpha=alpha, radius=radius)

    # Aufhaenger
    a = draw.fade(f, HOOK_START, HOOK_EIN, HOOK_HALT, HOOK_AUS)
    if a > 0:
        c.hook(hook[0], hook[1], alpha=a)

    # Rangliste: nach dem Aufhaenger auf, mit der Ergebniskarte wieder zu
    if HUD_START <= f:
        ein = min(255, int(255 * (f - HUD_START) / HUD_EIN))
        aus = 255 if f < karte_start else max(
            0, int(255 * (1 - (f - karte_start) / KARTE_EIN)))
        hud = min(ein, aus)
        if hud > 0:
            c.hud_ranking(rangfolge_bei(result, rennbild), comps, alpha=hud,
                          raus=ausgeschieden_bei(result, rennbild))
            # Rundenzaehler oben rechts. Ohne ihn steht die Serialitaet erst
            # auf der Endkarte – und die sieht bei einem Short kaum jemand.
            # Der Pruefbericht nennt genau das: „im HUD gibt es keine
            # Rundennummer und keinen Saisonstand".
            if runde:
                c.text(theme.WIDTH - theme.SAFE_RIGHT, theme.SAFE_TOP + 20,
                       runde, "badge", fill=theme.TEXT_MUTED,
                       anchor="rm", alpha=hud)
            # Der SEED, direkt darunter.
            #
            # Er ist das einzige, was dieser Kanal kann und die etablierte
            # Konkurrenz nicht: wer ihn abliest, kann das Rennen selbst
            # nachrechnen. Bis hierher stand die Ueberpruefbarkeit nur im
            # Code – Rundenarchiv, Codestand, Bibliotheksversionen, drei
            # Haertegrade beim Determinismus – und im Video sagte sie
            # niemandem etwas. Ein Versprechen, das man nicht sieht,
            # unterscheidet sich fuer den Zuschauer nicht von keinem.
            if seed is not None:
                c.text(theme.WIDTH - theme.SAFE_RIGHT, theme.SAFE_TOP + 58,
                       f"SEED {seed}", "badge", fill=theme.GATE,
                       anchor="rm", alpha=hud)

    # Ergebniskarte
    if f >= karte_start:
        a = min(255, int(255 * (f - karte_start) / KARTE_EIN))
        c.result_card(result.order, comps, alpha=a, points=punkte)

    return c.finish()


# ---------------------------------------------------------------------------
# Schritt 5 – Zusammensetzen
# ---------------------------------------------------------------------------


def ffmpeg_befehl(exe: str, wav: Path, ziel: Path, fps: int,
                  crf: int, preset: str) -> list[str]:
    """H.264 yuv420p + AAC 192 kbit/s + faststart, wie die Roadmap fordert.

    Die Farbkennzeichnung steht ausdruecklich drin: ohne sie raet der
    Abspieler, und dasselbe Video sieht auf zwei Geraeten verschieden aus.
    """
    return [
        exe, "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-f", "rawvideo", "-pixel_format", "rgb24",
        "-video_size", f"{theme.WIDTH}x{theme.HEIGHT}",
        "-framerate", str(fps), "-i", "-",
        "-i", str(wav),
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        # `apad` haengt Stille an, falls die Tonspur kuerzer ist als die
        # Bildfolge. Zusammen mit `-shortest` bestimmt damit IMMER das Bild
        # die Laenge. Ohne apad war es umgekehrt: eine zu kurze WAV schnitt
        # das Video ab, ffmpeg endete mit Code 0, und das Rundenarchiv
        # beglaubigte per Pruefsumme ein Video ohne Rennen.
        "-af", "apad",
        "-c:a", "aac", "-b:a", "192k", "-ar", str(audio.SR), "-ac", "2",
        "-movflags", "+faststart",
        "-shortest",
        str(ziel),
    ]


def video_schreiben(exe: str, wav: Path, ziel: Path, fps: int,
                    crf: int, preset: str, gesamt: int,
                    bild_fuer, fortschritt: str | None = None) -> dict:
    """Eine Bildfolge durch ffmpeg schreiben. Liefert die Pruefsummen.

    Herausgeloest aus `bauen()` am 30.07.2026, weil die Show dieselbe
    Kodierung braucht: `bild_fuer(f)` liefert Bild f, woher auch immer –
    aus einem Rennen, aus einer Segmentfolge mehrerer Laeufe, oder aus
    gezeichneten Karten. Die Pipeline war dafuer von Anfang an ausgelegt
    (eine rohe Bildfolge ueber stdin), nur stand die Schleife fest in
    `bauen`.

    HIER LAG DER SCHWERSTE FEHLER VON B5: ein abgeschnittenes Video wurde
    als Erfolg archiviert, weil ffmpeg mit Code 0 endete. Die drei
    Bedingungen am Ende sind die Abhilfe und stehen wortgleich so, wie sie
    dort standen. Wer hier vereinfacht, macht den Fehler noch einmal.
    """
    ziel.parent.mkdir(parents=True, exist_ok=True)
    befehl = ffmpeg_befehl(exe, wav, ziel, fps, crf, preset)
    t0 = time.perf_counter()
    proc = subprocess.Popen(befehl, stdin=subprocess.PIPE,
                            stderr=subprocess.PIPE)

    # Die Fehlerausgabe wird NEBENHER mitgelesen.
    #
    # Sonst haengt der Aufbau: die Rohbilder sind rund 5 GB, die gehen
    # Stueck fuer Stueck in ffmpegs Eingang. Schreibt ffmpeg in derselben
    # Zeit mehr in seine Fehlerausgabe, als die Pipe fasst (unter Windows
    # einige Kilobyte), blockiert ffmpeg beim Schreiben – und wir
    # blockieren beim Schreiben an ffmpeg. Beide warten aufeinander, und
    # zwar fuer immer. `-loglevel error` macht das unwahrscheinlich, aber
    # eine Warnung je Bild reicht schon.
    fehler_teile: list[bytes] = []

    def mitlesen():
        try:
            fehler_teile.append(proc.stderr.read())
        except Exception:
            pass

    leser = threading.Thread(target=mitlesen, daemon=True)
    leser.start()

    # Pruefsumme der ROHEN Bildfolge, waehrend sie durchlaeuft.
    #
    # Das ist die harte Determinismus-Zusage, die der Pruefbericht verlangt:
    # gleiche Versionen, gleicher Seed -> dieselbe Bildfolge, Bit fuer Bit.
    # Die MP4 kann das nicht leisten (x264 codiert je nach Threadzahl
    # anders), die Rohbilder vor dem Codieren schon. Kostet einen
    # hashlib-Aufruf je Bild.
    bilder_hash = hashlib.sha256()
    geschrieben = 0
    abgerissen = False

    try:
        for f in range(gesamt):
            bild = bild_fuer(f)
            if bild.mode != "RGB":
                bild = bild.convert("RGB")
            roh = bild.tobytes()
            bilder_hash.update(roh)
            proc.stdin.write(roh)
            geschrieben += 1
            if fortschritt and f % 60 == 0:
                anteil = f / gesamt
                verstrichen = time.perf_counter() - t0
                rest = verstrichen / anteil - verstrichen if anteil > 0.02 else 0
                print(f"\r{fortschritt}    {f:5d}/{gesamt}  "
                      f"{anteil * 100:3.0f} %   noch ~{rest:5.0f}s",
                      end="", flush=True)
    except BrokenPipeError:
        # ffmpeg ist unterwegs gestorben oder hat frueh dichtgemacht. Der
        # Grund steht in der Fehlerausgabe, die der Nebenlaeufer schon
        # eingesammelt hat. Frueher wurde das hier stillschweigend
        # verschluckt – der Aufbau meldete danach „100 %".
        abgerissen = True
    except BaseException:
        # Alles andere – Zeichenfehler, Strg+C, Speicher voll. ffmpeg wuerde
        # sonst weiterlaufen und aus den bisherigen Bildern eine abspielbare,
        # aber unvollstaendige MP4 fertigstellen.
        proc.kill()
        proc.wait()
        ziel.unlink(missing_ok=True)
        raise
    finally:
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        code = proc.wait()
        leser.join(timeout=10)
        try:
            proc.stderr.close()
        except Exception:
            pass
    fehler = b"".join(t for t in fehler_teile if t).decode("utf-8", "replace")

    # Drei Bedingungen, nicht eine. Ein Rueckgabewert von 0 allein sagt
    # NICHT, dass das Video vollstaendig ist: schliesst ffmpeg den Eingang
    # frueher, endet es zufrieden – mit einem Video, in dem das Rennen
    # fehlt. Eine halbfertige MP4 ist schlimmer als gar keine, weil sie
    # aussieht wie ein Ergebnis und sich hochladen laesst.
    if code != 0 or abgerissen or geschrieben != gesamt:
        ziel.unlink(missing_ok=True)
        gruende = []
        if code != 0:
            # Windows meldet negative Codes als grosse vorzeichenlose Zahl.
            signiert = code - 2 ** 32 if code > 2 ** 31 else code
            gruende.append(f"ffmpeg endete mit Code {signiert}")
        if abgerissen:
            gruende.append("ffmpeg hat den Bildeingang vorzeitig geschlossen")
        if geschrieben != gesamt:
            gruende.append(f"nur {geschrieben} von {gesamt} Bildern angenommen")
        raise SystemExit(
            "ABBRUCH beim Zusammensetzen – keine Datei geschrieben:\n"
            + "\n".join(f"  - {g}" for g in gruende)
            + (f"\n\nffmpeg meldet:\n{fehler}" if fehler.strip() else "")
        )
    return {"bildfolge": bilder_hash.hexdigest(), "bilder": geschrieben,
            "sekunden": time.perf_counter() - t0}


def bauen(disziplin, seed: int, ziel: Path, *, scale: int | None = None,
          runde: str | None = None, cache_nutzen: bool = True,
          neu: bool = False, trotzdem: bool = False,
          crf: int = 19, preset: str = "slow",
          archiv: bool = True, ueberschreiben: bool = False,
          vorschau: bool = False, leise: bool = False) -> dict:
    """Der ganze Ablauf. Liefert das Rundenmanifest."""
    def sag(*args):
        if not leise:
            print(*args, flush=True)

    scale = theme.SUPERSAMPLE if scale is None else scale
    fps = theme.FPS
    exe = ffmpeg_pfad()
    t_start = time.perf_counter()

    # Die Rundenbezeichnung muss B6 lesen koennen. Frueher landete jeder
    # beliebige String im Manifest – und `season.standings` brach danach
    # ueber dem GANZEN Archiv ab, nicht nur ueber der einen Datei. Eine
    # verschriebene Runde haette also die komplette Tabelle stillgelegt.
    if runde is not None and not standings.RUNDE_MUSTER.match(runde):
        raise SystemExit(
            f"--runde {runde!r} passt nicht auf das Muster SxxRyy "
            "(z. B. S01R07).\n"
            "So steht es im Rundenarchiv, und daraus rechnet der\n"
            "Punktestand die Saison. Ohne --runde bauen geht auch – die\n"
            "Folge zaehlt dann nicht zur Wertung.")

    # --- 1. Lauf -----------------------------------------------------------
    cache = (CACHE / f"{disziplin.NAME}-seed{seed}") if cache_nutzen else None
    t0 = time.perf_counter()
    result, state_pfad, abdruck = lauf_holen(disziplin, seed, cache, neu)
    sag(f"[1/5] Lauf      {len(result.frames)} Bilder, {result.duration:.1f}s, "
        f"{len(result.hits)} Aufpraelle   ({time.perf_counter() - t0:.1f}s)")

    # --- 2. Annahmekriterien ----------------------------------------------
    probleme = disziplin.check(result)
    if probleme and not trotzdem:
        raise SystemExit(
            "[2/5] ABBRUCH – dieser Lauf gehoert nicht veroeffentlicht:\n"
            + "\n".join(f"        - {p}" for p in probleme)
            + "\n\n      Anderen Seed waehlen:\n"
            f"        python -m gravitycup.disciplines.{disziplin.NAME} --search 10\n"
            "      Oder bewusst trotzdem bauen: --trotzdem"
        )
    sag("[2/5] Pruefung  " + ("bestanden"
                              if not probleme
                              else f"UEBERGANGEN ({len(probleme)} Mangel)"))

    # --- 3. Ton (vor den Bildern: ffmpeg braucht die Datei beim Start) -----
    t0 = time.perf_counter()
    # Ohne Zwischenspeicher kommt die WAV in ein Wegwerfverzeichnis. Frueher
    # lag sie neben der MP4 und blieb dort liegen – eine 6-MB-Datei, die
    # niemand bestellt hat und die beim naechsten Lauf still ueberschrieben
    # wurde.
    aufraeumen: tempfile.TemporaryDirectory | None = None
    if cache:
        wav = cache / "race.wav"
    else:
        aufraeumen = tempfile.TemporaryDirectory(prefix="gravitycup-")
        wav = Path(aufraeumen.name) / "race.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)

    ton_messung: dict | None = None
    messung_pfad = (cache / "ton.json") if cache else None
    if wav.exists() and cache and not neu and wav_passt(wav, result):
        # Aus dem Zwischenspeicher: die Lautheitsmessung kam beim ersten Lauf
        # heraus und liegt daneben. Ohne sie stuende im Rundenarchiv null –
        # und niemand koennte spaeter belegen, dass die Folge auf -14 LUFS
        # ausgeliefert wurde.
        if messung_pfad and messung_pfad.exists():
            ton_messung = json.loads(messung_pfad.read_text(encoding="utf-8"))
    else:
        stereo, ton_messung = audio.build(result)
        audio.write_wav(wav, stereo)
        if messung_pfad:
            messung_pfad.write_text(json.dumps(ton_messung), encoding="utf-8")
    sag(f"[3/5] Ton       {wav.name}   ({time.perf_counter() - t0:.1f}s)")

    # --- 4. Bilder ---------------------------------------------------------
    tops = kamerafahrt(result)
    nachlauf = outro_frames(fps)
    gesamt = len(result.frames) + nachlauf
    karte_start = max(0, len(result.frames) - int(KARTE_VORLAUF * fps))
    hook = getattr(disziplin, "HOOK", ("", ""))
    # Punkte auf der Endkarte: der Zuschauer soll sehen, was die Runde fuer
    # die Tabelle bedeutet, nicht nur wer gewonnen hat.
    punkte = standings.punkte_je_platz()
    marke = _rundenmarke(runde)

    try:
        messung = video_schreiben(
            exe, wav, ziel, fps, crf, preset, gesamt,
            lambda f: zeichne_bild(result, f, tops[min(f, len(tops) - 1)],
                                   hook, scale, karte_start,
                                   runde=marke, punkte=punkte, seed=seed),
            fortschritt=None if leise else "[4/5] Bilder")
    except BaseException:
        if aufraeumen is not None:
            aufraeumen.cleanup()
        raise
    bilder_hash = messung["bildfolge"]
    sag(f"\r[4/5] Bilder    {gesamt}/{gesamt}  100 %"
        f"            ({messung['sekunden']:.1f}s)")

    # --- 5. Archiv ---------------------------------------------------------
    manifest = {
        "kanal": "GRAVITY CUP",
        "runde": runde,
        "disziplin": disziplin.NAME,
        "seed": seed,
        "erzeugt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "codestand": codestand(),
        "versionen": versionen(exe),
        "gestaltung": {
            "aufloesung": f"{theme.WIDTH}x{theme.HEIGHT}",
            "fps": fps,
            "supersample": scale,
            "schrift": str(theme.font_path()),
            "schrift_im_projekt": theme.font_is_portable(),
        },
        "kodierung": {"crf": crf, "preset": preset,
                      "video": "libx264 yuv420p bt709",
                      "ton": f"aac 192k {audio.SR} Hz stereo"},
        "ergebnis": {
            "reihenfolge": [theme.competitor(i).name for i in result.order],
            "reihenfolge_index": list(result.order),
            "sieger": theme.competitor(result.winner).name,
            "zielzeiten": {theme.competitor(i).name: round(t, 3)
                           for i, t in sorted(result.finish_times.items(),
                                              key=lambda kv: kv[1])},
            "dauer_s": round(result.duration, 2),
            "bilder": len(result.frames),
            "aufpraelle": len(result.hits),
        },
        "annahme": probleme,
        # Der Punkteschluessel gehoert ins Manifest, nicht nur in den Code.
        # Sonst schreibt eine spaetere Aenderung von season.standings.PUNKTE
        # rueckwirkend jede veroeffentlichte Tabelle um, ohne dass es
        # irgendwo auffaellt – und das Archiv soll gerade davor schuetzen.
        "punkteschluessel": standings.punkte_je_platz(),
        "ton_messung": ton_messung,
        # Was diese Pruefsummen zusichern – und was NICHT.
        #
        # state_json und wav sind harte Zusagen: bei den Versionen aus
        # `versionen` kommt dieselbe Datei wieder heraus. Die mp4-Summe ist
        # nur ein Beleg dafuer, WELCHE Datei veroeffentlicht wurde. Sie ist
        # ausdruecklich KEINE Zusage auf Wiederholbarkeit: x264 codiert je
        # nach Threadzahl anders, und die leitet ffmpeg aus der CPU ab.
        # Wer nachrechnet, vergleicht die Reihenfolge, nicht die MP4.
        "pruefsummen": {
            "geometrie": abdruck,
            "lauf": hashlib.sha256(
                json.dumps(physics.to_dict(result), sort_keys=True).encode()
            ).hexdigest(),
            "state_json": sha256(state_pfad) if state_pfad else None,
            "bildfolge": bilder_hash,
            "wav": sha256(wav),
            "mp4": sha256(ziel),
            "hinweis": "lauf, bildfolge und wav sind harte Zusagen: gleiche "
                       "Versionen, gleicher Seed -> Bit fuer Bit dasselbe. "
                       "mp4 ist nur ein Beleg, WELCHE Datei veroeffentlicht "
                       "wurde – x264 haengt an der Threadzahl und ist nicht "
                       "wiederholbar. Nachgerechnet wird die Reihenfolge: "
                       "python -m gravitycup.build --pruefen",
        },
        "video": {
            "bilder": gesamt,
            "dauer_s": round(gesamt / fps, 3),
            "nachlauf_s": audio.TAIL_SECONDS,
        },
        "laufzeit_s": round(time.perf_counter() - t_start, 1),
    }

    if aufraeumen is not None:
        aufraeumen.cleanup()

    if archiv and vorschau:
        # Ein Vorschau-Build darf das Archiv NICHT anfassen. Sonst
        # ueberschreibt ein schneller Probelauf das Manifest der bereits
        # veroeffentlichten Folge – mit anderen Pruefsummen und
        # supersample=1. Das Archiv beschriebe dann eine Datei, die so nie
        # auf YouTube stand.
        #
        # Die Sperre haengt an der ABSICHT (--vorschau), nicht mehr an
        # `scale < theme.SUPERSAMPLE`: theme.py empfiehlt ausdruecklich,
        # SUPERSAMPLE fuer Probelaeufe auf 1 zu stellen – dann waere der
        # Vergleich `1 < 1` falsch und die Sperre still ausgehebelt.
        sag(f"[5/5] Archiv    uebersprungen (Vorschau, supersample={scale})")
    elif archiv:
        ARCHIV.mkdir(parents=True, exist_ok=True)
        name = runde or f"{disziplin.NAME}-seed{seed}"
        pfad = ARCHIV / f"{name}.json"
        if pfad.exists() and not ueberschreiben:
            alt = json.loads(pfad.read_text(encoding="utf-8"))
            raise SystemExit(
                f"Es gibt schon ein Manifest fuer {name}:\n"
                f"  {pfad.relative_to(PROJECT_ROOT)}\n"
                f"  vom {alt.get('erzeugt')}, Ergebnis "
                f"{' > '.join(alt.get('ergebnis', {}).get('reihenfolge', []))}\n\n"
                "Ein Rundenarchiv wird nicht stillschweigend ueberschrieben –\n"
                "sonst ist nicht mehr feststellbar, was veroeffentlicht wurde.\n"
                "Bewusst ersetzen: --ueberschreiben. Andere Runde: --runde."
            )
        pfad.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        sag(f"[5/5] Archiv    {pfad.relative_to(PROJECT_ROOT)}")

    # Die Beschreibung liegt fertig neben dem Video. Sie beim Hochladen von
    # Hand zu tippen hiesse: irgendwann steht dort ein anderer Seed als im
    # Archiv – und das Versprechen des Kanals ist nichts mehr wert.
    tabelle, runden_bisher = stand_bis(runde)
    text = ziel.with_suffix(".txt")
    text.write_text(beschreibung(manifest, tabelle, runden_bisher),
                    encoding="utf-8")

    groesse = ziel.stat().st_size / 1e6
    sag(f"\nfertig: {ziel}  ({groesse:.1f} MB, {gesamt / fps:.1f}s, "
        f"gesamt {manifest['laufzeit_s']:.0f}s)")
    sag(f"Beschreibung fuer den Upload: {text}")
    if manifest["codestand"]["sauber"] is False:
        sag("\nACHTUNG: der Arbeitsbaum war nicht sauber. Der Codestand im\n"
            "Archiv zeigt damit NICHT auf den Code, mit dem gerechnet wurde –\n"
            "diese Runde ist so nicht nachrechenbar. Vor dem Hochladen\n"
            "committen und neu bauen.")
    return manifest


# ---------------------------------------------------------------------------
# Nachrechnen
# ---------------------------------------------------------------------------


def pruefen(manifest_pfad: Path) -> int:
    """Runde aus dem Manifest neu simulieren und vergleichen.

    Das ist der Beweis, den der Kanal schuldig ist: wer den Seed aus der
    Videobeschreibung nimmt, muss auf dieselbe Reihenfolge kommen.
    """
    m = json.loads(Path(manifest_pfad).read_text(encoding="utf-8"))
    disziplin = DISZIPLINEN.get(m["disziplin"])
    if disziplin is None:
        print(f"Unbekannte Disziplin {m['disziplin']!r}")
        return 2

    print(f"Manifest    {manifest_pfad}")
    print(f"Runde       {m.get('runde') or '-'}  "
          f"{m['disziplin']}  seed={m['seed']}")
    # „sauber" kann True, False oder None sein. None heisst „nicht
    # feststellbar" – das darf nicht als „in Ordnung" durchgehen.
    sauber = m["codestand"].get("sauber")
    vermerk = {True: "", False: "  [Arbeitsbaum war UNSAUBER – der Commit "
                              "zeigt nicht auf den gerechneten Code]",
               None: "  [Zustand des Arbeitsbaums unbekannt]"}[sauber]
    print(f"Codestand   {m['codestand']['commit'][:12]}{vermerk}")
    print()

    # Nachrechnen darf NICHT an ffmpeg haengen. Wer pruefen will, ob ein
    # Rennen echt war, braucht die Physik – keinen Video-Encoder.
    try:
        exe = ffmpeg_pfad()
    except SystemExit:
        exe = None
    jetzt = versionen(exe)
    abweichung = [k for k, v in m["versionen"].items()
                  if jetzt.get(k) != v and not (k == "ffmpeg" and exe is None)]
    for k in sorted(m["versionen"]):
        gleich = jetzt.get(k) == m["versionen"][k]
        zeichen = " " if gleich else "!"
        print(f"  {zeichen} {k:<8} {m['versionen'][k]}"
              + ("" if gleich else f"   jetzt: {jetzt.get(k)}"))
    print()

    # Erst rechnen, dann beide Reihenfolgen zeigen – und die nachgerechnete
    # zuerst. Wer zuerst das Archivergebnis liest, liest das Nachgerechnete
    # nur noch bestaetigend.
    r = disziplin.run(m["seed"])
    # Verglichen werden STARTNUMMERN, nicht Anzeigenamen. Ab Saison 2
    # kommen die Namen aus den Kommentaren (theme.rename); ein
    # Namenswechsel wuerde sonst jede aeltere Runde als gefaelscht melden,
    # obwohl sich nur die Beschriftung geaendert hat.
    ist_idx = list(r.order)
    soll_idx = m["ergebnis"].get("reihenfolge_index")
    ist = [theme.competitor(i).name for i in ist_idx]
    soll = m["ergebnis"]["reihenfolge"]
    if soll_idx is None:
        soll_idx = None if set(soll) - {c.name for c in theme.competitors()} \
            else [next(k for k, c in enumerate(theme.competitors())
                       if c.name == n) for n in soll]

    abdruck_jetzt = lauf_fingerabdruck(disziplin, m["seed"])
    abdruck_archiv = (m.get("pruefsummen") or {}).get("geometrie")
    if abdruck_archiv and abdruck_archiv != abdruck_jetzt:
        print("  ! Die Strecke hat sich seither geaendert "
              "(Geometrie-Fingerabdruck weicht ab).")
        print(f"    Archiv {abdruck_archiv[:16]}  jetzt {abdruck_jetzt[:16]}")
        print()

    print(f"  Nachgerechnet {' > '.join(ist)}")
    print(f"  Archiv        {' > '.join(soll)}")
    print()

    stimmt = ist_idx == soll_idx if soll_idx is not None else ist == soll
    if stimmt and ist != soll:
        print("  (Anzeigenamen haben sich geaendert, die Startnummern nicht.)")
    if stimmt:
        print("  ERGEBNIS STIMMT – das Rennen ist nachrechenbar.")
        if abweichung:
            print(f"  (trotz abweichender Versionen: {', '.join(abweichung)})")
        return 0

    print("  ERGEBNIS WEICHT AB.")
    if abweichung:
        print(f"  Abweichende Versionen: {', '.join(abweichung)}")
        print("  Wahrscheinlich Ursache – pymunk rechnet in Gleitkomma und")
        print("  kann zwischen Fassungen anders loesen. Mit den Versionen aus")
        print("  requirements.txt nachrechnen.")
    else:
        print("  Bei identischen Versionen ist das ein echter Fehler.")
    return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Baustein B5 – Disziplin und Seed rein, MP4 raus")
    ap.add_argument("--discipline", "--disziplin", dest="disziplin",
                    default=descent.NAME, choices=sorted(DISZIPLINEN))
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out", default="out.mp4")
    ap.add_argument("--runde", help="Bezeichnung fuers Archiv, z. B. S01R01")
    ap.add_argument("--vorschau", action="store_true",
                    help="ohne Supersampling – rund 20x schneller, nur zum Sichten")
    ap.add_argument("--supersample", type=int,
                    help=f"Standard {theme.SUPERSAMPLE}")
    ap.add_argument("--crf", type=int, default=19)
    ap.add_argument("--preset", default="slow")
    ap.add_argument("--neu", action="store_true",
                    help="Zwischenspeicher ignorieren und neu rechnen")
    ap.add_argument("--ohne-cache", action="store_true")
    ap.add_argument("--ohne-archiv", action="store_true")
    ap.add_argument("--ueberschreiben", action="store_true",
                    help="ein vorhandenes Rundenmanifest bewusst ersetzen")
    ap.add_argument("--trotzdem", action="store_true",
                    help="auch bauen, wenn die Annahmekriterien reissen")
    ap.add_argument("--pruefen", metavar="MANIFEST",
                    help="Runde aus einem Manifest nachrechnen")
    ap.add_argument("--beschreibung", metavar="MANIFEST",
                    help="Videobeschreibung aus einem Manifest ausgeben, "
                         "ohne die Folge neu zu rendern")
    ap.add_argument("--ausgestrahlt", metavar="RUNDE",
                    help="Runde als gesendet vermerken, z. B. S01R01 "
                         "(zusammen mit --youtube-id). Erst danach spiegelt "
                         "das oeffentliche Archiv sie.")
    ap.add_argument("--youtube-id", metavar="ID", dest="youtube_id",
                    help="Video-Kennung, z. B. W3k8-a_PEMI")
    a = ap.parse_args()

    if a.pruefen:
        return pruefen(Path(a.pruefen))

    if a.ausgestrahlt:
        if not a.youtube_id:
            ap.error("--ausgestrahlt braucht --youtube-id")
        return ausgestrahlt(a.ausgestrahlt, a.youtube_id)

    # Ohne diesen Weg erreicht eine Korrektur an der Beschreibung die schon
    # gebauten Folgen nur ueber ein Neurendern – 2,5 min je Folge fuer eine
    # Textzeile. Aufgefallen, als YouTube die spitzen Klammern zurueckwies.
    if a.beschreibung:
        m = json.loads(Path(a.beschreibung).read_text(encoding="utf-8"))
        tabelle, runden_bisher = stand_bis(m.get("runde"))
        print(beschreibung(m, tabelle, runden_bisher), end="")
        return 0

    if a.seed is None:
        ap.error("--seed fehlt. Brauchbare Seeds finden:\n"
                 f"  python -m gravitycup.disciplines.{a.disziplin} --search 10")

    scale = 1 if a.vorschau else a.supersample
    bauen(
        DISZIPLINEN[a.disziplin], a.seed, Path(a.out),
        scale=scale, runde=a.runde,
        cache_nutzen=not a.ohne_cache, neu=a.neu, trotzdem=a.trotzdem,
        crf=a.crf, preset=a.preset, archiv=not a.ohne_archiv,
        ueberschreiben=a.ueberschreiben, vorschau=a.vorschau,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
