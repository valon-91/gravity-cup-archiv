#!/usr/bin/env python3
"""
Tests fuer Baustein B1 (theme.py + draw.py).

Laeuft mit der Standardbibliothek, pytest ist nicht noetig:

    python -m unittest discover -s tests -v
    python tests/test_b1_theme_draw.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gravitycup.core import draw, theme  # noqa: E402


class TestTheme(unittest.TestCase):
    def test_schrift_wird_gefunden(self):
        pfad = theme.font_path()
        self.assertTrue(pfad.exists(), f"Schrift fehlt: {pfad}")

    def test_alle_groessen_ladbar(self):
        for key in theme.SIZES:
            f = theme.font(key)
            self.assertIsNotNone(f, f"Groesse {key} nicht ladbar")

    def test_unbekannte_groesse_faellt_auf(self):
        with self.assertRaises(KeyError):
            theme.font("gibtsnicht")

    def test_fuenf_teilnehmer_mit_eigener_farbe(self):
        self.assertEqual(len(theme.COMPETITORS), 5)
        farben = [c.color for c in theme.COMPETITORS]
        self.assertEqual(len(set(farben)), 5, "zwei Teilnehmer teilen sich eine Farbe")

    def test_farben_sind_auch_ohne_farbsehen_unterscheidbar(self):
        """Rund acht Prozent der maennlichen Zuschauer sehen Rot und Gruen
        gleich. Die Palette muss sich darum zusaetzlich in der Helligkeit
        unterscheiden, sonst ist die Rangliste fuer sie unlesbar."""
        def luminanz(c):
            r, g, b = (v / 255 for v in c)
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        werte = sorted(luminanz(c.color) for c in theme.COMPETITORS)
        abstaende = [b - a for a, b in zip(werte, werte[1:])]
        self.assertTrue(
            all(d > 0.02 for d in abstaende),
            f"zwei Farben sind fast gleich hell: {[round(w, 3) for w in werte]}",
        )

    def test_namen_wechseln_ohne_farbwechsel(self):
        original = theme.competitors()
        try:
            neu = theme.rename(["a", "bb", "ccc", "dddd", "eeeee"])
            self.assertEqual([c.name for c in neu], ["A", "BB", "CCC", "DDDD", "EEEEE"])
            self.assertEqual([c.color for c in neu], [c.color for c in original])
        finally:
            theme.set_competitors(original)

    def test_zu_lange_namen_werden_gekappt(self):
        original = theme.competitors()
        try:
            neu = theme.rename(["x" * 40] + ["b"] * 4)
            self.assertLessEqual(len(neu[0].name), theme.NAME_MAX)
        finally:
            theme.set_competitors(original)

    def test_falsche_anzahl_namen_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            theme.rename(["nur", "drei", "namen"])


class TestCamera(unittest.TestCase):
    def test_start_setzt_fuehrenden_auf_den_anker(self):
        cam = draw.Camera.start_at(5000.0)
        self.assertAlmostEqual(cam.to_screen(5000.0),
                               theme.HEIGHT * theme.CAMERA_ANCHOR, places=3)

    def test_folgt_traege_statt_zu_springen(self):
        cam = draw.Camera.start_at(1000.0)
        vorher = cam.top
        cam.follow(2000.0)
        self.assertGreater(cam.top, vorher)
        self.assertLess(cam.top, 2000.0 - theme.HEIGHT * theme.CAMERA_ANCHOR,
                        "Kamera springt sofort ans Ziel statt zu gleiten")

    def test_klemmung_am_streckenende(self):
        """Hinter dem Ziel darf die Kamera nicht ins Leere weiterfahren."""
        cam = draw.Camera(limit_bottom=3000.0)
        for _ in range(400):
            cam.follow(99999.0)
        self.assertLessEqual(cam.top, 3000.0 - theme.HEIGHT * 0.62 + 0.5)


class TestCanvas(unittest.TestCase):
    def test_ausgabegroesse_stimmt(self):
        c = draw.Canvas(scale=1)
        self.assertEqual(c.finish().size, (theme.WIDTH, theme.HEIGHT))

    def test_supersampling_liefert_dieselbe_ausgabegroesse(self):
        c = draw.Canvas(scale=2)
        self.assertEqual(c.image.size, (theme.WIDTH * 2, theme.HEIGHT * 2))
        self.assertEqual(c.finish().size, (theme.WIDTH, theme.HEIGHT))

    def test_gleiche_eingabe_gleiches_bild(self):
        """Determinismus auf Bildebene: zweimal dasselbe gezeichnet muss
        Pixel fuer Pixel gleich sein. (Ueber Pillow-Versionen hinweg gilt
        das nicht – siehe docs/baustein-b1.md.)"""
        def bauen():
            c = draw.Canvas(scale=1, camera=draw.Camera.start_at(1000.0))
            c.grid()
            c.track_segment(60, 900, 1000, 1150)
            c.peg(400, 1200)
            c.marble(theme.competitor(0), 500, 1000, 1.2,
                     [(490, 960), (494, 975)])
            c.hud_ranking([0, 1, 2, 3, 4])
            c.hook("Which color wins?", "real physics, no cuts")
            return c.finish().tobytes()

        self.assertEqual(bauen(), bauen())


class TestEinblendungen(unittest.TestCase):
    """Der teuerste Fehler des Prototyps war eine Einblendung, deren Text
    nicht in seinen Kasten passte. Diese Tests nageln das fest."""

    def setUp(self):
        self.c = draw.Canvas(scale=1)

    def _text_passt_in_kasten(self, titel, unterzeile=""):
        layout = self.c.hook_layout(titel, unterzeile)
        x1, y1, x2, y2 = layout["box"]
        for y, text, size_key in layout["lines"]:
            breite, hoehe = self.c.measure(text, size_key)
            links = theme.WIDTH / 2 - breite / 2
            rechts = theme.WIDTH / 2 + breite / 2
            self.assertGreaterEqual(links, x1, f"{text!r} ragt links heraus")
            self.assertLessEqual(rechts, x2, f"{text!r} ragt rechts heraus")
            self.assertGreaterEqual(y - hoehe / 2, y1, f"{text!r} ragt oben heraus")
            self.assertLessEqual(y + hoehe / 2, y2, f"{text!r} ragt unten heraus")

    def test_hook_zweizeilig_bleibt_im_kasten(self):
        self._text_passt_in_kasten("Which color wins?", "real physics, no cuts")

    def test_hook_einzeilig_bleibt_im_kasten(self):
        self._text_passt_in_kasten("Round 7", "elimination")

    def test_hook_sehr_lang_bleibt_im_kasten(self):
        self._text_passt_in_kasten(
            "Which one of these five colors will win the whole thing",
            "no script, no retakes, pure physics",
        )

    def test_hook_verdeckt_das_rennen_nicht(self):
        """Die Teilnehmer sitzen beim Ankerpunkt der Kamera. Steht der
        Aufhaenger dort, verdeckt er genau das, worum es geht."""
        layout = self.c.hook_layout("Which color wins?", "real physics, no cuts")
        unterkante = layout["box"][3]
        self.assertLessEqual(
            unterkante, theme.OVERLAY_FLOOR,
            "Der Aufhaenger reicht in den Bereich, in dem gefahren wird",
        )

    def test_rangliste_waechst_mit_langen_namen(self):
        """Ab Saison 2 kommen die Namen aus den Kommentaren."""
        original = theme.competitors()
        try:
            theme.set_competitors(theme.rename(
                ["THUNDERBOLT", "KATARZYNA", "MAXIMILIAN", "BO", "WOLFGANG"]))
            c = draw.Canvas(scale=1)
            c.hud_ranking([0, 1, 2, 3, 4])
            breiteste = max(c.measure(k.name, "hud_entry")[0]
                            for k in theme.competitors())
            self.assertLess(
                108 + breiteste + 28,
                theme.WIDTH - theme.SAFE_RIGHT,
                "Rangliste waechst unter die Bedienleiste von Shorts",
            )
        finally:
            theme.set_competitors(original)

    def test_einblendungen_bleiben_in_der_sicheren_zone(self):
        """Unten liegen bei Shorts Kanalname und Titel, rechts die Knopfleiste."""
        c = draw.Canvas(scale=1)
        layout = c.hook_layout("Which color wins?", "real physics, no cuts")
        self.assertGreaterEqual(layout["box"][1], theme.SAFE_TOP)

    def test_ergebniskarte_bleibt_ueber_der_bedienleiste(self):
        c = draw.Canvas(scale=1)
        c.result_card([0, 1, 2, 3, 4], points=[5, 4, 3, 2, 1])
        # Die Karte wird ab 520 aufgebaut; die Tabelle endet rechnerisch hier:
        unterkante = 520 + 280 + 78 * 5 + theme.PANEL_PAD * 2
        self.assertLess(
            unterkante, theme.HEIGHT - theme.SAFE_BOTTOM,
            "Die Ergebnistabelle laeuft in die Shorts-Bedienleiste",
        )


class TestFade(unittest.TestCase):
    def test_verlauf_einer_einblendung(self):
        self.assertEqual(draw.fade(0, 0, 10, 20, 10), 0)
        self.assertEqual(draw.fade(10, 0, 10, 20, 10), 255)
        self.assertEqual(draw.fade(25, 0, 10, 20, 10), 255)
        self.assertEqual(draw.fade(40, 0, 10, 20, 10), 0)
        self.assertEqual(draw.fade(99, 0, 10, 20, 10), 0)
        self.assertEqual(draw.fade(-5, 0, 10, 20, 10), 0)

    def test_alpha_bleibt_im_gueltigen_bereich(self):
        for f in range(-5, 60):
            a = draw.fade(f, 0, 10, 20, 10)
            self.assertGreaterEqual(a, 0)
            self.assertLessEqual(a, 255)


if __name__ == "__main__":
    unittest.main(verbosity=2)
