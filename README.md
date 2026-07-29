# GRAVITY CUP — Rundenarchiv

Die Physik hinter dem YouTube-Kanal [@thegravitycup](https://youtube.com/@thegravitycup),
und das Archiv, aus dem sich **jede veröffentlichte Folge nachrechnen lässt**.

> **Der Ausgang wird simuliert, nicht geschrieben.**

Unter jedem Video steht der Seed. Mit diesem Repo kannst du ihn einlösen: Der
Lauf wird neu gerechnet, und die Reihenfolge muss dieselbe sein.

## Eine Folge nachrechnen

```bash
pip install -r requirements.txt
python -m gravitycup.build --pruefen runs/S01R01.json
```

Das lädt Seed, Disziplin und das archivierte Ergebnis aus dem Manifest,
simuliert den Lauf neu und vergleicht. Die Ausgabe endet mit
`ERGEBNIS STIMMT` oder mit einer Gegenüberstellung beider Reihenfolgen.

Zum Nachrechnen wird **kein ffmpeg** gebraucht — wer prüfen will, ob ein
Rennen echt war, braucht die Physik, keinen Video-Encoder.

### Wenn das Ergebnis abweicht

Zuerst die Bibliotheksversionen vergleichen — `--pruefen` stellt sie
gegenüber und markiert Abweichungen mit `!`. `pymunk` rechnet in Gleitkomma
und kann zwischen Fassungen anders lösen. Mit den in `requirements.txt`
festgenagelten Versionen ist eine Abweichung ein echter Fehler; dann bitte
ein Issue.

## Was der Codestand in der Videobeschreibung bedeutet

Jede Videobeschreibung nennt einen Codestand, etwa `code 689069d41cc2`. Dieses
Repo ist ein **gespiegelter Ausschnitt** der internen Entwicklung — die
Hashes stammen von dort und existieren hier nicht als Commits. Sie sind
trotzdem auffindbar: jeder Abgleich vermerkt seine Quelle in der
Commit-Nachricht.

```bash
git log --grep=689069d41cc2
```

Nicht gespiegelt werden Kanalstrategie, Prüfberichte und Planung. Alles, was
zum Nachrechnen gebraucht wird, ist hier.

## Was hier liegt

| | |
|---|---|
| `gravitycup/core/` | Gestaltung · Zeichnen · Simulation · Tonsynthese |
| `gravitycup/disciplines/` | descent (Sturzrennen) · elimination · scatter |
| `gravitycup/season/` | Punktestand und Tabellengrafik |
| `gravitycup/build.py` | Seed rein, MP4 raus, Manifest ins Archiv |
| `runs/*.json` | ein Manifest je **gesendeter** Runde – kommende Folgen fehlen hier bewusst, sonst stünde ihr Ausgang hier vor der Ausstrahlung |
| `tests/` | 235 unittest, ohne pytest lauffähig |
| `docs/baustein-*.md` | je Baustein die gemessenen Zahlen und die Fehler, die dabei gefunden wurden |

```bash
python -m unittest discover -s tests
```

## Was in einem Rundenmanifest steht

Seed, Disziplin, Codestand samt Sauberkeit des Arbeitsbaums, die Versionen von
Python, pymunk, numpy, Pillow, scipy und ffmpeg, die Gestaltungsparameter,
die Kodiereinstellungen und das vollständige Ergebnis mit Zielzeiten.

Der Punktestand wird **nicht geführt, sondern gerechnet** — aus `runs/*.json`.
Es gibt keinen Zähler, der von der Wirklichkeit abweichen könnte.

```bash
python -m gravitycup.season.standings --verlauf
```

## Wie die Seeds gewählt werden

```bash
python -m gravitycup.disciplines.descent --search 10
```

Zeigt brauchbare Seeds — **ohne** Sieger und Reihenfolge. Wer sich den Seed
nach dem Ausgang aussucht, hat ihn geschrieben statt simuliert. Deshalb zeigt
die Suche den Ausgang bewusst nicht an.

## Fairness

Startplatz-Bias und Engstellen werden vor jedem Saisonstart gemessen, nicht
angenommen:

```bash
python -m gravitycup.disciplines.descent --geometrie 200
python -m gravitycup.disciplines.descent --fairness 300
```

Entsprechend für `elimination` und `scatter`. Die gemessenen Werte und die
Fehler, die diese Prüfungen gefunden haben, stehen in `docs/baustein-*.md`.

## Schrift

Die Videos laufen mit Bahnschrift aus dem System. Die gehört Microsoft und
liegt nur auf Windows — die Schriftdatei ist deshalb nicht Teil dieses Repos
(→ `assets/fonts/LIESMICH.md`). Aufs Nachrechnen hat das keinen Einfluss: die
Reihenfolge entsteht in der Physik, nicht beim Zeichnen.

## Lizenz

Noch nicht festgelegt.
