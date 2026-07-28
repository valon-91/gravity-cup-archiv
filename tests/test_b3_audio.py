"""B3 – Tonsynthese: Lautheit und Spitzenwert.

Bis zum 29.07.2026 hatte B3 keine Tests. Diese hier decken die Stelle ab,
an der ein Fehler gemessen wurde: `TARGET_TRUE_PEAK` hiess True Peak,
begrenzt wurde aber der Sample-Peak.
"""

import math
import unittest

import numpy as np

from gravitycup.core import audio


class TestTruePeak(unittest.TestCase):

    def test_liegt_nie_unter_dem_sample_peak(self):
        """Die rekonstruierte Welle geht durch die Abtastpunkte – tiefer als
        der hoechste davon kann ihr Maximum nicht liegen."""
        rng = np.random.default_rng(7)
        for n in (256, 4096):
            x = rng.uniform(-0.8, 0.8, size=(n, 2))
            self.assertGreaterEqual(audio.true_peak(x) + 1e-9,
                                    float(np.abs(x).max()))

    def test_transient_schlaegt_zwischen_den_abtastpunkten_hoeher_aus(self):
        """Der Kern des Fehlers. Ein harter Wechsel sieht an den Abtast-
        punkten harmlos aus und ueberschreitet dazwischen die Grenze."""
        x = np.zeros((4800, 2))
        x[1000] = [0.9, 0.9]
        x[1001] = [-0.9, -0.9]
        self.assertGreater(audio.true_peak(x), float(np.abs(x).max()))

    def test_skaliert_linear(self):
        """Darauf beruht das Nachziehen: eine reine Skalierung erzeugt keine
        neuen Oberwellen, der True Peak folgt ihr exakt."""
        rng = np.random.default_rng(3)
        x = rng.uniform(-0.5, 0.5, size=(2048, 2))
        self.assertAlmostEqual(audio.true_peak(x * 0.5),
                               audio.true_peak(x) * 0.5, places=9)

    def test_stille_hat_keinen_ausschlag(self):
        self.assertAlmostEqual(audio.true_peak(np.zeros((512, 2))), 0.0)


class TestNormalize(unittest.TestCase):

    def signal(self, seed=1):
        rng = np.random.default_rng(seed)
        x = np.zeros((audio.SR, 2))
        for pos in range(200, audio.SR - 200, 700):
            x[pos] = rng.uniform(0.4, 1.0, size=2) * rng.choice([-1, 1])
            x[pos + 1] = -x[pos] * 0.9
        return x

    def test_misst_und_meldet_den_true_peak(self):
        _, m = audio.normalize(self.signal())
        self.assertIn("true_peak_dbfs", m)
        self.assertIn("true_peak_begrenzt", m)

    def test_gemeldeter_true_peak_stimmt_mit_der_messung(self):
        aus, m = audio.normalize(self.signal())
        gemessen = 20 * math.log10(max(1e-9, audio.true_peak(aus)))
        self.assertAlmostEqual(m["true_peak_dbfs"], gemessen, places=2)

    def test_abgeschaltet_bleibt_das_signal_unveraendert(self):
        """Der Schalter steht auf AUS, und das ist eine Entscheidung.
        Solange er aus ist, darf `normalize` nichts nachziehen."""
        alt = audio.TRUE_PEAK_NACHZIEHEN
        try:
            audio.TRUE_PEAK_NACHZIEHEN = False
            _, m = audio.normalize(self.signal())
            self.assertFalse(m["true_peak_begrenzt"])
        finally:
            audio.TRUE_PEAK_NACHZIEHEN = alt

    def test_eingeschaltet_haelt_er_die_grenze_ein(self):
        alt = audio.TRUE_PEAK_NACHZIEHEN
        try:
            audio.TRUE_PEAK_NACHZIEHEN = True
            _, m = audio.normalize(self.signal())
            self.assertLessEqual(m["true_peak_dbfs"],
                                 audio.TARGET_TRUE_PEAK + 0.01)
        finally:
            audio.TRUE_PEAK_NACHZIEHEN = alt

    def test_der_schalter_kostet_lautheit(self):
        """Genau der Grund, warum er aus ist. Faellt dieser Test, hat sich
        der Handel geaendert und die Entscheidung gehoert neu getroffen."""
        alt = audio.TRUE_PEAK_NACHZIEHEN
        try:
            audio.TRUE_PEAK_NACHZIEHEN = False
            _, aus_m = audio.normalize(self.signal())
            audio.TRUE_PEAK_NACHZIEHEN = True
            _, ein_m = audio.normalize(self.signal())
        finally:
            audio.TRUE_PEAK_NACHZIEHEN = alt
        self.assertLess(ein_m["lufs_nachher"], aus_m["lufs_nachher"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
