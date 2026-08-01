"""Eine Folge zu YouTube hochladen – nicht gelistet.

Nimmt der Handarbeit die drei Schritte ab, die sich zuverlaessig
automatisieren lassen: Datei aussuchen, hochladen, Kennung ins Manifest
schreiben. Das Umstellen auf oeffentlich bleibt bewusst draussen.

Zwei Dinge sind hier fest verdrahtet und nicht als Option gebaut:

* **Sichtbarkeit ist immer `unlisted`.** Ein Fehler im Ablauf, der eine Folge
  zu frueh oeffentlich stellt, verraet den Saisonausgang – und das ist nicht
  rueckholbar. Deshalb kann dieses Werkzeug es gar nicht erst. Der OAuth-
  Bereich ist aus demselben Grund nur `youtube.upload`: dieses Token *darf*
  nichts anderes.
* **`selfDeclaredMadeForKids = False`.** Der einzige Rechtspunkt, der ab dem
  ersten Upload gilt und nicht erst ab der ersten Einnahme. Von Hand
  vergisst man ihn irgendwann.

Ohne `--wirklich` passiert nichts – wie beim Abgleich ist die Trockenuebung
der Normalfall.

    python -m gravitycup.tools.hochladen --naechste
    python -m gravitycup.tools.hochladen --runde S01R02 --wirklich
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..core import theme  # noqa: F401  (haelt die Projektwurzel im Pfad)
from ..season import standings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARCHIV = PROJECT_ROOT / "runs"
DATEN = PROJECT_ROOT / "data"
CONFIG = PROJECT_ROOT / "config"

CLIENT_SECRET = CONFIG / "client_secret.json"
TOKEN = CONFIG / "token.json"

#: Nur Hochladen. Bewusst NICHT `youtube` oder `youtube.force-ssl` – die
#: duerfen auch loeschen und aendern, und dieses Token liegt auf der Platte.
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

#: 24 = Entertainment. Alternative waere 28 (Wissenschaft & Technik), was
#: besser zur Behauptung des Kanals passt, aber ein kleineres Publikum hat.
#: Eine Zeile aendern, wenn die Analytics etwas anderes nahelegen.
KATEGORIE = "24"

#: YouTube-Grenzen. Lieber hier scheitern als im Formular.
TITEL_MAX = 100
BESCHREIBUNG_MAX = 5000


def manifest_pfad(runde: str) -> Path:
    return ARCHIV / f"{runde}.json"


def lade_manifest(runde: str) -> dict:
    p = manifest_pfad(runde)
    if not p.exists():
        raise SystemExit(f"Kein Manifest {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def dateien(runde: str) -> tuple[Path, Path]:
    """(MP4, Beschreibung) – beide muessen existieren."""
    treffer = sorted(DATEN.glob(f"{runde}-*.mp4"))
    if not treffer:
        raise SystemExit(f"Keine MP4 zu {runde} in {DATEN}")
    if len(treffer) > 1:
        raise SystemExit(f"Mehrere MP4 zu {runde}: "
                         + ", ".join(t.name for t in treffer))
    mp4 = treffer[0]
    txt = mp4.with_suffix(".txt")
    if not txt.exists():
        raise SystemExit(
            f"Keine Beschreibung {txt.name}. Erzeugen mit:\n"
            f"  python -m gravitycup.build --beschreibung runs/{runde}.json"
            f" > {txt}")
    return mp4, txt


def titel_und_text(txt: Path) -> tuple[str, str]:
    """Erste Zeile ist der Titel, der ganze Text die Beschreibung.

    Bewusst NICHT hier zusammengebaut: die Beschreibung entsteht aus dem
    Rundenmanifest (`build.beschreibung`) und liegt fertig neben der MP4.
    Wer sie hier noch einmal formatieren wuerde, schuefe eine zweite
    Wahrheit neben dem Archiv.
    """
    text = txt.read_text(encoding="utf-8").rstrip("\n")
    titel = text.splitlines()[0].strip()
    if not titel:
        raise SystemExit(f"{txt.name}: erste Zeile ist leer")
    if len(titel) > TITEL_MAX:
        raise SystemExit(f"Titel ist {len(titel)} Zeichen lang, "
                         f"YouTube nimmt {TITEL_MAX}")
    if len(text) > BESCHREIBUNG_MAX:
        raise SystemExit(f"Beschreibung ist {len(text)} Zeichen lang, "
                         f"YouTube nimmt {BESCHREIBUNG_MAX}")
    for zeichen in "<>":
        if zeichen in text or zeichen in titel:
            raise SystemExit(
                f"Spitze Klammer in Titel oder Beschreibung – YouTube weist "
                f"das Formular zurueck. Sollte `build.ohne_spitze_klammern` "
                f"verhindern; hier stimmt etwas nicht.")
    return titel, text


def schlagworte(text: str) -> list[str]:
    return [w[1:] for w in text.split() if w.startswith("#") and len(w) > 1]


def offene_runden() -> list[str]:
    """Gebaute Runden ohne `youtube_id`, aufsteigend."""
    offen = []
    for p in sorted(ARCHIV.glob("*.json")):
        m = json.loads(p.read_text(encoding="utf-8"))
        if not m.get("youtube_id"):
            offen.append(p.stem)
    return sorted(offen, key=lambda r: (
        standings.RUNDE_MUSTER.match(r).groups()
        if standings.RUNDE_MUSTER.match(r) else (r, "")))


def dienst():
    """Angemeldeter YouTube-Dienst. Fragt beim ersten Mal im Browser nach."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build as api_build

    if not CLIENT_SECRET.exists():
        raise SystemExit(
            f"{CLIENT_SECRET} fehlt.\n"
            f"Google Cloud Console -> Google Auth Platform -> Clients -> "
            f"JSON herunterladen, dann dorthin legen. Die Beschreibung im "
            f"config-Ordner sagt, was noch hineingehoert.")

    daten = None
    if TOKEN.exists():
        daten = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if daten and daten.expired and daten.refresh_token:
        daten.refresh(Request())
    if not daten or not daten.valid:
        print("Keine gueltige Anmeldung – der Browser oeffnet sich gleich.")
        print("Der Warnhinweis 'Google hat diese App nicht ueberprueft' ist")
        print("erwartet: ueber 'Erweitert' weiterklicken.")
        fluss = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRET), SCOPES)
        daten = fluss.run_local_server(port=0)
        TOKEN.write_text(daten.to_json(), encoding="utf-8")
        print(f"Anmeldung gespeichert: {TOKEN.name}")
    return api_build("youtube", "v3", credentials=daten)


def hochladen(runde: str, mp4: Path, titel: str, text: str) -> str:
    """Laedt hoch und gibt die Video-Kennung zurueck."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    y = dienst()
    koerper = {
        "snippet": {
            "title": titel,
            "description": text,
            "tags": schlagworte(text),
            "categoryId": KATEGORIE,
        },
        "status": {
            # NICHT konfigurierbar, siehe Modulkopf.
            "privacyStatus": "unlisted",
            "selfDeclaredMadeForKids": False,
        },
    }
    medien = MediaFileUpload(str(mp4), chunksize=1024 * 1024, resumable=True)
    auftrag = y.videos().insert(part="snippet,status", body=koerper,
                                media_body=medien)

    antwort = None
    letzter = -1
    while antwort is None:
        try:
            stand, antwort = auftrag.next_chunk()
        except HttpError as e:
            raise SystemExit(f"YouTube lehnt ab: {e}")
        if stand:
            prozent = int(stand.progress() * 100)
            if prozent >= letzter + 10:
                print(f"  {prozent:3d} %")
                letzter = prozent
    print("  100 %")
    return antwort["id"]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Eine Folge nicht gelistet zu YouTube hochladen")
    ap.add_argument("--runde", help="z. B. S01R02")
    ap.add_argument("--datei", metavar="MP4",
                    help="eine freie Datei hochladen (Trailer, Vorschau). "
                         "Titel und Text kommen aus der .txt daneben. "
                         "OHNE Rundenarchiv - deshalb nur fuer Videos, die "
                         "kein Rennergebnis zeigen.")
    ap.add_argument("--naechste", action="store_true",
                    help="die naechste Runde ohne youtube_id nehmen")
    ap.add_argument("--wirklich", action="store_true",
                    help="tatsaechlich hochladen (sonst Trockenuebung)")
    a = ap.parse_args()

    gewaehlt = sum(1 for x in (a.naechste, a.runde, a.datei) if x)
    if gewaehlt != 1:
        ap.error("genau eines von --runde, --naechste, --datei angeben")

    if a.datei:
        # Freie Datei: kein Manifest, keine youtube_id, kein Archivvermerk.
        #
        # Das ist bewusst der duennere Weg und NUR fuer Videos gedacht, die
        # kein Rennergebnis zeigen - den Kanaltrailer zum Beispiel. Eine
        # Folge ohne Manifest waere nicht nachrechenbar, und genau das ist
        # das Versprechen des Kanals.
        mp4 = Path(a.datei)
        if not mp4.exists():
            print("Datei nicht gefunden: " + str(mp4))
            return 2
        txt = mp4.with_suffix(".txt")
        if not txt.exists():
            print("Kein Beschreibungstext neben der Datei: " + str(txt))
            return 2
        titel, text = titel_und_text(txt)
        print()
        print("  Datei        " + mp4.name + "  ("
              + format(mp4.stat().st_size / 1e6, ".1f") + " MB)")
        print("  Titel        " + titel)
        print("  Beschreibung " + str(len(text)) + " Zeichen aus " + txt.name)
        print("  Schlagworte  " + (", ".join(schlagworte(text)) or "-"))
        print("  Sichtbarkeit nicht gelistet   (fest, siehe Modulkopf)")
        print("  Fuer Kinder  nein             (fest)")
        print()
        if not a.wirklich:
            print("Trockenuebung. Zum Hochladen: --wirklich")
            return 0
        kennung = hochladen("(frei)", mp4, titel, text)
        print()
        print("hochgeladen: https://youtu.be/" + kennung)
        print()
        print("KEIN Archivvermerk - diese Datei hat kein Rundenmanifest.")
        print("Das Umstellen auf oeffentlich bleibt Handarbeit.")
        return 0

    if a.naechste:
        offen = offene_runden()
        if not offen:
            print("Keine offene Runde – alles hochgeladen.")
            return 0
        runde = offen[0]
        print(f"Naechste offene Runde: {runde}"
              + (f"   (danach: {', '.join(offen[1:4])}"
                 + (" ..." if len(offen) > 4 else "") + ")"
                 if len(offen) > 1 else ""))
    else:
        runde = a.runde

    m = lade_manifest(runde)
    if m.get("youtube_id"):
        print(f"{runde} ist bereits hochgeladen: {m['youtube_id']}")
        print("Ein zweiter Upload erzeugt eine Dublette auf dem Kanal.")
        return 1
    if m["codestand"].get("sauber") is not True:
        print(f"{runde}: der Arbeitsbaum war beim Bauen nicht sauber.")
        print("Diese Runde ist nicht nachrechenbar – erst neu bauen.")
        return 1

    mp4, txt = dateien(runde)
    titel, text = titel_und_text(txt)

    print()
    print(f"  Runde        {runde}  ({m['disziplin']}, seed {m['seed']})")
    print(f"  Datei        {mp4.name}  "
          f"({mp4.stat().st_size / 1e6:.1f} MB)")
    print(f"  Titel        {titel}")
    print(f"  Beschreibung {len(text)} Zeichen aus {txt.name}")
    print(f"  Schlagworte  {', '.join(schlagworte(text)) or '–'}")
    print(f"  Kategorie    {KATEGORIE}")
    print(f"  Sichtbarkeit nicht gelistet   (fest, siehe Modulkopf)")
    print(f"  Fuer Kinder  nein             (fest)")
    print()

    if not a.wirklich:
        print("Trockenuebung. Zum Hochladen: --wirklich")
        return 0

    kennung = hochladen(runde, mp4, titel, text)
    print(f"\nhochgeladen: https://youtube.com/shorts/{kennung}")

    m["youtube_id"] = kennung
    manifest_pfad(runde).write_text(
        json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{runde}: youtube_id = {kennung}")

    print()
    print("Jetzt noch von Hand – in dieser Reihenfolge:")
    print(f"  git add runs/{runde}.json && git commit -m \"{runde} ausgestrahlt\"")
    print("  python -m gravitycup.tools.veroeffentlichen "
          "--ziel ../gravity-cup-archiv --wirklich")
    print("  git -C ../gravity-cup-archiv push")
    print("  dann im Studio auf OEFFENTLICH stellen")
    print()
    print("Das Umstellen bleibt Handarbeit: erst muss das Manifest drueben")
    print("liegen, sonst laeuft der Pruefbefehl unter dem Video ins Leere.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
