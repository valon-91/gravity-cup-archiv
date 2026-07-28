# B3 – Tonsynthese

Nachgereicht am 29.07.2026. B3 war seit dem Bau der einzige Baustein ohne
Doku und ohne Tests – im README stand „Doku fehlt". Dieses Dokument
beschreibt, was `gravitycup/core/audio.py` tut, und hält die Messungen
fest, die beim Nachreichen entstanden sind. Eine davon ist ein Fehler.

## Worum es geht

Kein Sample-Material, keine Fremdmusik, keine Tonbibliothek. **Jeder Klang
wird aus dem Kollisionsprotokoll der Simulation gerechnet.** Das ist keine
Sparmaßnahme, sondern dieselbe Behauptung wie beim Bild: was man hört, ist
passiert.

Praktisch heißt das auch: kein Urheberrechtsanspruch, keine Sperrung in
einem Land, keine Tonspur, die bei Folge 40 anders klingt als bei Folge 1.

## Die Zuordnung

| Was man hört | Woraus es kommt |
|---|---|
| Lautstärke eines Klicks | Aufprallimpuls, mit Exponent 0,55 gestaucht |
| Tonhöhe | Startnummer des Teilnehmers |
| Klangfarbe | Trefferart: Wand · Stift · Kugel-Kugel |
| Stereo-Position | X-Position des **Kontaktpunkts** im Bild |

Die Skala ist **pentatonisch** – C, D, F, G, B♭. Der Grund ist mechanisch,
nicht musikalisch: in einem Rennen treffen ständig mehrere Kugeln
gleichzeitig auf. In einer Pentatonik gibt es keine Kombination aus zwei
Tönen, die schief klingt. In einer Dur-Tonleiter schon.

Die Trefferarten unterscheiden sich in Grundfrequenz, Abklingzeit und im
Verhältnis von Rauschen zu Ton:

| Art | Frequenz | Abkling | Rausch | Ton |
|---|---|---|---|---|
| Wand | × 0,5 | 26 | 0,55 | 0,45 |
| Stift | × 2,0 | 34 | 0,30 | 0,70 |
| Kugel | × 4,0 | 30 | 0,18 | 0,82 |

Die Wand klingt dumpf und rauschig, ein Kugeltreffer hell und klar. Beim
Stift steht im Code ein Hinweis auf einen Fehler des Prototyps: dort lag der
Faktor bei 1,5, also eine Quinte – die liegt **neben** der Pentatonik. Eine
Oktave (Faktor 2) bleibt darin.

Dazu drei Elemente, die nicht aus Kollisionen kommen:

* **Klangteppich** – vier leicht verstimmte Teiltöne über C2, ganz leise
  (0,07), steigt zum Ziel hin von 0,55 auf 1,0 an.
* **Riser** – 2,4 s vor dem Zieleinlauf, 180 → 900 Hz.
* **Sting** – ein kurzer Akkord auf den Sieger, 2,6 s, exponentiell
  abklingend.

## Lautheit: gemessen statt eingetragen

Der Prototyp übergab ffmpeg **fest eingetragene** `measured_*`-Werte aus
einem einzigen Messlauf. Für jedes weitere Rennen sind diese Zahlen falsch –
die Normalisierung rechnet dann mit den Werten eines fremden Videos. Bei
einer Serie mit hunderten Folgen schwankt die Lautstärke dadurch hörbar.

`audio.py` misst deshalb selbst, nach **ITU-R BS.1770** mit K-Bewertung und
Gating, und regelt danach. Zielwert `TARGET_LUFS = -14.0` – das ist etwa der
Wert, auf den YouTube normalisiert.

Gemessen an den ersten neun Folgen, fertige MP4s:

| | |
|---|---|
| Lautheit | **−13,9 bis −14,8 LUFS** über neun Folgen |
| Spannweite | 0,9 LU |
| Lautheitsumfang (LRA) | 3,1 bis 5,9 LU |

Das ist der Teil, der funktioniert: neun Folgen, drei Disziplinen, und die
Lautstärke schwankt um weniger als 1 LU. Genau das, was der Prototyp nicht
konnte.

## Der Fehler: Sample-Peak statt True Peak

Die Konstante heißt `TARGET_TRUE_PEAK`. Begrenzt wurde aber der
**Sample**-Peak:

```python
spitze = float(np.abs(aus).max())      # das ist NICHT der True Peak
```

Zwischen zwei Abtastwerten kann die rekonstruierte Welle deutlich höher
ausschlagen als an den Punkten selbst. Am stärksten bei kurzen, harten
Transienten – also genau bei dem, woraus diese Tonspur besteht. Der weiche
tanh-Limiter macht es sogar schlimmer: er verschärft die Flanken.

Dazu kommt ein zweiter Beitrag, der vorher niemandem aufgefallen war: **der
AAC-Kodierer legt 2,6–3,1 dB drauf.**

Ergebnis, gemessen an allen neun ausgelieferten MP4s: True Peak zwischen
**−0,3 und +3,6 dBFS**. Acht von neun übersteuern.

### Die gemessene Kurve

descent, seed 1, jeweils komplett gebaut und am fertigen MP4 gemessen:

| Ziel in der WAV | WAV True Peak | MP4 True Peak | MP4 Lautheit |
|---|---|---|---|
| heute (kein Nachziehen) | −0,70 | **+2,40 dBFS** | −14,50 LUFS |
| −1,5 dBTP | −1,50 | +1,40 dBFS | −15,30 LUFS |
| **−3,0 dBTP** | −3,00 | **−0,40 dBFS** ✅ | −16,10 LUFS |
| −4,5 dBTP | −4,50 | −1,50 dBFS | −16,80 LUFS |

### Warum es nicht behoben ist

Sauber unter null zu kommen kostet rund **1,6 LU Lautheit**. YouTube regelt
lautes Material herunter, leises aber **nicht** herauf – die Folge klänge
danach leiser als alles neben ihr im Feed. Heute liegen wir mit −14,5 LUFS
fast genau auf dem Zielwert.

Beides ist ein Fehler. Zwischen zwei Fehlern zu wählen ist keine
Entscheidung, die ein Programm allein treffen sollte, und der richtige Weg
ist vermutlich keiner der beiden Werte in der Tabelle, sondern ein **echter
Limiter mit Vorausschau**, der nur die Transienten greift statt das ganze
Signal herunterzuziehen. Das ändert den Klangcharakter – und der ist bei
diesem Kanal das Produkt, nicht die Verpackung.

Deshalb liegt jetzt vor:

* `audio.true_peak()` – Messung mit vierfacher Überabtastung nach BS.1770-4.
* `TRUE_PEAK_NACHZIEHEN` – Schalter, **auf AUS**. Der Klang ist unverändert.
* `true_peak_dbfs` und `true_peak_begrenzt` in der Messung, die `build.py`
  ins Rundenmanifest schreibt.

## Tests

9 Tests in `tests/test_b3_audio.py`. Drei davon sind die eigentlichen:

* **True Peak liegt nie unter dem Sample-Peak.** Die rekonstruierte Welle
  geht durch die Abtastpunkte.
* **Ein Transient schlägt dazwischen höher aus.** Das ist der Kern des
  Fehlers, als ausführbare Aussage.
* **Der Schalter kostet Lautheit.** Fällt dieser Test, hat sich der Handel
  geändert – und die Entscheidung gehört neu getroffen.

## Was hier noch schwach ist

* **Der Ton ist nie gegen einen Referenzhörer geprüft worden.** Alle Aussagen
  hier sind Messungen, keine Höreindrücke. Der einzige Höreindruck, den es
  gibt, ist „Ton ist gut" zu S01R01 auf einem Handy (28.07.2026).
* **Der Klangteppich läuft ungeregelt mit.** Er geht in die Lautheitsmessung
  ein, hat aber keinen eigenen Pegelbezug zu den Klicks. Bei einem Lauf mit
  sehr wenigen Aufprallen dominiert er stärker als gedacht – gemessen wurde
  das nicht.
* **`TAIL_SECONDS = 2.0` ist gesetzt, nicht hergeleitet – und kleiner als der
  Sting.** Der Sieger-Akkord dauert 2,6 s. Dass er trotzdem nie abgeschnitten
  wird, liegt nicht an `TAIL_SECONDS`, sondern daran, dass der Lauf nach dem
  Zieleinlauf noch weiterläuft (Ergebniskarte). Nachgemessen an allen neun
  Runden: kleinste Reserve **3,67 s**, größte 11,07 s – der Akkord passt
  überall. Eine künftige Disziplin, die unmittelbar am Ziel endet, würde ihn
  kürzen, ohne dass jemand es merkt.
