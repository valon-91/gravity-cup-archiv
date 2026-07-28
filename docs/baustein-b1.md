# B1 – Gestaltung und Zeichenprimitive

`gravitycup/core/theme.py` · `gravitycup/core/draw.py`
Stand 28.07.2026 · Test: `python -m gravitycup.tools.probe_theme --sheet`

## Was der Baustein macht

`theme.py` hält **jede** Gestaltungsentscheidung des Kanals an einer Stelle:
Ausgabeformat, sichere Zonen, Farben, Teilnehmer, Masse, Schrift, Schriftgrößen.
Kein anderes Modul legt selbst eine Farbe oder Größe fest. Wer hier eine Zahl
ändert, ändert sie für jedes künftige Video – das ist Absicht, denn genau daran
hängt der Wiedererkennungswert.

`draw.py` zeichnet: Kamera, Hintergrundverlauf, Raster, Strecke, Stifte,
Ziellinie, Teilnehmer mit Nachleuchten, laufende Rangliste, Aufhänger und
Ergebniskarte. Das Supersampling ist gekapselt – nach außen wird immer in
Ausgabe-Pixeln gerechnet.

## Einzeltest

```bash
python -m gravitycup.tools.probe_theme --sheet
```

Erzeugt in `probe/` die vier Bildsituationen, die im fertigen Video vorkommen,
plus ein Kontaktblatt. Es braucht **keine Physik-Bibliothek** – die Szene ist
künstlich. Geprüft wird nur das Aussehen, nicht die Simulation.

Nützliche Schalter: `--scale 1` (schnell statt Endqualität) · `--only 4_result`
· `--names THUNDERBOLT KATARZYNA MAXIMILIAN BO WOLFGANG` (Saison-2-Namen
ausprobieren) · `--seed 12`.

```bash
python -m unittest discover -s tests -v
```

23 Tests, Laufzeit unter einer Sekunde, ohne pytest.

## Getroffene Entscheidungen

**Der Aufhänger steht oben, nicht in der Mitte.** Im Prototyp lag er mittig und
verdeckte in den ersten 2,2 Sekunden genau die Teilnehmer – also in der Zeit,
die über das Weiterschauen entscheidet. Die Teilnehmer sitzen bei rund 45 % der
Bildhöhe (`CAMERA_ANCHOR`), darum liegt die Hook-Zone bei 210–470 und ein Test
(`test_hook_verdeckt_das_rennen_nicht`) hält das fest.

**Kästen werden aus dem gemessenen Text gebaut, nicht geraten.** Im Prototyp
war der Kasten auf feste Werte gesetzt; die Unterzeile stand deshalb halb
außerhalb und überlappte die Zeile darüber. `hook_layout()` rechnet Kasten und
Textpositionen getrennt vom Zeichnen aus, damit Tests nachrechnen können, dass
nichts herausragt – auch bei sehr langen Texten.

**Sichere Zonen für Shorts.** Über dem Video liegen Bedienelemente: unten
Kanalname, Titel und Tonzeile, rechts die Knopfleiste. `SAFE_TOP/BOTTOM/LEFT/
RIGHT` halten alle Einblendungen davon frei; zwei Tests prüfen es.

**Farben auf Unterscheidbarkeit statt auf Buntheit.** Rund acht Prozent der
männlichen Zuschauer haben eine Rot-Grün-Schwäche – für sie ist ein sattes Grün
neben einem satten Rot derselbe Farbklecks. Darum steht statt eines Wiesengrüns
ein türkisstichiges JADE in der Palette, und alle fünf Farben unterscheiden
sich zusätzlich in der Helligkeit. Ein Test rechnet die Luminanzabstände nach.

| Teilnehmer | Farbe |
|---|---|
| RED | `#FF3B30` |
| GOLD | `#FFB300` |
| JADE | `#00D9A3` |
| BLUE | `#2E7DFF` |
| VIOLET | `#C15CFF` |

Der Grundton bleibt kühl und technisch. Buntes, spielzeughaftes Material zieht
bei YouTube die Einstufung „für Kinder gemacht" nach sich, und die kostet
Kommentare, Personalisierung und Erlöse.

**Farbe und Name sind getrennt.** `Competitor(key, name, color)`. Ab Saison 2
kommen die Namen aus den Kommentaren, die Farben bleiben. `theme.rename()`
setzt neue Namen und kappt sie auf 12 Zeichen; die Rangliste misst den
längsten Namen und wächst mit, statt abzuschneiden.

**Die Ergebniskarte zeigt die Reihenfolge dieser Runde** mit den Rundenpunkten
(+5 bis +1). Der Saisonstand kommt in B6 dazu – `result_card()` hat dafür schon
den Parameter `points`. Die Karte dunkelt kräftig ab, sonst scheinen Ziellinie
und ausrollende Kugeln durch die Tabelle.

## Schrift – offener Punkt

Verwendet wird **Bahnschrift Bold SemiCondensed**, die Windows-Fassung der
DIN 1451: technisch, schmal, auf kleinen Displays gut lesbar, nicht verspielt.

⚠ Bahnschrift gehört Microsoft und liegt nur auf Windows. Zieht die Produktion
je auf eine Linux-VM um, sieht **jedes danach gebaute Video anders aus** – genau
das, was der Wiedererkennungswert nicht verträgt. `theme.py` sucht deshalb
zuerst nach `assets/fonts/GravityCup.ttf`; liegt dort eine frei lizenzierte
Schrift, wird sie bevorzugt und es muss nichts geändert werden. Das Testskript
warnt bei jedem Lauf, solange die Schrift aus dem System kommt.

## Gemessen

| | |
|---|---|
| Einzelbild, Supersampling 2 | rund 0,20 s |
| Einzelbild, Supersampling 1 | rund 0,05 s |
| hochgerechnet auf 900 Bilder (30 s Video) | rund 3 min |

Gemessen auf dem Windows-11-Rechner von Valon, mit der künstlichen Testszene
(6 Rampen). Die echte Strecke hat 12 Rampen, also wird es etwas mehr.

## Kanalbanner und Profilbild

```bash
python -m gravitycup.tools.make_branding
python -m gravitycup.tools.make_branding --standings 12 9 7 5 3 --season 1
```

Baut aus denselben Farben, derselben Schrift und demselben Hintergrund wie die
Videos: `banner.png` (2048×1152) und `profilbild.png` (800×800). Dazu drei
Vorschauen, die nicht hochgeladen werden – `banner_vorschau.png` markiert die
sichere Zone (1235×338, mehr sieht man auf dem Handy nicht),
`profilbild_rund.png` zeigt YouTubes runden Beschnitt und
`profilbild_klein.png` die Darstellung in Kommentaren.

Mit `--standings` zeigt das Banner statt des Claims den Saisonstand – so lässt
es sich nach jeder Runde in einem Aufruf neu bauen.

⚠ **Nie `font_variant()` benutzen**, um eine andere Schriftgröße zu bekommen:
Das erzeugt eine neue Schriftinstanz **ohne** die eingestellte Variante, und
der Schriftzug kommt dünn statt fett heraus (genau so passiert beim ersten
Banner). Stattdessen eine Größe in `theme.SIZES` eintragen und `theme.font()`
nehmen.

## Grenzen – was hier NICHT gilt

**„Gleicher Seed ⇒ bitgleiche Ausgabe" gilt nur innerhalb derselben Umgebung.**
Der Test `test_gleiche_eingabe_gleiches_bild` beweist, dass zweimal dasselbe
Zeichnen Pixel für Pixel dasselbe Bild ergibt. Über Pillow- und FreeType-
Versionen hinweg gilt das **nicht** – Schriftrasterung und der LANCZOS-Filter
können sich zwischen Versionen ändern. Wer echten Determinismus braucht, sichert
ihn auf der Ebene des Simulationsprotokolls, nicht auf der Bildbytes-Ebene.

**Die Rangliste kann kurz eine Kugel verdecken.** Nachzügler stehen weit oben
im Bild, dort sitzt die Rangliste. Der Kasten ist halbdurchsichtig, die Kugel
scheint durch. Falls das im echten Rennen stört, gehört es in B4 nachgezogen.
