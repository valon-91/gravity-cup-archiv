#!/usr/bin/env python3
"""
show.py – eine Folge der Langform-Show bauen.

Die Show ist eine EIGENE Sendung, nicht Teil der Saison (entschieden am
30.07.2026): Vollbild statt Hochformat, 64 Teilnehmer statt fünf, eigene
Wertung. Deshalb ein eigenes Werkzeug statt eines Schalters an `build.py` –
dort hängt jede Zeile an der Saisontabelle, am Punkteschlüssel und am
Rundenarchiv, und nichts davon gilt hier.

Gemeinsam ist beiden alles, worauf es ankommt: dieselbe Simulation,
dieselbe Tonerzeugung, dieselbe Kodierung über `build.video_schreiben`.

  python -m gravitycup.tools.show --seed 2 --out data/show-s01.mp4
  python -m gravitycup.tools.show --seed 2 --vorschau     # klein und schnell
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .. import build
from ..core import audio, physics, theme
from ..disciplines import arena, gauntlet
from . import karten

#: Die Disziplinen der Langform, mit ihrer Feldgroesse. `arena` traegt
#: 100 (gemessen 31.07.), `gauntlet` 112 – die Kennungen in `theme`
#: tragen bis 112, und mehr Teilnehmer sind der Laengen-Hebel ohne
#: Totzeit.
DISZIPLINEN = {"arena": (arena, 100), "gauntlet": (gauntlet, 112)}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

#: Feldgroesse der Show.
#:
#: Von 64 auf 100 am 31.07.2026, und die Begruendung ist gemessen, nicht
#: geschmacklich. Nachdem die Kammern durchlaessig waren, dauerte ein Lauf
#: mit 64 nur noch 4:28 - unter der Mindestlaenge. Zwei Hebel standen zur
#: Wahl, und sie sind nicht gleichwertig:
#:
#:     N     Ruhemoment   Dauer    Stillstand   Kugel-Kugel
#:     64        1,6 s     4:28        1,3 s        75 %
#:     64        4,0 s     7:00        3,6 s        75 %
#:     64        7,0 s    10:07        6,4 s        75 %
#:    100        1,6 s     8:17        1,3 s        81 %
#:    100        4,0 s    12:18        3,9 s        81 %
#:
#: Mehr Teilnehmer kostet KEINE Totzeit - der laengste Stillstand bleibt
#: bei 1,3 s - und das Gedraenge steigt von 75 auf 81 %. Ein laengerer
#: Ruhemoment kauft dieselbe Laenge mit Warten. Deshalb 100 und der
#: Ruhemoment unveraendert.
#:
#: Die Kennungen in `theme` tragen bis 112.
TEILNEHMER = 100
NL_ = chr(10)

#: Rundenarchiv der Show. Dasselbe Verzeichnis wie die Saison - die Show
#: ist ein anderes Format, aber dasselbe Versprechen.
ARCHIV = build.ARCHIV

#: Vorspann vor dem Rennen. AUS seit 12.08.2026, und die Begruendung ist
#: gemessen, nicht geschmacklich.
#:
#: SHOW-02 stellte drei Tafeln von zusammen 8,6 s vor das erste Bild des
#: Rennens. Nach acht Tagen sagt die Auswertung:
#:
#:     Video                        Vorspann   Ø gesehen   Bindung   Aufrufe
#:     SHOW-02            (5:30)       8,6 s        0:05      1,6 %     8755
#:     S01R08 Elimination (0:27)      keiner        0:19     70,7 %     1182
#:     S01R09 Scatter     (0:31)      keiner        0:16     52,3 %      471
#:     S01R02 Elimination (0:26)      keiner        0:13     50,6 %     3429
#:
#: Der durchschnittliche Zuschauer stieg 3,6 s aus, BEVOR das Rennen
#: begann: 98,4 % haben nie eine Kugel rollen sehen. Dieselben Kugeln,
#: dieselbe Physik, derselbe Ton halten in den Kurzfolgen bis 70,7 % -
#: und die zeigen ab Bild 1 das Feld, mit dem Aufhaenger DARUEBER
#: (`build.HOOK_START` = Bild 6, `HOOK_ENDE` = Bild 62).
#:
#: Die alte Begruendung steht im Modulkopf von `karten.py`: ohne Vorspann
#: wisse der Zuschauer nicht, worauf er achten soll. Sie war plausibel und
#: ist widerlegt - der Aufhaenger sagt dasselbe in zwei Sekunden ueber dem
#: laufenden Rennen, Seed und Kammerzahl stehen im HUD, und das
#: Nachrechnen steht in der Beschreibung.
#:
#: Der Schalter bleibt stehen, damit der Vergleich wiederholbar ist.
VORSPANN = False


def manifest(seed, teilnehmer, bauart, r, scale, crf, preset, ziel,
             bildfolge, ton, runde, disziplin=arena):
    """Alles, was noetig ist, um diese Folge nachzurechnen.

    Ohne diese Datei ist "the outcome is simulated, not written" eine
    Behauptung. Sie ist der einzige Unterschied zwischen dieser Show und
    den etablierten Murmelkanaelen - und faellt genau dann weg, wenn man
    sie beim ersten Mal weglaesst.

    Die BAUART gehoert hinein, nicht nur der Seed: dieselbe Zahl ergibt in
    einer anderen Kammergeometrie ein anderes Rennen.
    """
    exe = build.ffmpeg_pfad()
    comps = theme.competitors()
    return {
        "kanal": "GRAVITY CUP",
        "format": "show",
        "runde": runde,
        "seed": seed,
        "teilnehmer": teilnehmer,
        "disziplin": disziplin.NAME,
        "erzeugt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "codestand": build.codestand(),
        "versionen": build.versionen(exe),
        "bauart": asdict(bauart),
        "gestaltung": {
            "ausgabeformat": theme.FORMAT.name,
            "aufloesung": str(theme.WIDTH) + "x" + str(theme.HEIGHT),
            "fps": theme.FPS,
            "supersample": scale,
            "schrift": str(theme.font_path()),
            "schrift_im_projekt": theme.font_is_portable(),
        },
        "kodierung": {"crf": crf, "preset": preset,
                      "video": "libx264 yuv420p bt709",
                      "ton": "aac 192k " + str(audio.SR) + " Hz stereo"},
        "ergebnis": {
            "sieger": comps[r.winner].name,
            "reihenfolge_index": list(r.order),
            "reihenfolge": [comps[i].name for i in r.order],
            "kammern": len(r.marks),
            "ausgeschieden": len(r.eliminated),
            "dauer_s": round(r.duration, 2),
            "bilder": len(r.frames),
            "aufpraelle": len(r.hits),
        },
        "kennzahlen": disziplin.kennzahlen(r),
        "annahme": disziplin.check(r),
        "ton_messung": ton,
        "pruefsummen": {
            "lauf": hashlib.sha256(
                json.dumps(physics.to_dict(r), sort_keys=True).encode()
            ).hexdigest(),
            "bildfolge": bildfolge,
            "mp4": build.sha256(ziel),
            "hinweis": "lauf und bildfolge sind harte Zusagen: gleiche "
                       "Versionen, gleicher Seed -> Bit fuer Bit dasselbe. "
                       "mp4 ist nur ein Beleg, WELCHE Datei veroeffentlicht "
                       "wurde. Nachgerechnet wird die Reihenfolge.",
        },
    }


def beschreibung(m):
    """Die Videobeschreibung, aus dem Manifest erzeugt.

    Die erste Zeile ist zugleich der YouTube-TITEL (`hochladen --datei`
    liest sie so). Der Sieger steht bewusst GANZ UNTEN als markierter
    Spoiler: bei einem 30-Sekunden-Short ist er in der Beschreibung
    egal, bei fuenf Minuten Langform stand er vorher in Zeile 3 – ueber
    der Falz, sichtbar vor dem ersten Play. Am Kanalversprechen aendert
    das nichts, das Manifest traegt ihn oeffentlich.
    """
    e = m["ergebnis"]
    zeilen = [
        "GRAVITY CUP SHOW · " + str(m["teilnehmer"]) + " Enter, One Leaves",
        "",
        str(m["teilnehmer"]) + " marbles, " + str(e["kammern"])
        + " stages. Every stage is a landscape of giant shapes with one "
        "gated exit - when the gate opens, everybody wants through at "
        "once, and the slowest are OUT. Mass cuts early, duels at the "
        "end, one survivor.",
        "",
        "The outcome is simulated, not written. No script, no cuts, no "
        "retakes - a physics engine decides, and you can check it:",
        "  seed        " + str(m["seed"]),
        "  entrants    " + str(m["teilnehmer"]),
        "  discipline  " + m["disziplin"],
        "  code        " + m["codestand"]["commit"][:12],
        "  python      " + m["versionen"]["python"]
        + "  -  pymunk " + m["versionen"]["pymunk"],
    ]
    if build.ARCHIV_URL:
        zeilen += [
            "  archive     " + build.ARCHIV_URL,
            "  verify      python -m gravitycup.tools.show --pruefen "
            + "runs/" + m["runde"] + ".json",
        ]
    zeilen += [
        "",
        "No music, no stock sound: every impact is computed from the "
        "collision it belongs to.",
        "",
        "Result (spoiler, same as the public manifest): winner "
        + e["sieger"] + ", full order in the archive.",
        "",
        "#marblerace #physics #simulation",
    ]
    return build.ohne_spitze_klammern(NL_.join(zeilen) + NL_)


def pruefen(pfad):
    """Eine Folge aus ihrem Manifest neu rechnen und vergleichen.

    Der Beweis, den die Show schuldig ist: wer den Seed aus der
    Beschreibung nimmt, muss auf denselben Sieger kommen.
    """
    m = json.loads(Path(pfad).read_text(encoding="utf-8"))
    print("Manifest    " + str(pfad))
    print("Show        " + str(m["teilnehmer"]) + " Teilnehmer, seed "
          + str(m["seed"]) + ", " + str(m["ergebnis"]["kammern"]) + " Kammern")
    sauber = m["codestand"].get("sauber")
    vermerk = {True: "", False: "  [Arbeitsbaum war UNSAUBER]",
               None: "  [Zustand unbekannt]"}[sauber]
    print("Codestand   " + m["codestand"]["commit"][:12] + vermerk)
    print()

    try:
        exe = build.ffmpeg_pfad()
    except SystemExit:
        exe = None
    jetzt = build.versionen(exe)
    for k in sorted(m["versionen"]):
        gleich = jetzt.get(k) == m["versionen"][k]
        zeichen = " " if gleich else "!"
        rest = "" if gleich else "   jetzt: " + str(jetzt.get(k))
        print("  " + zeichen + " " + k.ljust(8) + " " + m["versionen"][k] + rest)
    print()

    theme.set_format(m["gestaltung"]["ausgabeformat"])
    theme.set_competitors(theme.feld(m["teilnehmer"]))
    modul, _ = DISZIPLINEN[m.get("disziplin", "arena")]
    bauart = modul.Bauart(**m["bauart"])
    r = modul.run(m["seed"], m["teilnehmer"], bauart)

    ist = list(r.order)
    soll = m["ergebnis"]["reihenfolge_index"]
    namen = [theme.competitors()[i].name for i in ist]
    print("  Nachgerechnet " + namen[0] + "   (dann "
          + " > ".join(namen[1:4]) + " ...)")
    print("  Archiv        " + m["ergebnis"]["sieger"] + "   (dann "
          + " > ".join(m["ergebnis"]["reihenfolge"][1:4]) + " ...)")
    print()
    if ist == soll:
        print("  ERGEBNIS STIMMT - die Folge ist nachrechenbar.")
        return 0
    print("  ERGEBNIS WEICHT AB.")
    erste = next((k for k, (a, b) in enumerate(zip(ist, soll)) if a != b), 0)
    print("  Erste Abweichung auf Platz " + str(erste + 1) + ".")
    return 1


def trailer_bauen(ziel, scale=None, crf=19, preset="slow",
                  teilnehmer=TEILNEHMER):
    """Den Kanaltrailer bauen.

    Er wirbt mit dem VERSPRECHEN, nicht mit einem Ergebnis. Ein Trailer,
    der einen Sieger zeigt, verfaellt mit der Folge; das Versprechen nicht.
    Genau deshalb steht er als Kanaltrailer und nicht als Video im Feed -
    ein normales Video gibt seinen Launch-Moment einmal aus, ein Trailer
    hat keinen und arbeitet ab dem ersten Besucher still weiter.

    Kein Ton aus einem Rennen: es gibt keins. Stattdessen Stille mit einem
    kurzen Anschlag je Tafel, aus derselben Tonerzeugung wie die Folgen.
    """
    import numpy as np

    theme.set_format("quer")
    theme.set_competitors(theme.feld(teilnehmer))
    scale = theme.SUPERSAMPLE if scale is None else scale
    exe = build.ffmpeg_pfad()
    gesamt = karten.trailer_bilder(theme.FPS)

    # Ton: Stille, dazu je Tafel ein Anschlag. Dieselben Bausteine wie im
    # Rennen, damit der Trailer nach demselben Kanal klingt.
    n = int(gesamt / theme.FPS * audio.SR)
    links = np.zeros(n)
    rechts = np.zeros(n)
    t = 0.0
    for k, (_, _, dauer) in enumerate(karten.TRAILER_TAFELN):
        klang = audio.sting(n, int(t * audio.SR), 392.0 * (1.0 + 0.12 * k))
        links += klang * 0.55
        rechts += klang * 0.55
        t += dauer
    stereo, messung = audio.normalize(np.stack([links, rechts], axis=1))
    wav = ziel.with_suffix(".wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    audio.write_wav(wav, stereo)

    ergebnis = build.video_schreiben(
        exe, wav, ziel, theme.FPS, crf, preset, gesamt,
        lambda f: karten.trailer(f, scale, theme.FPS),
        fortschritt="Trailer")
    wav.unlink(missing_ok=True)
    text = (
        "GRAVITY CUP" + NL_ + NL_
        + "Physics simulations. No script, no cuts, no chosen winner." + NL_
        + "Every episode carries its seed - anyone can recompute it and get"
        + " the same result." + NL_ + NL_
        + "Archive and verification: " + (build.ARCHIV_URL or "") + NL_ + NL_
        + "#marblerace #physics #simulation" + NL_)
    ziel.with_suffix(".txt").write_text(build.ohne_spitze_klammern(text),
                                        encoding="utf-8")
    print(NL_ + "fertig: " + str(ziel) + "  ("
          + format(ziel.stat().st_size / 1e6, ".1f") + " MB, "
          + format(gesamt / theme.FPS, ".0f") + " s)")
    return ergebnis


def bauen(seed: int, ziel: Path, teilnehmer: int = TEILNEHMER,
          scale: int | None = None, crf: int = 19, preset: str = "slow",
          bauart=None, disziplin=arena) -> dict:
    """Seed rein, MP4 raus."""
    theme.set_format("quer")
    theme.set_competitors(theme.feld(teilnehmer))
    scale = theme.SUPERSAMPLE if scale is None else scale
    bauart = bauart or disziplin.VORGABE
    exe = build.ffmpeg_pfad()
    t_start = time.perf_counter()

    # --- 1. Lauf ---------------------------------------------------------
    t0 = time.perf_counter()
    r = disziplin.run(seed, teilnehmer, bauart)
    k = disziplin.kennzahlen(r)
    print(f"[1/4] Lauf      {len(r.frames)} Bilder, {r.duration:.0f}s, "
          f"{len(r.hits)} Aufpraelle, {k['kugel_kugel'] * 100:.0f} % "
          f"Kugel-Kugel   ({time.perf_counter() - t0:.0f}s)")

    probleme = disziplin.check(r)
    if probleme:
        print("[2/4] Pruefung  UEBERGANGEN:")
        for pr in probleme:
            print(f"        - {pr}")
    else:
        print("[2/4] Pruefung  bestanden")

    # --- 2. Ton ----------------------------------------------------------
    t0 = time.perf_counter()
    wav = ziel.with_suffix(".wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    stereo, messung = audio.build(r)
    # Stille fuer den Vorspann davorsetzen, sonst laeuft der Ton dem Bild
    # um genau die Vorspannlaenge voraus. Ohne Vorspann faellt sie weg -
    # sonst beginnt die Show mit 8,6 s Stille ueber dem laufenden Rennen.
    if VORSPANN:
        import numpy as _np
        stille = _np.zeros((int(karten.vorspann_bilder(theme.FPS) / theme.FPS
                                * audio.SR), stereo.shape[1]))
        stereo = _np.concatenate([stille, stereo])
    audio.write_wav(wav, stereo)
    print(f"[3/4] Ton       {wav.name}, {messung['lufs_nachher']:+.1f} LUFS "
          f"  ({time.perf_counter() - t0:.0f}s)")

    # --- 3. Bilder -------------------------------------------------------
    #
    # Das Rennen ab Bild 1, der Aufhaenger darueber - wie in den
    # Kurzfolgen. Warum kein Vorspann mehr davorsteht: siehe `VORSPANN`.
    tops = build.kamerafahrt(r)
    nachlauf = build.outro_frames(theme.FPS)
    vorne = karten.vorspann_bilder(theme.FPS) if VORSPANN else 0
    gesamt = vorne + len(r.frames) + nachlauf
    karte_start = max(0, len(r.frames) - int(build.KARTE_VORLAUF * theme.FPS))
    hook = (disziplin.HOOK[0], disziplin.HOOK[1].format(n=teilnehmer))
    comps = theme.competitors()

    def bild_fuer(f):
        if f < vorne:
            return karten.vorspann(f, teilnehmer, seed, scale, theme.FPS)
        g = f - vorne
        return build.zeichne_bild(
            r, g, tops[min(g, len(tops) - 1)], hook, scale, karte_start,
            comps=comps, runde="SHOW · " + str(len(r.marks)) + " STAGES",
            punkte=None, seed=seed)

    ergebnis = build.video_schreiben(
        exe, wav, ziel, theme.FPS, crf, preset, gesamt, bild_fuer,
        fortschritt="[4/4] Bilder")
    print(f"\r[4/4] Bilder    {gesamt}/{gesamt}  100 %"
          f"              ({ergebnis['sekunden']:.0f}s)")

    # --- 4. Archiv -------------------------------------------------------
    runde = ziel.stem.upper()
    m = manifest(seed, teilnehmer, bauart, r, scale, crf, preset, ziel,
                 ergebnis["bildfolge"], messung, runde, disziplin)
    ARCHIV.mkdir(parents=True, exist_ok=True)
    (ARCHIV / (runde + ".json")).write_text(
        json.dumps(m, indent=2, ensure_ascii=False) + NL_, encoding="utf-8")
    ziel.with_suffix(".txt").write_text(beschreibung(m), encoding="utf-8")
    print("        Archiv    runs/" + runde + ".json")
    print("        Text      " + ziel.with_suffix(".txt").name)

    wav.unlink(missing_ok=True)
    groesse = ziel.stat().st_size / 1e6
    gesamtzeit = time.perf_counter() - t_start
    print(f"\nfertig: {ziel}  ({groesse:.0f} MB, "
          f"{gesamt / theme.FPS / 60:.1f} min Laufzeit, "
          f"{gesamtzeit / 60:.0f} min gebaut)")
    print(f"Sieger: {comps[r.winner].name}")
    return {"lauf": k, "video": ergebnis, "sieger": comps[r.winner].name}


def main() -> int:
    ap = argparse.ArgumentParser(description="Eine Folge der Langform-Show")
    ap.add_argument("--trailer", action="store_true",
                    help="statt einer Folge den Kanaltrailer bauen")
    ap.add_argument("--pruefen", metavar="MANIFEST",
                    help="eine Folge aus ihrem Manifest nachrechnen")
    ap.add_argument("--seed", type=int, default=2)
    ap.add_argument("--disziplin", choices=sorted(DISZIPLINEN),
                    default="arena")
    ap.add_argument("--teilnehmer", type=int,
                    help="Vorgabe: Feldgroesse der Disziplin")
    ap.add_argument("--out", default="data/show.mp4")
    ap.add_argument("--vorschau", action="store_true",
                    help="ohne Supersampling – deutlich schneller, nur zum Sichten")
    ap.add_argument("--supersample", type=int)
    ap.add_argument("--crf", type=int, default=19)
    ap.add_argument("--preset", default="slow")
    ap.add_argument("--halt-erste", type=float)
    ap.add_argument("--halt-letzte", type=float)
    a = ap.parse_args()

    if a.pruefen:
        return pruefen(Path(a.pruefen))

    if a.trailer:
        trailer_bauen(Path(a.out), 1 if a.vorschau else a.supersample, a.crf, a.preset)
        return 0

    modul, feld = DISZIPLINEN[a.disziplin]
    teilnehmer = a.teilnehmer if a.teilnehmer is not None else feld
    bauart = modul.VORGABE
    if a.halt_erste is not None or a.halt_letzte is not None:
        bauart = modul.Bauart(
            halt_erste=a.halt_erste if a.halt_erste is not None
            else modul.VORGABE.halt_erste,
            halt_letzte=a.halt_letzte if a.halt_letzte is not None
            else modul.VORGABE.halt_letzte)

    scale = 1 if a.vorschau else a.supersample
    bauen(a.seed, Path(a.out), teilnehmer, scale, a.crf, a.preset, bauart,
          disziplin=modul)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
