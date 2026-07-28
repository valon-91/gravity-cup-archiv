# B7 – Disziplin 2: Eliminierung

`gravitycup/disciplines/elimination.py` + die Regel-Naht in `core/physics.py`
Stand 28.07.2026 · Test: `python -m gravitycup.disciplines.elimination --seed 1`

## Was der Baustein macht

Fünf Teilnehmer, vier Kontrollpunkte. An jedem scheidet der Letzte aus, einer
bleibt übrig.

```bash
python -m gravitycup.disciplines.elimination --seed 1
python -m gravitycup.disciplines.elimination --search 10      # ohne Ausgang
python -m gravitycup.disciplines.elimination --geometrie 200
python -m gravitycup.disciplines.elimination --fairness 200
python -m gravitycup.build --discipline elimination --seed 1 --runde S01R02 --out folge02.mp4
python -m unittest tests.test_b7_elimination -v                # 34 Tests
```

Warum das Format trägt: beim Sturzrennen ist nach zehn Sekunden meist klar,
wer vorn liegt. Hier fällt alle paar Sekunden eine Entscheidung, und wer
zurückliegt, ist beim nächsten Kontrollpunkt **raus** – nicht bloß Vierter.
Der Zuschauer bekommt vier Mal einen Grund weiterzuschauen statt einmal.

## Die Naht, die es nur auf dem Papier gab

`docs/baustein-b2.md` behauptet seit B2: *„Eine Disziplin liefert nur zwei
Dinge: die **Geometrie** und die **Siegbedingung**."*

Im Code stand die Siegbedingung fest verdrahtet:

```python
regel = RaceToLine(track.finish_y)          # physics.py, vor B7
```

Die Roadmap sagt zu B7: *„Erste neue Disziplin. Ab hier ist die Struktur
bewiesen."* Genau hier ist sie es nicht gewesen. Neu ist deshalb:

* `physics.Regel` – Basisklasse. Sie sieht **jeden Rechenschritt** und sagt
  zwei Dinge: wer jetzt aus dem Spiel ist, und wann das Ergebnis feststeht.
  Die Wertung liefert sie ebenfalls: nur sie weiß, was ein Platz in dieser
  Disziplin bedeutet.
* `physics.RaceToLine` – das Sturzrennen, jetzt als Regel statt als
  Sonderfall in der Schleife.
* `simulate(..., regel=...)` – ohne Angabe gilt weiterhin „wer zuerst unten
  ist". B4 merkt von der Änderung nichts, ein Test nagelt das fest.
* `simulate` bricht ab, wenn eine Regel eine unvollständige Wertung
  liefert. Eine Regel, die jemanden vergisst, würde in der Saisontabelle
  stillschweigend null Punkte vergeben.

Ausgeschiedene werden aus dem `pymunk.Space` genommen – Kugel **und** Körper.
Sie bleiben stehen, wo sie waren, und sind für die anderen nicht mehr da.
Eine liegengebliebene Kugel mitten auf der Strecke wäre ein Hindernis, das
der Zuschauer nicht erklären kann.

## Vier Fehler beim Bauen, alle gemessen

### 1. Die Geduldsuhr lief ab der ersten Ausscheidung

`simulate` startet den Nachlauf, sobald „etwas passiert ist", und bricht
sechs Sekunden später ab. Zählte auch eine Ausscheidung als Startsignal, war
sechs Sekunden nach dem **ersten** Tor Schluss: **26 von 40 Seeds** endeten
mit einer statt vier Ausscheidungen. Ein Ausscheiden ist kein Zieleinlauf,
sondern der Anfang vom Rennen. `finish_frame` hängt jetzt nur an den
Zielzeiten.

### 2. Zu viel freier Fall

Erste Fassung: **8,8 Sekunden**. Das Fenster verlangt 20–38.

Mehr Höhe hätte es schlimmer gemacht – länger fallen heißt schneller fallen.
Die Bremse ist das **Rollen**, nicht der Weg. Das Sturzrennen holt seine 28 s
aus zehn Rampen, rund 2,8 s je Rampe.

| Rutschen je Abschnitt | Dauer |
|---|---|
| 0 (nur Trichter) | 8,8 s |
| 1 | 8,6–10,5 s |
| 2 | 16,6–17,8 s |
| **3** | **23,8–27,4 s** |

### 3. Stifte blind aufs Raster gesetzt

Dieselbe Blindheit, an der das Sturzrennen 94 % seiner Läufe verlor: das
Stiftraster wurde gesetzt, ohne es gegen den Trichter zu prüfen. Jetzt
entstehen erst **alle** Segmente, dann die Stifte mit
`physics.passt_durch()` gegen alles bisherige.

### 4. Eine Rutsche durfte fast auf die nächste fallen

430 px Abstand, bis zu 352 px Gefälle – blieben 18 px. Eine Kugel ist 64.
Die Seeds 16, 36, 37, 38, 44 und 55 endeten alle bei der 60-Sekunden-
Notbremse, mit gestapelten Kugeln am selben Rutschenende. Das Sturzrennen
hat gegen genau das einen Deckel (`RAMP_DROP_MAX`); hier fehlte er.

Dazu eine Zahl, die *nicht* aus B4 übernommen werden konnte:
`RUTSCHE_ENDE_WEITE` = 154 px statt der 90 px von `CLEARANCE`. Der Grund ist
die Disziplin selbst – der Trichter führt das Feld vor jedem Tor zusammen,
danach kommen die Kugeln als Pulk an. Vier Kugeln in einem Durchlass, der
genau eine breit ist, verkeilen sich.

**Nach allen vier Korrekturen: 80 von 80 Seeds brauchbar, immer genau vier
Ausscheidungen, 23,8–27,4 s.**

### 5. Die Torprüfung prüfte nichts

`pruefe_durchlaesse` suchte die Trichterpaare mit
`zip(segments[0::2], segments[1::2])`. Bei fünf Segmenten je Abschnitt liegt
das echte Paar auf den Indizes 3 und 4 – die Reißverschluss-Paarung liefert
(2,3) und (4,5) und erwischt **nie** ein Tor. Sie meldete trotzdem „in
Ordnung". Neu ist `tor_paare()`, das die Paare über ihre bekannte Position
holt, und ein Test, der ein absichtlich zu enges Tor unterschiebt.

## Fairness

| | Wert |
|---|---|
| stärkster Startplatz (200 Läufe) | **23,0 %** (Erwartung 20 %) |
| χ² über die 5 Startplätze | 1,85 (kritisch 9,49) |
| verschiedene Zielzeiten | 192 von 200 |
| Seeds ohne Ergebnis | 0 |

Nebenbei ist die Disziplin **robuster** als das Sturzrennen: eine
hängengebliebene Kugel blockiert den Lauf nicht, sie scheidet aus.

Beim Messen fiel auf, dass die Vielfalt zuerst über die **Videodauer**
gemessen wurde – die ist auf ganze Bilder gerundet und vom festen Nachlauf
beschnitten und meldete deshalb fälschlich ein Massenproduktions-Muster
(83 von 200). Gemessen wird jetzt die Zielzeit des Überlebenden.

## Der Befund der Prüfung: die Entscheidung war nicht im Bild

Eine Mehragenten-Prüfung fand 11 bestätigte Befunde. Der schwerste kam von
zwei Prüfern unabhängig voneinander, mit denselben Zahlen:

**30–42 % aller Ausscheidungen passierten außerhalb des Bildes.**

Die Kamera hing am Führenden (`theme.CAMERA_ANCHOR` = 45 % Bildhöhe).
Ausgeschieden wird aber per Definition **hinten** – die betroffene Kugel
stand im Mittel 404 px, maximal 876 px über ihrer eigenen Torlinie. Bei
seed 1 schieden GOLD, BLUE und VIOLET bei Bildschirm-y −423, −329 und −378
aus: drei von vier Entscheidungen unsichtbar. Der Zuschauer sah nur, wie in
der Rangliste ein Name durchgestrichen wurde.

Das trifft genau das Versprechen der Disziplin – „vier Mal einen Grund
weiterzuschauen" – und das des Kanals: eine Entscheidung, die man nicht
sieht, ist im Video nicht von einer geschriebenen zu unterscheiden.

Ein Prüfer wies zusätzlich nach, dass mein eigener „Fix" (die Kamera folgt
nur noch aktiven Kugeln) **wirkungslos** war: `kamerafahrt()` lieferte
bitgleich dasselbe wie ohne den Filter. Ein Ausgeschiedener kann gar nicht
der Tiefste sein – beim Ausscheiden sind alle anderen schon durchs Tor.

**Behoben:** die Kamera klemmt jetzt auch nach **oben**. Zielwert ist das
Minimum aus „Führender auf 45 %" und „Letzter mindestens
`KAMERA_RAND_OBEN` unter der Oberkante".

| | vorher | jetzt |
|---|---|---|
| Ausscheidungen im Bild | 64 % | **100 %** |
| Bilder ohne den Führenden | 0 % | 0 % |

Dass beides zugleich geht, ist gemessen und keine Annahme: die
Feldspreizung liegt im Median bei 255 px und maximal bei 1474 – bei 1920
Bildhöhe passt beides.

Weiterer bestätigter Blocker: **der Zwischenspeicher kannte die
Siegbedingung nicht.** `lauf_fingerabdruck` hasht Geometrie und Physik –
bis B6 war das vollständig, weil die Regel fest in `simulate` stand. Seit
B7 bringt jede Disziplin ihre eigene mit, und eine geänderte Regel hätte
einen alten `state.json` weiterverwendet. Jede Disziplin liefert jetzt
`regel_kennung(seed)`.

## Im Bild

* **Kontrollpunkte** als gestrichelte bernsteinfarbene Linie mit `GATE n`,
  bewusst anders als die Ziellinie: eine Kontrolllinie ist keine Ziellinie,
  und wer beides gleich zeichnet, macht aus zwei Regeln eine. Sie erlischt,
  sobald sie ausgelöst hat.
* **Ausgeschiedene** blenden über eine halbe Sekunde aus und schrumpfen
  dabei. Einfach stehenlassen sah aus wie ein Fehler, sofort verschwinden
  wie ein Bildfehler.
* In der **Rangliste** bleiben sie stehen, gedämpft und durchgestrichen. Sie
  ganz zu streichen wäre falsch – der Zuschauer soll sehen, *wer* raus ist,
  nicht nur dass jemand fehlt.
* Die **Kamera** folgt der tiefsten Kugel, die noch im Rennen ist. Zählten
  Ausgeschiedene mit, hinge sie an einer Kugel, die gar nicht mehr fährt.

## Offen

* **Der Punkteschlüssel passt nicht zu jeder Disziplin.** Der Prüfbericht
  warnt: *„die acht Disziplinen liefern strukturell unvergleichbare
  Ergebnisse (Verfolgung hat nicht einmal fünf vergleichbare Positionen)."*
  Die Eliminierung liefert eine vollständige Rangfolge über fünf Plätze,
  passt also. Für spätere Disziplinen ist das nicht garantiert.
* **Der Trichter ist die einzige Engstelle mit Absicht.** 172 px lichte
  Weite – zwei Kugeln passen, drei nicht. Das ist gewollt (Gedränge am Tor),
  liegt aber näher an der B4-Falle als alles andere im Projekt. Ein Test
  hält die Grenze fest.
* **Nur `--tore 4` ist vermessen.** Andere Werte sind über die CLI
  erreichbar, aber ungeprüft – und `Elimination` besteht zu Recht darauf,
  dass es genau `Teilnehmerzahl − 1` Kontrollpunkte gibt.
