# B8 – Disziplin 3: Streuung

`gravitycup/disciplines/scatter.py`
Stand 28.07.2026 · Test: `python -m gravitycup.disciplines.scatter --seed 3`

## Was der Baustein macht

Ein Plinko-Brett: 62 versetzte Stiftreihen von Wand zu Wand, darunter neun
Landefächer mit Punktwerten. Gewertet wird das **Fach**, nicht die Zeit.

```bash
python -m gravitycup.disciplines.scatter --seed 3
python -m gravitycup.disciplines.scatter --search 10        # ohne Ausgang
python -m gravitycup.disciplines.scatter --geometrie 200
python -m gravitycup.disciplines.scatter --fairness 800
python -m gravitycup.build --discipline scatter --seed 3 --runde S01R03 --out folge03.mp4
python -m unittest tests.test_b8_scatter -v                 # 38 Tests
```

Damit ist die dritte Disziplin gebaut – und der Kanal hat genug Material für
die Halde, ohne die 3-je-Disziplin-Regel zu brechen.

## Die erste Disziplin, die kein Rennen ist

Der Prüfbericht warnt: *„die acht Disziplinen liefern strukturell
unvergleichbare Ergebnisse"*. Hier zeigt sich das zuerst: zwei Kugeln können
im **selben Fach** landen, und die Saisontabelle braucht trotzdem eine
vollständige Rangfolge über fünf Plätze.

**Gleichstandsregel: Punktwert, dann Landezeit.** Wer früher unten war, hat
den kürzeren Weg gefunden – eine Tatsache des Laufs, keine Auslosung. Die
Startnummer kommt so wenig vor wie beim Zieleinlauf in B2, aus demselben
Grund.

Das Fach steht **im Moment des Querens** der Wertlinie fest. Danach darf die
Kugel weiterhüpfen, ohne dass sich die Wertung ändert – sonst hinge das
Ergebnis daran, wann die Simulation aufhört. Die Wertlinie liegt zwischen den
Oberkanten der Trennwände und dem Boden: darüber könnte die Kugel das Fach
noch wechseln, darunter müsste man warten, bis sie liegen bleibt, und
„liegen bleiben" ist bei einer hüpfenden Kugel keine saubere Bedingung.

## Der Befund der Prüfung: das Brett belohnte den Normalfall

Eine Mehragenten-Prüfung fand 12 bestätigte Befunde, zwei davon schwer.

**1. Die äußerste Stiftspalte wurde nie gesetzt.** Das Raster war 119 px
weit, die Verwerfungsschwelle von `passt_durch` lag bei 118 – ein Pixel
Reserve. Mit ±5 px Streuung fielen 66–72 % aller Stifte durch, die äußerste
Spalte in **0 von 2000 Seeds**. Übrig blieb an beiden Wänden ein
senkrechter Kanal von im Median 152 px.

Der Wandkanal aus Fehler 1 war also nicht behoben, sondern nur nach innen
gewandert. Gemessen über 600 Seeds: **31,7 %** aller Kugeln landeten in
einem 50-Punkte-Fach, nur 6,6 % im 3-Punkte-Fach. Die Disziplin belohnte
den **häufigsten** Ausgang am höchsten – und nannte ihn im Kommentar
„Glückstreffer".

Behoben in drei Schritten:

* Das Raster spannt jetzt von **Wand zu Wand**; die äußersten Spalten sind
  Teil der Wand. Es gibt keinen Abstand mehr, in dem ein Kanal entstehen
  könnte.
* Der Stift-zu-Stift-Abstand hängt an `MIN_GAP` (74), nicht an `CLEARANCE`
  (90). Zwischen zwei Stiften soll eine Kugel durch – knapp. Das ist der
  Unterschied zwischen einem Plinko-Brett und einem Sieb.
* Sieben Spalten statt neun. Bei neun bleiben 92 px lichte Weite, und fünf
  Kugeln verkeilen sich: 35 von 60 Seeds erreichten das Ziel nicht.

**Und dann die eigentliche Erkenntnis:** auch mit vollständigem Raster
bleibt die Verteilung randlastig. Eine Glockenkurve entsteht nur, wenn der
Zufallslauf die Wände **nie erreicht**. Bei 1080 px Breite und 62 Reihen
erreicht er sie in jedem Lauf, und eine reflektierende Wand kehrt die
Verteilung um.

Statt das Brett gegen seine Physik zu biegen, folgen jetzt die **Werte der
Messung**: der Höchstwert liegt in der Mitte.

| | Anteil der Landungen | Wert |
|---|---|---|
| Mitte (Fach 5) | **11,6 %** | **50** |
| Rand (Fach 1 + 9) | 43,0 % | 3 |

Belohnt wird, was selten ist – und was selten ist, wurde gemessen, nicht
angenommen. Ein Test hält das fest: kippt die Verteilung, wird er rot.

**2. Die Rangliste im Video widersprach der Ergebniskarte.**
`build.rangfolge_bei` reihte die Gelandeten nach der **Zeit** – der
Siegbedingung des Sturzrennens. Gemessen über 39 Läufe: in **92 %** wich
die Rangliste vom Endergebnis ab, in **44 %** zeigte sie einen anderen
Führenden. Bei seed 11 sprang GOLD in der letzten Sekunde ohne sichtbare
Bewegung von Platz 4 auf 2.

B5 und B7 haben je einen Test dagegen – B8 fehlte er. Er ist nachgezogen,
und `rangfolge_bei` reiht jetzt nach `extras["punkte"]`.

## Vier Fehler beim Bauen, alle gemessen

### 1. Ein 126 px breiter freier Kanal an der Wand

Die Stifte hielten `CLEARANCE` (90 px) Abstand zur Wand – dieselbe Regel, die
in B4 richtig ist. Nur entstand daraus hier ein **senkrechter Kanal**, in dem
Kugeln ungebremst bis nach unten rutschten.

Gemessen an seed 1: GOLD, JADE und BLUE klebten am Ende alle bei x=999 an der
Wand. Über 40 Seeds landeten **132 von 200** Kugeln in den beiden äußersten
Fächern. Ein Plinko-Brett, dessen Verteilung an den Rändern spitz ist statt in
der Mitte, ist kein Plinko-Brett.

Behoben mit **Wandstiften**, die die Wand leicht überlappen – wie der
Rampenanfang im Sturzrennen. Die Regel „lichte Weite mindestens `MIN_GAP`"
gilt für Stellen, durch die eine Kugel *muss*. Hier soll sie gerade nicht
durch.

### 2. Der Lauf endete, während vier von fünf Kugeln noch fielen

`simulate` wartet nach der ersten Landung 6 Sekunden auf den Rest – das passt
zu einem Rennen, bei dem alle ungefähr gleich schnell unten sind. Auf einem
7500 px hohen Brett laufen die Landungen weit auseinander: **18 von 40 Seeds**
meldeten „nicht gelandet", obwohl die Kugeln bloß noch unterwegs waren.
`GEDULD = 22 s`.

### 3. Ungerade Stiftreihen waren immer nach rechts versetzt

Die Beschneidung am Rand traf dadurch links anders als rechts – und zwar in
**jedem** Seed gleich. Keine Streuung, sondern eine eingebaute Schräglage:
25,0 % Siege für Startplatz 1, χ² 10,44 gegen kritische 9,49.

### 4. `passt_durch` verwarf immer den rechten von zwei Stiften

Auch danach blieb ein Rest: **7 345 Stifte links gegen 6 692 rechts** über 40
Bretter – elf Standardabweichungen. `passt_durch` prüft gegen die schon
gesetzten Stifte; wer von links nach rechts setzt, verwirft immer den
**rechten**.

Beide Fehler sind mit dem Umbau auf ein Raster von Wand zu Wand
verschwunden: es wird nichts mehr beschnitten und nichts mehr verworfen. Die
Reihen stehen fest, die Streuung je Seed kommt aus dem **Reihenabstand**.

## Die Reihenzahl ist die Bremse

Freier Fall durch ein Brett ist schnell; jeder Aufprall kostet Tempo.
Gemessen über je 40 Seeds:

| Reihen | Dauer | brauchbar |
|---|---|---|
| 30 | 10–20 s | 0 % |
| 46 | 17–22 s | 38 % |
| **62** | **25–29 s** | **95 %** |
| 76 | 30–37 s | zu nah an der 38-s-Grenze |

Die Zahl musste zweimal nachgezogen werden, weil sich das Brett unter der
Hand geändert hat: erst war jeder zweite Stift verworfen worden
(durchlässig, schnell), nach der Reparatur steht das Raster vollständig
(dicht, langsam).

## Fairness

| | Wert |
|---|---|
| stärkster Startplatz (800 Läufe) | **22,1 %** (Erwartung 20 %) |
| χ² über die 5 Startplätze | 6,92 (kritisch 9,49) |
| verschiedene Landezeiten | 738 von 800 |
| Seeds ohne Ergebnis | 0 |

Das Raster steht seit der Reparatur **fest** an den Wänden – es darf nicht
mehr wandern, sonst entsteht dort wieder eine Lücke. Damit trotzdem kein
Brett dem anderen gleicht, schwankt der **Reihenabstand** mit dem Seed.
Ohne diese Streuung lag Startplatz 1 in jedem Lauf auf derselben Spalte:
24,8 % Siege, χ² 10,1.

Die Punktwerte sind symmetrisch (50 · 24 · 12 · 6 · 3 · 6 · 12 · 24 · 50).
Wären die hohen Werte auf einer Seite, hätte die Bildseite einen dauerhaften
Vorteil – dieselbe Lehre wie der gespiegelte Zickzack in B4.

## Neu in der Grundlage

* **`RunResult.extras`** – ein allgemeines Feld für alles, was eine Disziplin
  sonst noch ins Bild bringen will. Absichtlich **eines** statt eines je
  Disziplin: bei acht Disziplinen wäre `RunResult` sonst eine Sammelstelle
  für Sonderfälle. Die Streuung legt dort Fächer, Punktwerte und Landefach ab.
* **`Regel.schritt` bekommt `x_jetzt`.** Bis B7 reichte die Höhe; die
  Streuung wertet nach der Seite.
* **Die Beschriftung waagrechter Marken kommt aus den Daten.** Bei der
  Eliminierung steht dort `GATE n`; bei der Streuung markiert dieselbe Linie,
  wo das Fach feststeht, und „GATE 1" wäre schlicht falsch.
* **`fach_kanten(faecher=None)`** statt `faecher=FAECHER`: ein Modulwert als
  Vorgabewert wird beim Import eingefroren. `theme.py` warnt an derselben
  Stelle vor demselben Fehler. Aufgefallen ist es, weil ein Test die Fachzahl
  änderte und die Geometrieprüfung das nicht bemerkte.

## Offen

* **Die Verteilung ist randlastig, nicht glockenförmig.** Das ist Physik,
  keine Einstellung: reflektierende Wände kehren die Binomialverteilung um.
  Die Werte folgen jetzt der Messung. Wer die Glockenkurve will, braucht ein
  Brett, das breiter ist, als der Zufallslauf in 62 Reihen wandert – bei
  1080 px Bildbreite gibt es das nicht.
* **Nur `--reihen 62` ist vermessen.** Andere Werte laufen, sind aber
  ungeprüft.
* **χ² 6,92 ist der schwächste Fairness-Wert der drei Disziplinen**
  (Sturzrennen 7,4 bei n=500, Eliminierung 1,9 bei n=200). Unter der
  kritischen Schwelle, aber der Abstand ist kleiner. Vor dem Saisonstart
  einmal mit n = 2000 nachmessen.
