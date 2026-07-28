# B4 – Disziplin 1: Sturzrennen

`gravitycup/disciplines/descent.py`
Stand 28.07.2026 · Test: `python -m gravitycup.disciplines.descent --seed 2`

## Was der Baustein macht

Fünf Teilnehmer fallen über eine Zickzack-Strecke nach unten; wer zuerst durch
die Ziellinie geht, gewinnt. Die Datei liefert **nur** die Geometrie
(`build_track`) und die Annahmekriterien (`check`) – Physik, Kollisions­protokoll
und Rangfolge stehen in `core/physics.py` (B2).

```bash
python -m gravitycup.disciplines.descent --seed 2         # ein Lauf
python -m gravitycup.disciplines.descent --search 8       # brauchbare Seeds
python -m gravitycup.disciplines.descent --geometrie 200  # Engstellen suchen
python -m gravitycup.disciplines.descent --fairness 300   # Startplatz-Bias
python -m gravitycup.tools.probe_descent --seed 2         # Strecke als Bild
python -m unittest tests.test_b4_descent -v               # 18 Tests
```

## Der Zustand vor dieser Sitzung

Zwei Messwerte sperrten das erste Video:

| | vorher | jetzt |
|---|---|---|
| Seeds ohne Zieleinlauf | **281 von 300 (94 %)** | 0 von 500 (0 %) |
| brauchbare Seeds (`check` leer) | 2,3 % | **96,8 %** |
| stärkster Startplatz | **42,1 %** | 24,2 % (Erwartung 20 %) |
| χ² über die 5 Startplätze | – | 7,38 (kritisch 9,49 bei p=0,05) |

Beides ist behoben. Der stärkste Platz liegt jetzt im Rauschen: bei 5 Plätzen
und 500 Läufen ist eine Standardabweichung 1,8 Prozentpunkte, und der
**Erwartungswert des Maximums** von fünf gleich starken Plätzen liegt bei rund
23,5 %. 24,2 % ist damit kein Vorteil, sondern Zufall.

## Fehler 1 – eine Engstelle von 36 Pixeln

**Der einzige Grund, warum 94 % der Läufe nie ankamen.**

Rampen durften bis `x = 1000` auslaufen, die rechte Wand steht bei `x = 1040`.
Beide sind 18 px dick, also blieben **36 px lichte Weite**. Eine Kugel ist
**64 px** dick. Sie passte nicht durch, verkeilte sich in der Ecke aus
Rampenende und Wand – und die vier anderen stauten sich dahinter. Der Lauf
stand nach fünf Sekunden still und lief die vollen 44 s Notbremse leer weiter.

Mitgeschrieben für `seed=2`, alle Angaben in Weltkoordinaten:

```
t=  0.0s  ( 540, 151) ( 462, 151) ( 618, 151) ( 696, 151) ( 384, 151)
t=  5.0s  ( 619, 860) ( 879, 954) ( 999, 998) ( 939, 976) (  81, 566)
t= 10.0s  ( 819, 933) ( 879, 954) ( 999, 998) ( 939, 976) (  81, 566)
t= 40.0s  ( 819, 933) ( 879, 954) ( 999, 998) ( 939, 976) (  81, 566)
                                   ^ verkeilt   ^^^^^^^^^^^^ Stau dahinter
```

Die fünfte Kugel bei `x=81` steckte im selben Fehlertyp: der äußerste Stift der
Mischzone stand bei `x=100`, die Wand bei `x=40` – 36 px Durchlass.

### Was der alte Kommentar behauptete

Im Code stand, kleine Neigungen hielten die Kugeln durch **Reibung** fest.
Nachgemessen stimmt das nicht: eine einzelne Kugel rollt auf jeder Neigung von
18 % bis 48 % sauber durch (jeweils > 3600 px in 8 s). Die Reibung war nie das
Problem, und die Gegenmaßnahme – steilere Rampen – hat den echten Fehler nur
verdeckt. Der Kommentar ist ersetzt.

### Die Regel, die daraus wurde

Zwei Zahlen, beide als **lichte Weite** (ohne die Dicke der Begrenzung):

```python
MARBLE_D  = 2 * theme.MARBLE_RADIUS   # 64 px – so dick ist eine Kugel
MIN_GAP   = MARBLE_D + 10             # 74 px – Ausschlusskriterium
CLEARANCE = MARBLE_D + 26             # 90 px – Zielwert beim Bauen
```

* `RAMP_END_MAX` ist **keine gewählte Zahl** mehr, sondern folgt aus
  `CLEARANCE`: `WALL_RIGHT - SEG_RADIUS - CLEARANCE - SEG_RADIUS` = 932.
* Gewürfelte Stifte werden gegen alle Segmente und alle bereits gesetzten
  Stifte geprüft (`passt_durch`) und sonst neu gewürfelt. Vorher landeten sie
  auch mal direkt auf der nächsten Rampe.
* `pruefe_durchlaesse(track)` sucht die Fallen und ist über `--geometrie N`
  aufrufbar. Zwei Tests kaputtmachen die Strecke absichtlich und prüfen, dass
  die Prüfung anschlägt – sonst sagt sie nur immer „in Ordnung".

## Fehler 2 – der Zickzack fiel immer nach rechts

Rampe 1 lief bisher **in jedem Rennen** von links oben nach rechts unten. Wer
rechts startet, trifft sie weiter unten, rollt kürzer und liegt sofort vorn.
Über zehn Rampen bleibt dieser Vorsprung erhalten: das Rennen war zu einem
guten Teil bei der Auslosung entschieden.

Die Mischzone (Plinko-Stifte direkt nach dem Start) sollte das auffangen,
schaffte es aber nur teilweise – gemessen über 300 Läufe:

| Variante | stärkster Platz |
|---|---|
| feste Richtung, ohne Mischzone | 96,5 % (Messung der Vorsitzung) |
| feste Richtung, mit Mischzone | 32,8 % |
| **Richtung pro Seed gespiegelt** | **24,0 %** |
| gespiegelt, ohne Mischzone | 24,3 % |

Der Zickzack wird jetzt pro Seed als Ganzes gespiegelt (`MIRROR_ZIGZAG`). Die
Mischzone bleibt trotzdem drin: sie trägt zur Fairness kaum etwas bei, liefert
aber die ersten Aufpralle für die Tonspur und streut das Feld vor Rampe 1.

## Fehler 3 – das Stiftraster stand immer gleich

Bei festem Raster stand der mittlere Startplatz in **jedem** Rennen genau über
einer Stiftspalte, die Nachbarn immer in der Lücke: 7 % Siege gegen 33 %. Das
Raster bekommt jetzt pro Seed eine zufällige Phase.

## Fehler 4 – Bild und Physik meinten verschiedene Stifte

Die Mischzone benutzte Stifte mit Radius 15, `draw.py` zeichnet aber
`theme.PEG_RADIUS` = 14. Im Video wäre die Kugel sichtbar **neben** dem Stift
abgeprallt. `descent.PEG_RADIUS` kommt jetzt aus `theme`, und `Canvas.peg()`
nimmt den Radius aus `physics.Peg` entgegen.

## Warum die Mischzone nicht dichter werden darf

Naheliegender Reflex gegen Startplatz-Vorteile: mehr Stiftreihen. Gemessen über
je 200 Läufe – fünf **gleichzeitig** fallende Kugeln verklemmen sich dann
gegenseitig:

| Mischzone | brauchbare Läufe |
|---|---|
| 5 Reihen × 5 Stifte (jetzt) | 97,5 % |
| 7 Reihen × 6 Stifte | 25,7 % |
| 12 Reihen × 7 Stifte | 0 % |
| 14 Reihen × 7 Stifte | 0 % |

Ein Plinko-Brett ist für **eine** Kugel gebaut. Wer hier verdichtet, baut
Staus.

## Annahmekriterien (`check`)

Ein Lauf darf nur veröffentlicht werden, wenn `check(result)` leer ist:

* Dauer zwischen 20 s und 38 s
* alle fünf im Ziel (nicht bloß nach Position gewertet)
* mindestens 60 Aufpralle, sonst bliebe die Tonspur leer
* Sieger höchstens 6 s vor dem Zweiten – sonst kein Spannungsbogen

96,8 % der Seeds erfüllen das. Als Nebenbefund: in **jedem** angenommenen Lauf
sind alle fünf Kugeln zu 100 % der Bilder gleichzeitig im Bild – die
Kamerafrage stellt sich für B5 also nicht. Bei abgelehnten Läufen spreizt sich
das Feld auf bis zu 4736 px, mehr als das Doppelte der Bildhöhe.

## Tests

`tests/test_b4_descent.py`, 18 Tests. Vier davon sind teuer (120 Simulationen,
zusammen ~20 s) und halten fest, was sich nur statistisch zeigt: Zielquote,
Vollständigkeit, Startplatz-Verteilung, Vielfalt der Zielzeiten.

Ein Test ist bewusst **ohne festen Seed** geschrieben: Er prüft, dass unter 40
Seeds mindestens 5 brauchbare sind, statt einen bestimmten Seed festzunageln.
Beim Vereinheitlichen des Stiftradius wurde `seed=7` unbrauchbar – ein
seed-fester Test wäre rot geworden, obwohl die Strecke besser geworden war.

## Offen

* **Archiv je veröffentlichter Runde** (Seed, Codestand, Bibliotheksversionen,
  Ergebnis). Ohne das kann niemand nachrechnen, ob ein Rennen echt war – und
  genau das ist das Verkaufsargument des Kanals. Der Prüfbericht nennt es;
  gebaut ist es nicht.
* Die Strecke ist bisher nur mit `RAMP_COUNT = 10` vermessen. Andere Werte sind
  über `--ramps` erreichbar, aber ungeprüft.
