#!/usr/bin/env python3
"""
Tests fuer Baustein B2 (physics.py).

Jeder Test haelt eine Eigenschaft fest, die der Prototyp NICHT hatte.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gravitycup.core import physics, theme  # noqa: E402


class TestDeterminismus(unittest.TestCase):
    def test_gleicher_seed_gleicher_lauf(self):
        a = physics.simulate(physics.demo_track(7), 7)
        b = physics.simulate(physics.demo_track(7), 7)
        self.assertEqual(a.order, b.order)
        self.assertEqual(len(a.frames), len(b.frames))
        self.assertEqual(a.frames, b.frames)
        self.assertEqual(len(a.hits), len(b.hits))

    def test_anderer_seed_anderer_lauf(self):
        a = physics.simulate(physics.demo_track(7), 7)
        b = physics.simulate(physics.demo_track(11), 11)
        self.assertNotEqual(a.frames, b.frames)

    def test_speichern_und_laden_aendert_nichts(self):
        import tempfile, os
        a = physics.simulate(physics.demo_track(7), 7)
        fd, pfad = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            physics.save(a, pfad)
            b = physics.load(pfad)
            self.assertEqual(a.order, b.order)
            self.assertEqual(a.frames, b.frames)
            self.assertEqual(a.finish_times, b.finish_times)
        finally:
            os.unlink(pfad)


class TestWertung(unittest.TestCase):
    """In einer Liga darf keine Wertung unvollstaendig sein."""

    def setUp(self):
        self.r = physics.simulate(physics.demo_track(7), 7)

    def test_rangfolge_ist_immer_vollstaendig(self):
        """Der Prototyp fuehrte nur die Angekommenen. Beim echten Lauf mit
        seed=7 kamen vier von fuenf an – VIOLET fehlte in der Liste und
        haette in der Saisontabelle stillschweigend null Punkte bekommen."""
        self.assertEqual(sorted(self.r.order), list(range(5)))
        self.assertEqual(len(set(self.r.order)), 5)

    def test_angekommene_stehen_vor_nicht_angekommenen(self):
        letzte_platzierung = {t: i for i, t in enumerate(self.r.order)}
        for angekommen in self.r.finished:
            for offen in range(5):
                if offen in self.r.finished:
                    continue
                self.assertLess(letzte_platzierung[angekommen],
                                letzte_platzierung[offen])

    def test_zielzeiten_sind_aufsteigend(self):
        zeiten = [self.r.finish_times[i] for i in self.r.finished]
        self.assertEqual(zeiten, sorted(zeiten))

    def test_sieger_ist_der_erste_der_rangfolge(self):
        self.assertEqual(self.r.winner, self.r.order[0])


class TestZielerfassung(unittest.TestCase):
    def test_subframe_zeiten_sind_feiner_als_ein_bild(self):
        """Der Prototyp prueft nur einmal je Bild. Zwischen zwei Bildern legt
        eine Kugel bis zu 43 Pixel zurueck – mehr als ihr Durchmesser. Zwei
        Kugeln im selben Bild waren damit ununterscheidbar."""
        r = physics.simulate(physics.demo_track(7), 7)
        bild_dauer = 1.0 / r.fps
        zeiten = sorted(r.finish_times.values())
        # Mindestens eine Zeit darf nicht auf einem glatten Bildvielfachen liegen
        krumm = [t for t in zeiten if abs((t / bild_dauer) % 1.0) > 1e-6]
        self.assertTrue(krumm, "alle Zielzeiten liegen auf glatten Bildgrenzen")

    def test_regel_erkennt_durchgang(self):
        regel = physics.RaceToLine(100.0)
        self.assertIsNone(regel.crossed(50.0, 90.0))
        self.assertIsNone(regel.crossed(110.0, 130.0))
        anteil = regel.crossed(90.0, 110.0)
        self.assertIsNotNone(anteil)
        self.assertAlmostEqual(anteil, 0.5, places=6)

    def test_regel_zaehlt_nur_einmal(self):
        regel = physics.RaceToLine(100.0)
        self.assertIsNotNone(regel.crossed(99.0, 101.0))
        self.assertIsNone(regel.crossed(101.0, 103.0))


class TestKollisionsprotokoll(unittest.TestCase):
    def test_aufprallorte_nutzen_die_volle_breite(self):
        """Der teuerste Tonfehler des Prototyps: der Aufprallort wurde ueber
        beide Koerpermittelpunkte gemittelt. Bei Wand und Stift ist der
        zweite Koerper der statische Raum mit Mittelpunkt (0,0) – jede
        X-Position wurde also halbiert und die rechte Bildhaelfte klappte in
        die Mitte. Genau daraus wird das Stereopanorama gerechnet."""
        r = physics.simulate(physics.demo_track(7), 7)
        wand_treffer = [h for h in r.hits if h.kind in ("wall", "peg")]
        self.assertTrue(wand_treffer, "keine Wandtreffer protokolliert")
        groesstes_x = max(h.x for h in wand_treffer)
        self.assertGreater(
            groesstes_x, theme.WIDTH * 0.6,
            f"kein Wandtreffer rechts der Mitte (groesstes x={groesstes_x}) – "
            f"deutet auf den halbierten Aufprallort hin",
        )

    def test_aufprallorte_liegen_im_bild(self):
        r = physics.simulate(physics.demo_track(7), 7)
        for h in r.hits:
            self.assertGreaterEqual(h.x, -50)
            self.assertLessEqual(h.x, theme.WIDTH + 50)

    def test_leise_beruehrungen_werden_nicht_protokolliert(self):
        r = physics.simulate(physics.demo_track(7), 7)
        for h in r.hits:
            self.assertGreaterEqual(h.impulse, physics.MIN_IMPULSE)

    def test_jeder_treffer_gehoert_zu_einem_teilnehmer(self):
        r = physics.simulate(physics.demo_track(7), 7)
        for h in r.hits:
            self.assertIn(h.competitor, range(5))
            self.assertIn(h.kind, ("wall", "peg", "marble"))


class TestFairness(unittest.TestCase):
    def test_startplaetze_liegen_auf_gleicher_hoehe(self):
        """Im Prototyp standen sie diagonal ueber 312 Pixel gestaffelt –
        der unterste Platz erreichte die erste Rampe rund 7,6 Bilder frueher."""
        track = physics.demo_track(7)
        hoehen = {y for _x, y in track.starts}
        self.assertEqual(len(hoehen), 1,
                         f"Startplaetze auf verschiedenen Hoehen: {hoehen}")

    def test_startplaetze_werden_verlost(self):
        """Wer welchen Platz bekommt, darf nicht an der Startnummer haengen."""
        gewinner = set()
        for seed in range(20):
            r = physics.simulate(physics.demo_track(seed), seed)
            gewinner.add(r.winner)
        self.assertGreater(len(gewinner), 1,
                           "ueber 20 Laeufe gewinnt immer derselbe Teilnehmer")


class TestAbbruch(unittest.TestCase):
    def test_zu_wenige_startplaetze_werden_gemeldet(self):
        track = physics.demo_track(7)
        track.starts = track.starts[:2]
        with self.assertRaises(physics.SimulationError):
            physics.simulate(track, 7)

    def test_unerreichbares_ziel_bricht_ab_statt_ein_video_zu_bauen(self):
        """Kommt niemand an, soll es krachen. Der Prototyp lieferte
        klaglos ein 60-Sekunden-Video ohne Sieger."""
        track = physics.demo_track(7)
        track.finish_y = 10_000_000.0
        with self.assertRaises(physics.SimulationError):
            physics.simulate(track, 7, max_seconds=3.0)


class TestLaenge(unittest.TestCase):
    def test_lauf_passt_in_ein_short(self):
        """Die Roadmap will 25–40 s. Laeuft es laenger, taugt es nicht."""
        r = physics.simulate(physics.demo_track(7), 7)
        self.assertGreater(r.duration, 15.0)
        self.assertLess(r.duration, 45.0,
                        f"Lauf dauert {r.duration:.1f}s – zu lang fuer ein Short")


class TestStartplatzStatistik(unittest.TestCase):
    """Die Auswertung, die am 29.07.2026 einen falschen Alarm ausgeloest hat.

    Gemeldet wurde „die Streuung ist unfair, Chi-Quadrat 10,8 ueber der
    kritischen 9,49" – gemessen mit n=2000. Tatsaechlich reisst das
    Sturzrennen dieselbe Schwelle schon bei n=1200, und die Effektstaerke
    aller drei Disziplinen ist praktisch gleich. Der Fehler lag nicht in der
    Disziplin, sondern im Vergleich.
    """

    def test_chi2_und_p_gegen_handrechnung(self):
        s = physics.startplatz_statistik([206, 253, 252, 266, 222],
                                         ziehungen=200)
        self.assertAlmostEqual(s["chi2"], 10.30, places=1)
        self.assertAlmostEqual(s["p"], 0.0357, places=3)

    def test_gleichverteilung_hat_kein_signal(self):
        s = physics.startplatz_statistik([240] * 5, ziehungen=200)
        self.assertAlmostEqual(s["chi2"], 0.0, places=9)
        self.assertAlmostEqual(s["p"], 1.0, places=9)

    def test_der_zufallsrahmen_schrumpft_mit_der_laufzahl(self):
        """Das ist der Kern: je laenger man misst, desto enger liegt der
        staerkste Platz allein durch Zufall an den 20 %. Ohne diese Zahl
        sagt „staerkster Platz 22 %" nichts."""
        rahmen = [physics.startplatz_statistik([n // 5] * 5,
                                               ziehungen=4000)["zufall_grenze"]
                  for n in (200, 1200, 3600)]
        self.assertEqual(rahmen, sorted(rahmen, reverse=True))
        self.assertGreater(rahmen[0], 0.24)
        self.assertLess(rahmen[-1], 0.23)

    def test_feste_chi2_schwelle_kippt_allein_mit_der_laufzahl(self):
        """Dieselbe Verteilung, nur laenger gemessen – und eine feste
        Schwelle sagt einmal „in Ordnung" und einmal „unfair". Genau dieser
        Fehlschluss ist passiert. Er darf nicht wieder moeglich sein, ohne
        dass dieser Test faellt.
        """
        anteile = [0.196, 0.207, 0.192, 0.218, 0.186]
        klein = physics.startplatz_statistik(
            [round(a * 200) for a in anteile], ziehungen=200)
        gross = physics.startplatz_statistik(
            [round(a * 20000) for a in anteile], ziehungen=200)

        self.assertAlmostEqual(klein["staerkster_anteil"],
                               gross["staerkster_anteil"], places=2)
        self.assertLess(klein["chi2"], 9.488)
        self.assertGreater(gross["chi2"], 9.488)

    def test_urteil_haengt_an_der_effektstaerke_nicht_an_chi2(self):
        """Beide Verteilungen oben sind dieselbe Sache. Das Urteil darf sich
        zwischen ihnen nicht umdrehen."""
        anteile = [0.196, 0.207, 0.192, 0.218, 0.186]
        for n in (200, 20000):
            with self.subTest(n=n):
                s = physics.startplatz_statistik(
                    [round(a * n) for a in anteile], ziehungen=2000)
                ok, _ = physics.fairness_urteil(s)
                self.assertTrue(ok, f"bei n={n} faelschlich als unfair "
                                    f"gemeldet")

    def test_echte_dominanz_wird_erkannt(self):
        """Der Fall, um den es wirklich geht: ein Platz gewinnt zu oft."""
        s = physics.startplatz_statistik([500, 200, 150, 100, 50],
                                         ziehungen=200)
        ok, grund = physics.fairness_urteil(s)
        self.assertFalse(ok)
        self.assertIn("50.0 %", grund)

    def test_leere_messung_stuerzt_nicht_ab(self):
        s = physics.startplatz_statistik([0, 0, 0, 0, 0], ziehungen=10)
        self.assertEqual(s["laeufe"], 0)
        self.assertEqual(s["p"], 1.0)


class TestStartauslosung(unittest.TestCase):
    """Die Auslosung der Startplaetze ist nachspielbar – und muss es sein.

    `simulate` lost die Plaetze mit `random.Random(seed)` aus. Die
    Fairnessmessung jeder Disziplin spielt genau diese Auslosung nach, um
    einen Sieg dem richtigen STARTPLATZ zuzuordnen. Das funktioniert nur,
    solange zwischen `random.Random(seed)` und dem Mischen kein weiterer
    Zufall verbraucht wird.

    Faellt dieser Test, misst jede `--fairness`-Ausgabe im Projekt ab dann
    Rauschen statt Startplatz-Schraeflage – ohne dass sonst irgendetwas
    auffaellt. Das ist der Grund, warum er hier steht.
    """

    def nachgespielt(self, seed, count=5):
        rng = random.Random(seed)
        plaetze = list(range(count))
        rng.shuffle(plaetze)
        return plaetze

    def test_auslosung_ist_nachspielbar(self):
        for seed in (1, 7, 42, 123):
            with self.subTest(seed=seed):
                track = physics.demo_track(7)
                r = physics.simulate(track, seed)
                plaetze = self.nachgespielt(seed)
                for teilnehmer, platz in enumerate(plaetze):
                    self.assertAlmostEqual(
                        r.frames[0][teilnehmer][0], track.starts[platz][0],
                        places=6,
                        msg=f"Teilnehmer {teilnehmer} startet nicht auf dem "
                            f"ausgelosten Platz {platz}")

    def test_die_auslosung_haengt_am_seed(self):
        """Gleicher Seed, gleiche Auslosung – sonst waere die Runde nicht
        nachrechenbar."""
        self.assertEqual(self.nachgespielt(5), self.nachgespielt(5))

    def test_verschiedene_seeds_losen_verschieden(self):
        verschieden = {tuple(self.nachgespielt(s)) for s in range(1, 40)}
        self.assertGreater(len(verschieden), 10,
                           "Die Auslosung variiert kaum – dann sitzt jede "
                           "Farbe faktisch auf einem festen Platz")


if __name__ == "__main__":
    unittest.main(verbosity=2)
