#!/usr/bin/env python3
"""
Tests fuer Baustein B2 (physics.py).

Jeder Test haelt eine Eigenschaft fest, die der Prototyp NICHT hatte.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
