# B6 – Punktestand + Tabellengrafik

`gravitycup/season/standings.py` · `gravitycup/season/card.py`
Stand 28.07.2026 · Test: `python -m gravitycup.season.standings`

## Der Punktestand wird nicht geführt, sondern gerechnet

Es gibt **keinen** mitlaufenden Zähler. Quelle ist immer das Rundenarchiv
`runs/*.json`, das B5 je Folge schreibt.

Das ist die eigentliche Entscheidung dieses Bausteins. Ein gepflegter Stand
könnte von der Wirklichkeit abweichen – durch einen Tippfehler, einen
abgebrochenen Lauf, eine Folge, die doch nicht hochgeladen wurde. Niemandem
würde es auffallen, und rückwirkend wäre jede veröffentlichte Tabelle
wertlos. Gerechnet dagegen ist die Tabelle immer genau das, was in den
Manifesten steht, aus denen auch die Videos entstanden sind.

`--json` schreibt eine Momentaufnahme für Grafik und Community-Posts. Sie
wird nie zurückgelesen; im JSON steht das auch drin.

```bash
python -m gravitycup.season.standings                  # aktuelle Tabelle
python -m gravitycup.season.standings --saison 1 --verlauf
python -m gravitycup.season.standings --json data/stand.json
python -m gravitycup.season.card --saison 1            # beide Grafiken
python -m unittest tests.test_b6_standings -v          # 30 Tests
```

## Der Punkteschlüssel: 10-6-4-2-1

Der Prüfbericht hält fest: *„Ebenso fehlt das **Punktesystem** vollständig –
der Satz ‚Punkte werden über alle Folgen mitgeführt' ist der Kern des
Konzepts, aber nirgends steht, wie viele Punkte es wofür gibt. B6 soll
standings.py bauen, ohne eine Regel zu bekommen."*

Also gemessen statt geraten. 12 Saisons zu je 24 **echten** Runden,
dieselben Läufe unter jedem Schlüssel ausgewertet – sonst vergleicht man
Schlüssel gegen Zufall:

| Schlüssel | Führungswechsel je Saison | punktgleich an der Spitze | Vorsprung 1./2. | Spanne 1./5. |
|---|---|---|---|---|
| 5-4-3-2-1 | 7,7 | 17 % | 5,8 | 16,1 |
| 8-5-3-2-1 | 6,3 | 0 % | 9,9 | 28,2 |
| **10-6-4-2-1** | **6,6** | **8 %** | **12,2** | **36,2** |
| 12-6-3-1-0 | 5,9 | 0 % | 15,9 | 48,8 |
| 3-2-1-0-0 | 8,3 | 8 % | 4,3 | 13,4 |

Flache Schlüssel halten die Tabelle länger offen, enden aber mit
Vorsprüngen, die nach Zufall aussehen. Steile Schlüssel geben eine klare
Tabelle, kosten aber Führungswechsel – und die sind der Grund zum
Wiederkommen (Roadmap §7, Tag 60: *„Sonst stimmt der Grund zum Abonnieren
nicht — Tabelle und Serienlogik deutlicher machen"*).

10-6-4-2-1 liegt bei den Führungswechseln fast auf dem flachen Schlüssel
(6,6 gegen 7,7), liefert aber einen lesbaren Endstand. Dazu ein
inhaltliches Argument: der Kanal fragt „Which color wins?". Bei 5-4-3-2-1
ist ein Sieg genau **einen** Punkt mehr wert als Platz zwei – das entwertet
die Frage, mit der jedes Video anfängt. Und niemand steht auf null: auch
der Letzte nimmt einen Punkt mit und bleibt in der Tabelle sichtbar.

**Ändern heißt: eine Zeile.** Aber nur zwischen zwei Saisons – mitten in
einer Saison wäre jede bereits veröffentlichte Tabelle falsch.

## Gleichstand

Nach Punkten passiert das in 8 % der Saisons. Die Regel entscheidet also
regelmäßig den Saisonsieg und ist kein Zierrat.

Der Reihe nach: **Punkte → Siege → zweite Plätze → dritte → … → Ergebnis
der jüngsten Runde.**

Was *nicht* vorkommt, ist die Startnummer. Nach demselben Grundsatz, aus
dem B2 den Gleichstand am Ziel per Subframe auflöst statt per Auslosung:
kein Platz darf einen Vorteil haben, den er nicht erlaufen hat. Ein Test
nagelt das fest.

Beim Bauen kam dabei eine Eigenschaft heraus, die vorher nicht offensichtlich
war: weil in einer Runde nie zwei Teilnehmer denselben Platz belegen,
unterscheiden sich zwei Einträge spätestens im `letzter_platz`. **Die
Tabelle ist nach einer gelaufenen Runde nie mehrdeutig** – es gibt immer
einen Ersten. Eine erste Fassung hatte deshalb eine „TIED AT THE TOP"-Anzeige,
die nie hätte erscheinen können; sie ist jetzt „LEVEL ON POINTS" und meint,
was sie sagt.

## Was das Archiv nicht durchgehen lässt

Ein still falsch gerechneter Punktestand ist der schlimmste Fehler dieses
Bausteins – er fällt niemandem auf. Deshalb bricht `lade_runden()` lieber ab:

| Fall | Verhalten |
|---|---|
| dieselbe Runde zweimal im Archiv | **Abbruch** – sonst zählt eine Folge doppelt |
| Manifest ohne `runde` | still übergangen (war ein Probelauf) |
| Rundenbezeichnung passt nicht auf `SxxRyy` | **Abbruch** |
| `reihenfolge_index` fehlt oder ist unvollständig | **Abbruch** |
| kaputtes JSON | **Abbruch** |
| leeres Archiv | leere Tabelle, kein Fehler |

`S1R1` und `S01R01` gelten dabei als **dieselbe** Runde – verglichen werden
die Zahlen, nicht die Schreibweise.

## Die Grafik

Zwei Formate, eine Quelle:

* **Videoformat 1080×1920** – Endkarte, Community-Post
* **Bannerformat 2048×1152** – Kanalbanner mit Saisonstand

Das Banner zeichnet nicht selbst, sondern ruft `make_branding.banner()` mit
dem Saisonstand auf. Die Funktion konnte das schon; ein zweiter Zeichenweg
wäre ein zweites Aussehen.

Nachgemessen mit dem Härtefall Saison 2 – Namen aus den Kommentaren mit den
vollen `theme.NAME_MAX` = 12 Zeichen und dreistelligen Punktzahlen nach 24
Runden: Name, Siegzähler und Punktspalte überschneiden sich nicht.

## Anbindung an B5

* Die **Endkarte** zeigt jetzt die Punkte der Runde (`+10 +6 +4 +2 +1`). Der
  Zuschauer soll sehen, was die Runde für die Tabelle bedeutet, nicht nur
  wer gewonnen hat.
* Oben rechts steht ein **Rundenzähler** (`S01 · R01`), eingeblendet mit der
  Rangliste. Der Prüfbericht bemängelt: *„Serialität ist nur für Videoende
  und Banner geplant, nicht für die ersten Sekunden — im HUD gibt es keine
  Rundennummer und keinen Saisonstand."* Bei einem Short sieht die Endkarte
  kaum jemand; wenn die Serie erst dort auftaucht, taucht sie für die
  meisten gar nicht auf.

## Offen

* **Der Saisonstand selbst fehlt in den ersten Sekunden.** Der Prüfbericht
  verlangt Rundenzähler *und* Punktestand; eingebaut ist nur der Zähler. Ein
  Fünf-Farben-Balken mit Punkten unter der Rangliste wäre der nächste
  Schritt – dafür ist aber erst zu klären, ob er nicht dasselbe Problem
  bekommt wie der Ranglistenkasten (verdeckt Teilnehmer).
* **Die Tabelle prüft nicht, ob ihre Runden noch nachrechenbar sind.**
  `build.py --pruefen` kann das je Runde; B6 ruft es nicht auf. Für einen
  Kanal, dessen Tabelle das Produkt ist, wäre ein
  `standings --pruefen-alle` folgerichtig.
* **Disziplinen ohne fünf vergleichbare Plätze.** Der Prüfbericht nennt
  „Verfolgung" (einer flieht, vier jagen). `lade_runden()` besteht auf einer
  vollständigen Rangfolge über alle fünf – solche Disziplinen brauchen
  entweder eine eigene Abbildung auf Plätze oder einen eigenen Schlüssel.
  Betrifft B7/B8 noch nicht.
