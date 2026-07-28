# B2 – Simulationsgrundlage

`gravitycup/core/physics.py`
Stand 28.07.2026 · Test: `python -m gravitycup.core.physics --seed 7`

## Was der Baustein macht

Die gemeinsame Basis aller Disziplinen. Eine Disziplin liefert nur zwei Dinge:
die **Geometrie** (`Track`: Rampen, Stifte, Startplätze, Ziellinie) und die
**Siegbedingung**. Alles andere steht hier und ist für jede Disziplin gleich:
Aufbau des Raums, Zeitschritte, Kollisionsprotokoll, Bildabtastung, Rangfolge.

Ergebnis ist ein `RunResult` – reine Daten, kein Bild, kein Ton. Erst `draw.py`
macht daraus Bilder, `audio.py` einen Ton.

```bash
python -m gravitycup.core.physics --seed 7
python -m gravitycup.core.physics --seed 7 --json lauf.json
python -m unittest tests.test_b2_physics -v      # 19 Tests
```

## Vier Fehler des Prototyps, die hier behoben sind

### 1. Das Stereopanorama nutzte nur die halbe Bildbreite

Der Prototyp berechnete den Aufprallort als Mittel **beider Körpermittelpunkte**
(`sim.py:106`). Bei Wand- und Stiftreffern ist der zweite Körper aber der
statische Raum mit Mittelpunkt (0,0) – jede X-Position wurde also halbiert.

Gemessen am echten Lauf mit `seed=7`:

| | Prototyp | B2 |
|---|---|---|
| Wand-/Stifttreffer | 198 | 205 |
| kleinstes x | 39 | 48 |
| größtes x | **501** | **1032** |
| genutzte Bildbreite | **43 %** | 91 % |
| Verteilung (4 Spalten) | 94 / 104 / **0 / 0** | 90 / 5 / 16 / 94 |

Im Piloten kam **jeder einzelne Wandtreffer aus der linken Hörhälfte**. Die
rechte Hälfte des Stereobildes war leer – ausgerechnet bei dem Merkmal, mit dem
der Kanal wirbt. B2 nimmt den echten Kontaktpunkt aus dem Arbiter.

### 2. Die Wertung war unvollständig

`finish_order` enthielt nur, wer wirklich ankam. Beim echten Prototyp-Lauf mit
`seed=7` kamen **vier von fünf** an – VIOLET fehlte einfach in der Liste. In
einer Saisontabelle hätte das stillschweigend null Punkte bedeutet, ohne dass
irgendwo steht warum.

B2 liefert **immer** eine vollständige Rangfolge: erst die Angekommenen nach
exakter Zielzeit, dann der Rest nach erreichter Tiefe. `finished` sagt getrennt,
wer wirklich durchs Ziel ging.

### 3. Gleichstand entschied die Startreihenfolge

Der Prototyp prüft den Zieldurchgang einmal je Bild. Zwischen zwei Bildern legt
eine Kugel bis zu 43 Pixel zurück – mehr als ihr eigener Durchmesser. Zwei
Kugeln im selben Bild waren ununterscheidbar, und entschieden hat die Position
in der Liste, also der Zufall der Startauslosung.

B2 prüft bei **jedem Rechenschritt** (8× je Bild) und interpoliert den genauen
Zeitpunkt des Durchgangs. Die Zielzeiten stehen in `finish_times` und sind
feiner als ein Bild.

### 4. Die Startaufstellung war nicht neutral

Der Kommentar in `sim.py:78` verspricht eine „enge Traube in der Mitte, damit
keine Farbe strukturell bevorzugt ist". Tatsächlich standen die Kugeln
**diagonal über 312 Pixel gestaffelt**; der unterste Platz erreichte die erste
Rampe rund 7,6 Bilder früher. Ausgeglichen wurde das nur im Mittel über viele
Läufe – innerhalb eines Rennens war der Vorteil echt.

B2 setzt alle Startplätze auf **dieselbe Höhe** und verlost die Zuordnung.
Welcher Platz geometrisch besser ist, entscheidet weiter die Strecke – aber
niemand kann ihn sich aussuchen.

⚠ Offen: Ob ein bestimmter Startplatz über viele Läufe trotzdem im Vorteil ist,
ist **nicht gemessen**. Das gehört vor Saisonstart geprüft (200 Läufe je Seed),
und falls ja, rotieren die Plätze über die Saison.

## Weiteres

**Kein stiller Fehlschlag.** Erreicht niemand das Ziel, wirft `simulate()` eine
`SimulationError` statt ein 60-Sekunden-Video ohne Sieger zu liefern.

**Ein einziger Seed.** Startauslosung und Streckenstreuung leiten sich daraus
ab. Der Prototyp führte einen zweiten Seed für den Ton (`audio.py`, Standard 1),
der unabhängig vom Lauf war.

## Gemessen

| | |
|---|---|
| Simulation, 960 Bilder (32 s) | 0,15 s |
| Aufprälle im Protokoll | 228 |
| alle 19 Tests | 6,0 s |

## Noch offen

Die `demo_track()` in diesem Modul ist eine **Probestrecke**, damit B2 allein
testbar ist. Die richtige Strecke des Sturzrennens kommt in B4 – dann wird auch
die Länge auf das Short-Fenster von 25–40 s eingestellt.
