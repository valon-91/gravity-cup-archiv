#!/usr/bin/env python3
"""
Eigenschaften, die fuer JEDE Disziplin gelten muessen.

Warum es diese Datei gibt – und warum sie anders aussieht als die anderen:

Jede andere Testdatei haelt VORFAELLE fest, und das steht dort auch so:
„Jeder Test haelt einen Fehler fest, der gemessen wurde." Das schuetzt
zuverlaessig vor Rueckfaellen und **gar nicht** vor dem naechsten Fall
derselben Klasse. Am 31.07.2026 waren 330 Tests gruen, waehrend die Show
unsendbar war.

Aus der Chronik gezaehlt, zwei Klassen mit je fuenf Faellen:

  Eine Luecke, in die das Feld nicht passt
    B4    36 px zwischen Rampenende und Wand   -> 94 % der Laeufe verloren
    B7    18 px Rest bei 64 px Kugel
    B8   126 px freier Kanal an der Wand       -> 132 von 200 Kugeln
    B10  Ausgang mit zwei Kugelbreiten         -> verklemmt dauerhaft
    B10  111 px zwischen Stift und Seitenwand  -> zwei Kugeln verkeilt

  Eine Kennzahl meldet gruen, waehrend es steht
    B5   abgeschnittenes Video, ffmpeg quittiert mit Code 0
    B7   Torpruefung prueft durch falsche Paarung nichts, meldet "in Ordnung"
    B10  Kugel wird auf einem Rotorfluegel im Kreis getragen - sie BEWEGT
         sich und kommt nie an
    B10  `lebendig` als Mittelwert: 77 %, waehrend drei Minuten stehen
    B10  99 % gemeldet, waehrend der Sieger 25 Minuten vor dem Ausgang
         hin und her geschlagen wird

Beide Klassen haben eine gemeinsame Ursache, und die ist hier gefasst:
**eine Zahl wurde fuer fuenf Teilnehmer gemessen und fuer hundert
weiterverwendet.**

    python -m unittest tests.test_eigenschaften -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gravitycup.core import physics, theme                      # noqa: E402
from gravitycup.disciplines import arena, descent               # noqa: E402
from gravitycup.disciplines import elimination, scatter         # noqa: E402
from gravitycup.tools import show                               # noqa: E402

#: Jede Disziplin mit dem Feld, mit dem sie WIRKLICH laeuft. Nicht mit dem,
#: fuer das ihre Konstanten einmal gemessen wurden - das ist der Punkt.
DISZIPLINEN = [
    ("descent", descent, "hoch", 5),
    ("elimination", elimination, "hoch", 5),
    ("scatter", scatter, "hoch", 5),
    ("arena", arena, "quer", show.TEILNEHMER),
]


class EigenschaftsFall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._format = theme.FORMAT
        cls._comps = theme.competitors()

    @classmethod
    def tearDownClass(cls):
        theme.set_format(cls._format)
        theme.set_competitors(cls._comps)


class TestLueckenPassenZumFeld(EigenschaftsFall):
    """Wie breit eine Luecke sein muss, haengt am FELD, nicht an der Kugel.

    Die Kopplung hat gefehlt, und deshalb konnte die Arena mit hundert
    Teilnehmern eine Regel erben, die fuer fuenf gemessen war. Bei fuenf
    erreicht praktisch nie ein zweiter dieselbe Luecke im selben
    Augenblick; bei hundert erreichen sie jede gleichzeitig, und zwei
    brauchen zusammen 128 px statt 64.
    """

    def test_min_gap_deckt_das_feld(self):
        for name, modul, _, feld in DISZIPLINEN:
            with self.subTest(name):
                noetig = physics.mindest_luecke(feld)
                self.assertGreaterEqual(
                    modul.MIN_GAP, noetig,
                    f"{name} laeuft mit {feld} Teilnehmern, sichert aber nur "
                    f"{modul.MIN_GAP:.0f} px lichte Weite – noetig sind "
                    f"{noetig:.0f} px. Wer das Feld vergroessert, muss die "
                    f"Luecken mitvergroessern.")

    def test_clearance_liegt_ueber_min_gap(self):
        """Beim BAUEN mehr Abstand halten als beim PRUEFEN verlangt wird.

        Sonst liegt jede Strecke genau auf der Grenze, und Rundung oder
        Streuung druecken einzelne Paare darunter – die Lehre aus B4.
        """
        for name, modul, _, _ in DISZIPLINEN:
            with self.subTest(name):
                self.assertGreater(modul.CLEARANCE, modul.MIN_GAP, name)

    def test_die_strecken_halten_es_auch_ein(self):
        """Die Konstante zu pruefen genuegt nicht – die Strecke muss sie
        einhalten. Genau hier hat die Torpruefung aus B7 versagt: sie
        prueft durch eine falsche Paarung nichts und meldet "in Ordnung"."""
        for name, modul, fmt, feld in DISZIPLINEN:
            with self.subTest(name):
                theme.set_format(fmt)
                theme.set_competitors(theme.feld(feld))
                noetig = physics.mindest_luecke(feld)
                track = (modul.build_track(2, feld) if modul is arena
                         else modul.build_track(2))
                self.assertEqual(physics.engstellen(track, noetig), [],
                                 f"{name}: Engstelle unter {noetig:.0f} px")


class TestNichtsStehtStill(EigenschaftsFall):
    """Was eine Disziplin fuer brauchbar haelt, muss sich auch bewegen.

    Das ist die Eigenschaft, die in allen fuenf Faellen der zweiten Klasse
    verletzt war – zuletzt bei einer Show, die 63 von 63 Ausscheidungen
    meldete, waehrend das Bild stand.

    Die Arena prueft es seit dem 31.07.2026 selbst. Die drei
    Kurzdisziplinen haben es nie gemessen: dort faellt ein stehender Lauf
    heute nur INDIREKT durch, ueber "zu lang" und "nicht gelandet"
    (gemessen an scatter seed 4 und 7, 21,1 und 15,3 s Stillstand). Ein
    Lauf, der fuenfzehn Sekunden steht und dabei im Zeitfenster bleibt,
    kaeme durch.

    Die Arena bleibt hier aussen vor – ihr Lauf kostet zwei Minuten und
    wird in `test_b10_arena.TestLauf` geprueft.
    """

    SEEDS = range(1, 9)

    def test_ein_brauchbarer_lauf_bewegt_sich(self):
        theme.set_format("hoch")
        theme.set_competitors(theme.feld(5))
        geprueft = 0
        for name, modul, _, _ in DISZIPLINEN:
            if modul is arena:
                continue
            for seed in self.SEEDS:
                try:
                    r = modul.run(seed)
                except physics.SimulationError:
                    continue
                if modul.check(r):
                    continue            # schon abgelehnt, aus welchem Grund auch immer
                geprueft += 1
                steht = physics.stillstand(r)
                self.assertLessEqual(
                    steht, physics.MAX_STILLSTAND,
                    f"{name} seed {seed} gilt als brauchbar, steht aber "
                    f"{steht:.1f}s am Stueck (hoechstens "
                    f"{physics.MAX_STILLSTAND:.0f}s)")
        self.assertGreater(geprueft, 10,
                           "zu wenige brauchbare Laeufe – der Test prueft "
                           "sonst nichts und meldet trotzdem gruen")


class TestDieAnzeigePasstZumFeld(EigenschaftsFall):
    """Dieselbe Klasse wie die Luecken – nur im Bild statt in der Physik.

    Die Namensspalte der Rangliste stand fest bei 108 px. Das reichte fuer
    zwei Stellen und war nie falsch, solange fuenf oder vierundsechzig
    antraten. Gemessen an der Vorschau vom 31.07.2026 mit HUNDERT stand im
    Kasten woertlich "100GOLD K" – die Platzziffer im Namen.

    Geprueft wird deshalb nicht "100 passt", sondern dass die Spalte der
    laengsten wirklich vorkommenden Platzziffer folgt. Damit haelt es auch
    bei tausend.
    """

    FELDER = (5, 64, show.TEILNEHMER, 112)

    def _leinwand(self):
        from gravitycup.core import draw
        theme.set_format("quer")
        return draw.Canvas(1)

    def test_name_faengt_hinter_der_platzziffer_an(self):
        from gravitycup.core import draw
        c = self._leinwand()
        for feld in self.FELDER:
            with self.subTest(feld=feld):
                comps = theme.feld(feld)
                theme.set_competitors(comps)
                zeilen = draw.Canvas.hud_zeilen(list(range(feld)))
                rang_x, namen_x, breite = c.hud_spalten(zeilen, comps)
                for rang, idx in zeilen:
                    if idx is None:
                        continue
                    ziffer = c.measure(f"{rang + 1}", "hud_entry")[0]
                    self.assertLessEqual(
                        rang_x + ziffer, namen_x,
                        f"{feld} Teilnehmer: Platz {rang + 1} ist "
                        f"{ziffer:.0f} px breit und laeuft in den Namen")

    def test_der_kasten_umschliesst_den_laengsten_namen(self):
        """ACHTUNG, dieser Test hat Spielraum – gemessen am 31.07.2026.

        `theme.HUD_WIDTH` (320 px) ist heute breiter als jeder Inhalt: der
        laengste Eintrag endet je nach Feld bei 204 bis 263 px, es bleiben
        also 57 bis 116 px Luft. Der Test schlaegt deshalb erst an, wenn
        der Kasten um mehr als 60 px zu schmal wird (nachgemessen: 40 px
        sieht er nicht, 60 px faengt er).

        Er haelt also nichts, was heute knapp waere – er faengt den Tag,
        an dem die Namen laenger werden. Ab Saison 2 kommen sie aus den
        Kommentaren, und "ORCHID K" ist schon 143 px breit.
        """
        from gravitycup.core import draw
        c = self._leinwand()
        for feld in self.FELDER:
            with self.subTest(feld=feld):
                comps = theme.feld(feld)
                theme.set_competitors(comps)
                zeilen = draw.Canvas.hud_zeilen(list(range(feld)))
                _, namen_x, breite = c.hud_spalten(zeilen, comps)
                for _, idx in zeilen:
                    if idx is None:
                        continue
                    name = c.measure(comps[idx].name, "hud_entry")[0]
                    self.assertLessEqual(
                        namen_x + name, breite,
                        f"{feld} Teilnehmer: '{comps[idx].name}' laeuft "
                        f"aus dem Kasten")


class TestDieKennzahlMisstWasSieBehauptet(EigenschaftsFall):
    """`stillstand` muss einen stehenden Lauf auch als stehend melden.

    Ein Kriterium, das nie ausschlaegt, ist kein Kriterium – die
    Torpruefung aus B7 hat genau das zwei Bausteine lang vorgemacht.
    Hier wird deshalb ein Lauf GEBAUT, der steht, und geprueft, dass die
    Zahl ihn findet.
    """

    def _lauf(self, bilder, bewegt: bool):
        felder = []
        for f in range(bilder):
            y = 100.0 + (f * 20.0 if bewegt else 0.0)
            felder.append([(50.0, y, 0.0), (60.0, y, 0.0)])
        return physics.RunResult(
            seed=1, fps=30, track_name="probe", frames=felder, hits=[],
            order=[0, 1], finished=[], finish_times={}, finish_frame=None,
            segments=[], pegs=[], finish_y=9999.0)

    def test_ein_stehender_lauf_wird_gefunden(self):
        self.assertAlmostEqual(
            physics.stillstand(self._lauf(90, bewegt=False)), 89 / 30, 2)

    def test_ein_laufender_lauf_steht_nicht(self):
        self.assertEqual(physics.stillstand(self._lauf(90, bewegt=True)), 0.0)

    def test_ausgeschiedene_zaehlen_nicht_als_stillstand(self):
        """Wer ausgeschieden ist, steht mit Absicht. Zaehlte er mit, waere
        jede Eliminierung am Ende ein Stillstand."""
        r = self._lauf(90, bewegt=False)
        r.frames = [[(50.0, 100.0, 0.0), (60.0, 100.0 + f * 20.0, 0.0)]
                    for f in range(90)]
        r.eliminated = {0: 0.0}
        self.assertEqual(physics.stillstand(r), 0.0)


if __name__ == "__main__":
    unittest.main()
