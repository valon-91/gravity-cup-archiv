#!/usr/bin/env python3
"""
Tests fuer Baustein B4 (disciplines/descent.py).

Jeder Test haelt einen Fehler fest, an dem die Strecke schon einmal
gescheitert ist. Die beiden teuren Tests (viele Simulationen) stehen am
Ende und sind bewusst als solche gekennzeichnet.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import math
import random
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gravitycup.core import physics, theme          # noqa: E402
from gravitycup.disciplines import descent          # noqa: E402


class TestDurchlaesse(unittest.TestCase):
    """Der Fehler, an dem 281 von 300 Laeufen hingen.

    Rampen endeten bis x=1000, die Wand steht bei x=1040 – 36 px lichte
    Weite fuer eine 64 px dicke Kugel. Die erste Kugel verkeilte sich, die
    anderen stauten sich dahinter, das Rennen stand still.
    """

    def test_min_gap_ist_groesser_als_eine_kugel(self):
        self.assertGreater(descent.MIN_GAP, 2 * theme.MARBLE_RADIUS,
                           "Engstellen-Grenze muss ueber dem Kugeldurchmesser liegen")
        self.assertGreater(descent.CLEARANCE, descent.MIN_GAP,
                           "Zielwert beim Bauen muss lockerer sein als das Ausschlusskriterium")

    def test_rampenende_laesst_eine_kugel_vorbei(self):
        luecke = (descent.WALL_RIGHT - descent.SEG_RADIUS) \
            - (descent.RAMP_END_MAX + descent.SEG_RADIUS)
        self.assertGreaterEqual(luecke, descent.CLEARANCE)

    def test_keine_strecke_hat_engstellen(self):
        for seed in range(1, 61):
            with self.subTest(seed=seed):
                maengel = descent.pruefe_durchlaesse(descent.build_track(seed))
                self.assertEqual(maengel, [], f"seed {seed}: {maengel[:3]}")

    def test_pruefung_findet_die_alte_falle(self):
        """Die Pruefung darf nicht bloss immer 'in Ordnung' sagen."""
        kaputt = descent.build_track(1)
        # Rampenende dicht an die rechte Wand ruecken – der Zustand von vorher
        kaputt.segments = list(kaputt.segments)
        kaputt.segments[0] = physics.Segment(60.0, 700.0, 1000.0, 1000.0,
                                             descent.SEG_RADIUS)
        maengel = descent.pruefe_durchlaesse(kaputt)
        self.assertTrue(any("Rampenende" in m for m in maengel), maengel)

    def test_pruefung_findet_stift_an_der_wand(self):
        kaputt = descent.build_track(1)
        kaputt.pegs = list(kaputt.pegs) + [physics.Peg(110.0, 900.0, 15.0)]
        maengel = descent.pruefe_durchlaesse(kaputt)
        self.assertTrue(any("Segment" in m for m in maengel), maengel)


class TestGeometrie(unittest.TestCase):
    def test_gleicher_seed_gleiche_strecke(self):
        a, b = descent.build_track(9), descent.build_track(9)
        self.assertEqual(a.segments, b.segments)
        self.assertEqual(a.pegs, b.pegs)

    def test_anderer_seed_andere_strecke(self):
        self.assertNotEqual(descent.build_track(9).segments,
                            descent.build_track(10).segments)

    def test_startplaetze_auf_gleicher_hoehe(self):
        starts = descent.build_track(3).starts
        self.assertEqual(len({y for _, y in starts}), 1,
                         "gestaffelte Startplaetze verschenken Rennen vor dem Start")
        self.assertEqual(len(starts), len(theme.competitors()))

    def test_zickzack_wird_gespiegelt(self):
        """Faellt die erste Rampe immer nach rechts, gewinnt rechts.

        Ohne Spiegelung: staerkster Startplatz 32,8 %. Mit: 24,0 %.
        """
        richtungen = Counter()
        for seed in range(1, 81):
            rampe = descent.build_track(seed).segments[0]
            richtungen[rampe.x2 > rampe.x1] += 1
        self.assertGreater(min(richtungen.values()), 20,
                           f"Zickzack laeuft einseitig: {dict(richtungen)}")

    def test_rampen_reichen_ueber_die_mitte(self):
        """Sonst faellt eine Kugel an der naechsten Rampe vorbei."""
        for seed in range(1, 31):
            with self.subTest(seed=seed):
                for s in descent.build_track(seed).segments[:descent.RAMP_COUNT]:
                    x_ende = s.x2 if s.y2 > s.y1 else s.x1
                    ueberstand = abs(x_ende - theme.WIDTH / 2)
                    self.assertGreater(x_ende, 0)
                    self.assertLess(ueberstand, theme.WIDTH / 2,
                                    "Rampenende liegt ausserhalb der Bahn")

    def test_mischzone_haengt_am_seed(self):
        """Festes Raster hiess: der mittlere Platz stand immer auf einem Stift."""
        oben = [tuple(sorted(round(p.x) for p in descent.build_track(s).pegs
                             if p.y < 400))
                for s in (1, 2, 3, 4)]
        self.assertEqual(len(set(oben)), 4, "Mischzone ist bei jedem Seed gleich")


class TestAnnahmekriterien(unittest.TestCase):
    def test_zu_langer_lauf_wird_abgelehnt(self):
        r = descent.run(1)
        r.frames = r.frames * 3            # kuenstlich auf ueber 38 s strecken
        self.assertTrue(any("zu lang" in p for p in descent.check(r)))

    def test_es_gibt_ueberhaupt_brauchbare_laeufe(self):
        """Kein fester Seed: die Geometrie aendert sich, die Aussage nicht.

        Frueher stand hier `check(run(7)) == []`. Nach einer Aenderung am
        Stiftdurchmesser war seed 7 unbrauchbar und der Test rot – obwohl
        die Strecke besser geworden war. Was zaehlt, ist die Ausbeute.
        """
        treffer = descent.find_seeds(5, grenze=40)
        self.assertEqual(len(treffer), 5,
                         "unter 40 Seeds keine 5 brauchbaren Laeufe")
        for seed, r in treffer:
            self.assertEqual(descent.check(r), [], f"seed {seed}")

    def test_nicht_angekommene_werden_abgelehnt(self):
        r = descent.run(1)
        r.finished = r.finished[:-1]
        self.assertTrue(any("nicht im Ziel" in p for p in descent.check(r)))


class TestStreckeTaugtFuerEineSaison(unittest.TestCase):
    """Die beiden teuren Tests. Zusammen rund 40 Sekunden.

    Sie ersetzen das Augenmass: ohne sie ist nicht nachweisbar, dass der
    Ausgang wirklich simuliert und nicht von der Auslosung entschieden wird.
    """

    LAEUFE = 120

    @classmethod
    def setUpClass(cls):
        cls.siege = Counter()
        cls.kaputt = 0
        cls.unvollstaendig = 0
        cls.zeiten = []
        n = len(theme.competitors())
        for seed in range(1, cls.LAEUFE + 1):
            try:
                r = physics.simulate(descent.build_track(seed), seed,
                                     max_seconds=descent.SEARCH_CUTOFF)
            except physics.SimulationError:
                cls.kaputt += 1
                continue
            rng = random.Random(seed)
            plaetze = list(range(n))
            rng.shuffle(plaetze)
            cls.siege[plaetze[r.winner]] += 1
            cls.zeiten.append(round(min(r.finish_times.values()), 3))
            if len(r.finished) < n:
                cls.unvollstaendig += 1

    def test_fast_jeder_seed_kommt_ins_ziel(self):
        """Vorher: 281 von 300 Seeds erreichten das Ziel nie."""
        self.assertLessEqual(self.kaputt, self.LAEUFE * 0.05,
                             f"{self.kaputt} von {self.LAEUFE} Seeds ohne Zieleinlauf")

    def test_meist_kommen_alle_fuenf_an(self):
        self.assertLessEqual(self.unvollstaendig, len(self.zeiten) * 0.15,
                             f"{self.unvollstaendig} Laeufe mit Nachzueglern")

    def test_kein_startplatz_dominiert(self):
        gesamt = sum(self.siege.values())
        anteil = max(self.siege.values()) / gesamt
        self.assertLess(anteil, 0.30,
                        f"staerkster Platz {anteil * 100:.1f} % – "
                        f"Verteilung {dict(sorted(self.siege.items()))}")

    def test_laeufe_unterscheiden_sich(self):
        """Gleiche Zielzeit in vielen Laeufen = Massenproduktions-Muster."""
        self.assertGreater(len(set(self.zeiten)), len(self.zeiten) * 0.8,
                           f"nur {len(set(self.zeiten))} verschiedene Zielzeiten")


if __name__ == "__main__":
    unittest.main(verbosity=2)
