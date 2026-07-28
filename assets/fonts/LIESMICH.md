# Schriften

Hier gehört die **Hausschrift des Kanals** als `GravityCup.ttf` hinein.

`gravitycup/core/theme.py` sucht diese Datei zuerst und nimmt nur dann eine
Systemschrift, wenn sie fehlt.

## Warum das wichtig ist

Aktuell läuft alles mit **Bahnschrift** aus `C:\Windows\Fonts`. Die gehört
Microsoft, liegt nur auf Windows und darf nicht mitgeliefert werden. Sobald die
Produktion auf einen anderen Rechner oder in eine Linux-VM umzieht, sieht jedes
danach gebaute Video anders aus – und der Wiedererkennungswert des Kanals ist
dahin.

Liegt hier eine frei lizenzierte Schrift, kann das nicht passieren.

## Empfehlung

Eine Schrift unter SIL Open Font License, kondensiert und sportlich:

| Schrift | Warum |
|---|---|
| **Oswald** | kondensiert, mehrere Gewichte, sehr gut lesbar auf kleinen Displays – deckt Überschrift und Rangliste allein ab |
| Bebas Neue | Klassiker für Sportgrafik, nur Großbuchstaben |
| Anton | sehr fett, plakativ, gut für Titelkarten |
| Barlow Condensed | ruhiger, viele Schnitte |

Datei herunterladen, in `GravityCup.ttf` umbenennen, hier ablegen. Danach meldet
`python -m gravitycup.tools.probe_theme` keine Warnung mehr.
