# B5 – Orchestrierung: Seed rein, MP4 raus

`gravitycup/build.py`
Stand 28.07.2026 · Test: `python -m gravitycup.build --seed 1 --vorschau --out probe.mp4`

## Was der Baustein macht

```bash
python -m gravitycup.build --seed 1 --runde S01R01 --out folge01.mp4
python -m gravitycup.build --seed 1 --vorschau --out probe.mp4   # ~20x schneller
python -m gravitycup.build --pruefen runs/S01R01.json            # nachrechnen
python -m unittest tests.test_b5_build -v                        # 29 Tests
```

Fünf Schritte:

| | Schritt | Ergebnis |
|---|---|---|
| 1 | Lauf rechnen oder aus dem Zwischenspeicher holen | `state.json` |
| 2 | Annahmekriterien prüfen | Abbruch statt Schrott |
| 3 | Ton rechnen oder aus dem Zwischenspeicher holen | `race.wav` |
| 4 | Bilder zeichnen, roh an ffmpeg | `out.mp4` |
| 5 | Rundenarchiv schreiben | `runs/S01R01.json` |

Der Ton kommt **vor** den Bildern, weil ffmpeg die WAV beim Start als zweite
Quelle braucht. Die Bilder gehen als rohes RGB durch eine Pipe – 5,3 GB, die
nie auf der Platte landen.

## Vorgaben der Roadmap

| Vorgabe | Stand |
|---|---|
| `--discipline`, `--seed`, `--out` | ✅ |
| Zwischenschritte cachebar | ✅ `state.json`, `race.wav`, Lautheitsmessung |
| Abbruch statt kaputter Datei | ✅ dreifach abgesichert, siehe unten |
| unter 6 min für 30 s | ✅ **148 s** (Vorschau: 31 s) |
| H.264 yuv420p, AAC 192 kbit/s, `+faststart` | ✅ per Test festgenagelt |

## Der Blocker, den die Prüfung gefunden hat

Ein abgeschnittenes Video wurde als **Erfolg** gemeldet, archiviert und
per Prüfsumme beglaubigt.

`-shortest` bindet die Länge des Videos an die Tonspur. Ist die WAV kürzer
als die Bildfolge, schließt ffmpeg den Bildeingang, sobald der Ton zu Ende
ist – und beendet sich mit **Rückgabewert 0**. Nachgemessen mit genau dem
ffmpeg-Aufruf aus `ffmpeg_befehl()`: 150 Bilder gegen eine 2,5-Sekunden-WAV
ergaben ein MP4 mit 2,5 s, Exit-Code 0, leere Fehlerausgabe.

Der alte Code fing den `BrokenPipeError` stillschweigend ab, prüfte nur
`code != 0` und meldete danach unbedingt „Bilder 900/900 100 %". Ins
Rundenarchiv ging die SHA-256 der halben Datei, `dauer_s` und `bilder`
kamen aus der Simulation. Das Archiv hätte damit ein Video beglaubigt, in
dem das Rennen fehlt – und genau diese Beglaubigung ist das
Verkaufsargument des Kanals.

Auslöser wäre kein Hirngespinst: `audio.write_wav` schreibt direkt in den
Zwischenspeicher. Ein Strg+C mittendrin hinterlässt eine kurze, gültig
aussehende WAV, die der nächste Aufbau kommentarlos genommen hätte.

**Jetzt vierfach abgesichert:**

1. `-af apad` hängt Stille an – die Bildfolge bestimmt immer die Länge.
2. `wav_passt()` prüft Kanalzahl, Abtastrate und **Samplezahl** gegen den
   Lauf, bevor eine zwischengespeicherte WAV benutzt wird.
3. Die geschriebenen Bilder werden gezählt; `geschrieben != gesamt` bricht ab.
4. Ein `BrokenPipeError` wird als Fehler festgehalten statt verschluckt.

Bei Abbruch wird die Zieldatei gelöscht: eine halbfertige MP4 ist schlimmer
als gar keine, weil sie aussieht wie ein Ergebnis und sich hochladen lässt.

## Weitere behobene Befunde

### Die Seitenwände fehlten in 60 % aller Bilder

`Canvas.track_segment` fragte „ist ein **Ende** des Stücks sichtbar?". Die
Seitenwände laufen von y=0 bis y=5680 durch die ganze Strecke – mitten im
Rennen liegen beide Enden weit außerhalb, also wurden sie nicht gezeichnet.
Sichtbar war das an den Einzelbildern: die Strecke wirkte wie frei
schwebende Rampen statt wie ein Schacht. Neu ist `Camera.overlaps()`, das
auf **Überschneidung** mit dem Sichtband prüft.

### Der Aufhänger verdeckte bis zu drei von fünf Kugeln

Die Kamera hängt am Führenden (45 % Bildhöhe). Zieht sich das Feld
auseinander, wandern die Hinteren nach oben – in den Aufhängerkasten hinein.
Gemessen an seed 2: von Bild 30 bis 78 standen bis zu drei Kugeln dahinter.
Genau in den Sekunden, in denen der Kasten fragt „welche Farbe gewinnt?".

Statt den Kasten zu verkleinern legt `kamerafahrt()` das Bild während des
Aufhängers um 320 px tiefer und fährt danach mit einer S-Kurve zurück
(linear ergab einen sichtbaren Ruck von 16 auf 5 px/Bild). Über 30 Seeds:

| | Kugelmittelpunkte hinter dem Kasten |
|---|---|
| ohne Versatz | 461 |
| 240 px | 26 |
| **320 px** | **0** |

### Der Zwischenspeicher war blind für die Streckengeometrie

Er wurde allein über Seed und Disziplinnamen identifiziert. Die Streckenform
in `descent.py` wurde an einem einzigen Tag mehrfach umgebaut – ein danach
gebautes Video wäre aus einem **alten** `state.json` entstanden und hätte
einen Ausgang gezeigt, den der veröffentlichte Seed nicht mehr ergibt.
`--pruefen` hätte die Folge als gefälscht gemeldet.

`lauf_fingerabdruck()` hasht jetzt die tatsächliche Geometrie (alle
Segmente, Stifte, Startplätze, Ziellinie) plus die Physikkonstanten,
Kugelgröße und Bildrate. Ändert sich irgendetwas davon, wird neu gerechnet
und die alte WAV gelöscht.

### Kleineres

* Die Ergebniskarte ließ die Ziellinie durchscheinen – als gestrichelte
  Linie quer durch die letzte Tabellenzeile. Tabellendeckung 178 → 236.
* `ffmpeg`s Fehlerausgabe wird nebenher mitgelesen. Vorher erst nach dem
  letzten Bild: füllt ffmpeg die Pipe (unter Windows wenige Kilobyte),
  warten beide Seiten aufeinander – dauerhaft.
* Jede andere Ausnahme beim Zeichnen killt ffmpeg und löscht die Datei.
  Vorher lief ffmpeg weiter und stellte aus den bisherigen Bildern eine
  abspielbare, unvollständige MP4 fertig.
* `--pruefen` braucht kein ffmpeg mehr. Wer prüfen will, ob ein Rennen echt
  war, braucht die Physik – keinen Videoencoder.
* `--pruefen` vergleicht **Startnummern**, nicht Anzeigenamen. Ab Saison 2
  kommen die Namen aus den Kommentaren; ein Namenswechsel hätte sonst jede
  ältere Runde als gefälscht gemeldet.
* Ein Vorschau-Build (`--vorschau`) schreibt **kein** Archiv, und ein
  vorhandenes Manifest wird nicht ohne `--ueberschreiben` ersetzt.
* Ohne Zwischenspeicher landet die WAV in einem Wegwerfverzeichnis statt
  neben der MP4.

## Das Rundenarchiv

`runs/S01R01.json`, im Git – im Gegensatz zu `data/` und den MP4s. Aus
diesen Dateien lässt sich jede veröffentlichte Runde nachrechnen, ohne dass
jemand Gigabyte an Videos aufheben muss.

Der Determinismus-Vertrag hat drei Härtegrade, wie der Prüfbericht ihn
verlangt:

| Prüfsumme | Zusage |
|---|---|
| `lauf`, `state_json` | **hart** – gleiche Versionen, gleicher Seed ⇒ Bit für Bit dasselbe |
| `bildfolge` | **hart** – SHA-256 der rohen RGB-Bilder vor dem Codieren |
| `wav` | **hart** |
| `mp4` | **weich** – nur ein Beleg, *welche* Datei veröffentlicht wurde |

Die MP4 ist ausdrücklich **nicht** wiederholbar: x264 codiert je nach
Threadzahl anders, und die leitet ffmpeg aus der CPU ab. Wer nachrechnet,
vergleicht die Reihenfolge.

`bildfolge` kostet einen `hashlib`-Aufruf je Bild und ersetzt die vom
Prüfbericht geforderte PNG-Sequenz: gehasht wird dasselbe Pixelmaterial,
nur bevor es in die Pipe geht statt nach dem Umweg über die Platte.

## Die Seed-Wahl darf den Ausgang nicht verraten

`descent.py --search` zeigt seit dieser Sitzung **nur noch** Dauer,
Zieleinläufe, Aufprallzahl und Abstand an der Spitze – nicht Sieger und
Reihenfolge. Wer sich aus einer Liste den Seed aussucht, bei dem die
Lieblingsfarbe gewinnt, hat den Ausgang geschrieben statt simuliert. Für
den Blick danach gibt es `--verraten`.

Die Abbruchmeldung in `build.py` verweist auf genau diesen Aufruf.

Für die erste Folge fiel die Wahl auf **seed 1** – den ersten Seed
überhaupt, der die Annahmekriterien erfüllt. Eine Regel, die jeder
nachvollziehen kann und die nicht am Ergebnis hängt.

## Entschieden: die Rangliste bleibt oben

Gemessen über 10 brauchbare Läufe steht in **29,8 %** der Bilder mindestens
eine Kugelmitte hinter dem Ranglistenkasten (9,2 % aller Kugel-Bilder).
Verschieben auf die Höhe direkt über der Shorts-Leiste (Oberkante 1154)
drückt das auf 11,8 % bzw. 7,4 %.

**Valon hat entschieden: bleibt oben** (28.07.2026). Begründung: der Kasten
ist zu 48 % durchsichtig, die Kugeln bleiben erkennbar – es ist kein Fehler,
nur nicht optimal. Ein Umzug widerspräche `theme.OVERLAY_FLOOR = 520` („ab
hier abwärts keine dauerhafte Einblendung") und legte das Aussehen jedes
künftigen Videos neu fest.

`Canvas.hud_ranking()` nimmt einen `top`-Parameter entgegen – falls die
Entscheidung später kippt, ist es eine Zeile in `build.zeichne_bild()`.

## Offen

* **Der Arbeitsbaum muss beim Bauen sauber sein.** Sonst zeigt der Commit
  im Archiv nicht auf den gerechneten Code, und die Runde ist nicht
  nachrechenbar. `build.py` warnt am Ende deutlich, verhindert es aber
  nicht.
* Mehrere Kerne: gerendert wird auf einem. Bei 148 s von 360 s Budget
  besteht kein Anlass – die Bilder sind nach `kamerafahrt()` aber bewusst
  unabhängig voneinander, eine Parallelisierung wäre also ohne Umbau
  möglich.
