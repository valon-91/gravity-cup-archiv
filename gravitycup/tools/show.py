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
from ..disciplines import arena
from . import karten

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TEILNEHMER = 64
NL_ = chr(10)

#: Rundenarchiv der Show. Dasselbe Verzeichnis wie die Saison - die Show
#: ist ein anderes Format, aber dasselbe Versprechen.
ARCHIV = build.ARCHIV


def manifest(seed, teilnehmer, bauart, r, scale, crf, preset, ziel,
             bildfolge, ton, runde):
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
        "disziplin": arena.NAME,
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
        "kennzahlen": arena.kennzahlen(r),
        "annahme": arena.check(r),
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
    """Die Videobeschreibung, aus dem Manifest erzeugt."""
    e = m["ergebnis"]
    zeilen = [
        "GRAVITY CUP SHOW - " + str(m["teilnehmer"]) + " enter, one leaves",
        "",
        "Winner: " + e["sieger"],
        str(e["kammern"]) + " stages, " + str(e["ausgeschieden"])
        + " eliminations, " + format(e["dauer_s"] / 60, ".0f") + " minutes.",
        "",
        "The outcome is simulated, not written.",
        "",
        "Check it yourself:",
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
    bauart = arena.Bauart(**m["bauart"])
    r = arena.run(m["seed"], m["teilnehmer"], bauart)

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
          bauart: arena.Bauart | None = None) -> dict:
    """Seed rein, MP4 raus."""
    theme.set_format("quer")
    theme.set_competitors(theme.feld(teilnehmer))
    scale = theme.SUPERSAMPLE if scale is None else scale
    bauart = bauart or arena.VORGABE
    exe = build.ffmpeg_pfad()
    t_start = time.perf_counter()

    # --- 1. Lauf ---------------------------------------------------------
    t0 = time.perf_counter()
    r = arena.run(seed, teilnehmer, bauart)
    k = arena.kennzahlen(r)
    print(f"[1/4] Lauf      {len(r.frames)} Bilder, {r.duration:.0f}s, "
          f"{len(r.hits)} Aufpraelle, {k['kugel_kugel'] * 100:.0f} % "
          f"Kugel-Kugel   ({time.perf_counter() - t0:.0f}s)")

    probleme = arena.check(r)
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
    # um genau die Vorspannlaenge voraus.
    import numpy as _np
    stille = _np.zeros((int(karten.vorspann_bilder(theme.FPS) / theme.FPS
                            * audio.SR), stereo.shape[1]))
    stereo = _np.concatenate([stille, stereo])
    audio.write_wav(wav, stereo)
    print(f"[3/4] Ton       {wav.name}, {messung['lufs_nachher']:+.1f} LUFS "
          f"  ({time.perf_counter() - t0:.0f}s)")

    # --- 3. Bilder -------------------------------------------------------
    #
    # Vorspann VOR dem Rennen. Ohne ihn sieht ein Zuschauer 64 Kugeln in
    # einem Kasten und weiss nicht, worauf er achten soll - und die Regel
    # ("wer als Letzter durch die Tuer kommt, ist raus") ist der Grund,
    # warum man ueberhaupt hinschaut.
    tops = build.kamerafahrt(r)
    nachlauf = build.outro_frames(theme.FPS)
    vorne = karten.vorspann_bilder(theme.FPS)
    gesamt = vorne + len(r.frames) + nachlauf
    karte_start = max(0, len(r.frames) - int(build.KARTE_VORLAUF * theme.FPS))
    hook = (arena.HOOK[0], arena.HOOK[1].format(n=teilnehmer))
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
                 ergebnis["bildfolge"], messung, runde)
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
    ap.add_argument("--teilnehmer", type=int, default=TEILNEHMER)
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

    bauart = arena.VORGABE
    if a.halt_erste is not None or a.halt_letzte is not None:
        bauart = arena.Bauart(
            halt_erste=a.halt_erste if a.halt_erste is not None
            else arena.VORGABE.halt_erste,
            halt_letzte=a.halt_letzte if a.halt_letzte is not None
            else arena.VORGABE.halt_letzte)

    scale = 1 if a.vorschau else a.supersample
    bauen(a.seed, Path(a.out), a.teilnehmer, scale, a.crf, a.preset, bauart)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
