#!/usr/bin/env python3
"""
Tests fuer Disziplin 5 (gauntlet.py) – die Langform-Show, Fassung 2.

Konstruktionsebene: ein voller Lauf kostet ~40 s und gehoert nicht in
die Testsuite. Was hier steht, sind die Masse und Kopplungen, an denen
die Vorgaenger nachweislich gestorben sind – Verklemmungsbereich,
Feld-Luecken, Leiter-Enden.

    python -m unittest tests.test_gauntlet -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gravitycup.core import physics, theme                     # noqa: E402
from gravitycup.disciplines import gauntlet                    # noqa: E402

MARBLE_D = 2 * theme.MARBLE_RADIUS


class TestLeiter(unittest.TestCase):
    def test_endet_bei_eins(self):
        for n in (2, 5, 20, 100, 112):
            stufen = gauntlet.leiter(n)
            self.assertEqual(stufen[-1], 1, f"Leiter fuer {n} endet nicht")

    def test_faellt_streng(self):
        stufen = gauntlet.leiter(112)
        for a, b in zip([112] + stufen, stufen):
            self.assertGreater(a, b)

    def test_massenschnitte_vorn_duelle_hinten(self):
        """Der Kern von Valons Konzeptwahl: vorn faellt ein ANTEIL."""
        stufen = gauntlet.leiter(112)
        self.assertGreaterEqual(112 - stufen[0], 5,
                                "erste Kammer muss ein Massenschnitt sein")
        self.assertEqual(stufen[-2] - stufen[-1], 1,
                         "das Finale muss ein Duell sein")


class TestBauart(unittest.TestCase):
    def test_verklemmungsbereich_wird_abgelehnt(self):
        """Unter fuenf Kugelbreiten woelbt der Pulk einen Bogen –
        gemessen am 31.07. (seed 7) und am 03.08. (Konzept-Messreihe)."""
        with self.assertRaises(ValueError):
            gauntlet.Bauart(ausgang_kugeln_min=4.0).pruefen()

    def test_ausgang_nie_unter_minimum(self):
        b = gauntlet.VORGABE
        for drin in (2, 5, 20, 60, 112):
            self.assertGreaterEqual(
                b.ausgang(drin, 112),
                b.ausgang_kugeln_min * MARBLE_D - 1e-9)


class TestGeometrie(unittest.TestCase):
    def test_track_baut_und_tore_passen(self):
        vorher = theme.competitors()
        theme.set_format("quer")
        theme.set_competitors(theme.feld(112))
        try:
            formen = gauntlet.kammerformen(112)
            track = gauntlet.build_track(3, 112)
        finally:
            theme.set_competitors(vorher)
            theme.set_format("hoch")
        self.assertEqual(len(track.tore), len(formen),
                         "je Kammer genau eine Sperre")
        self.assertEqual(len(track.starts), 112)
        # Jede Sperre liegt unter ihrer Kammer und deckt den Ausgang.
        for form, tor in zip(formen, track.tore):
            s = tor[0]
            self.assertGreater(s.y1, form.unten)
            self.assertGreaterEqual(abs(s.x2 - s.x1),
                                    form.ausgang,
                                    f"Sperre {form.nummer} zu kurz")

    def test_wuehlzeit_skaliert_mit_dem_feld(self):
        """Fester Timer je Kammer war in der Arena ein Ladebildschirm –
        die Wuehlzeit muss mit dem Feld auf null fallen."""
        formen = gauntlet.kammerformen(112)
        regel = gauntlet.KammernMitRuhe(
            formen, 99999.0,
            ruhe=[12.0 * (f.weiter / 112) for f in formen])
        regel.vorbereiten(112)
        regel.kammer = 0
        frueh = regel.halt_beat
        regel.kammer = len(formen) - 1
        spaet = regel.halt_beat
        self.assertGreater(frueh, spaet + 5.0)
        self.assertLess(spaet, 2.0)


class TestEndkarte(unittest.TestCase):
    """Die Endkarte lief mit 112 Zeilen 8 000 px aus dem Bild – die
    letzte sichtbare Zeile endete mitten im Buchstaben (SHOW-02,
    03.08.2026). Dieselbe Klasse wie die 108-px-Namensspalte."""

    def test_112_zeilen_passen_ins_vollbild(self):
        from gravitycup.core.draw import Canvas
        gezeigt, gekuerzt = Canvas.endkarte_zeilen(112, 604.0, 78.0, 1080.0)
        self.assertTrue(gekuerzt)
        unterkante = 604.0 + 78.0 * (gezeigt + 1) + 2 * theme.PANEL_PAD
        self.assertLessEqual(unterkante, 1080.0)
        self.assertGreaterEqual(gezeigt, 2, "Sieger und Zweiter muessen stehen")

    def test_fuenfer_karte_bleibt_ungekappt(self):
        """Die Kurzfolgen (Hochformat, 5 Teilnehmer) muessen pixelgleich
        bleiben – dort hat die Kappung nichts zu suchen."""
        from gravitycup.core.draw import Canvas
        gezeigt, gekuerzt = Canvas.endkarte_zeilen(5, 800.0, 78.0, 1920.0)
        self.assertEqual((gezeigt, gekuerzt), (5, False))


class TestVorlauf(unittest.TestCase):
    """Was ein Zuschauer in Sekunde 0 sieht.

    SHOW-02 stellte 8,6 s Tafeln vor das erste Bild des Rennens. Gemessen
    nach acht Tagen (12.08.2026): 8 755 Aufrufe, durchschnittlich gesehen
    0:05, Bindung 1,6 %. Der mittlere Zuschauer stieg 3,6 s aus, BEVOR
    das Rennen begann – 98,4 % haben nie eine Kugel rollen sehen.

    Dieselben Kugeln, dieselbe Physik, derselbe Ton halten in den
    Kurzfolgen 43–71 %, und die zeigen ab Bild 1 das Feld mit dem
    Aufhaenger DARUEBER.

    Keiner der 347 Tests sah das: gemessen wurde die Simulation, das
    Bild und der Ton – nie, was in Sekunde 0 auf dem Schirm steht.
    """

    def test_show_beginnt_mit_dem_rennen(self):
        from gravitycup.tools import show
        self.assertFalse(
            show.VORSPANN,
            "Die Show muss mit dem Rennen beginnen, nicht mit Tafeln "
            "(Begruendung und Messung: show.VORSPANN)")

    def test_vorlauf_bleibt_unter_der_entscheidungszeit(self):
        """Der Waechter, falls der Vorspann je wieder eingeschaltet wird.

        Die Grenze ist nicht gewaehlt, sondern die im Projekt bereits
        gemessene: die Kurzfolgen bringen dieselbe Information in
        HOOK_ENDE Bildern unter – ueber dem laufenden Rennen statt davor,
        und halten damit bis 70,7 %.
        """
        from gravitycup import build
        from gravitycup.tools import karten, show
        if not show.VORSPANN:
            self.skipTest("Vorspann ist aus – der Fall kann nicht eintreten")
        vorlauf = karten.vorspann_bilder(theme.FPS) / theme.FPS
        grenze = build.HOOK_ENDE / theme.FPS
        self.assertLessEqual(
            vorlauf, grenze,
            f"{vorlauf:.1f} s ohne Rennen vor einem Video, dessen "
            f"Zuschauer im Schnitt nach 5 s weg sind")


if __name__ == "__main__":
    unittest.main(verbosity=2)
