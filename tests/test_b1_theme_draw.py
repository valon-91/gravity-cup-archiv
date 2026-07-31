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


class TestGrossfeld(unittest.TestCase):
    """Die Show laeuft mit groesserem Feld als die Saison (30.07.2026).

    Gemessen liegt der Kugel-Kugel-Anteil bei 5 Teilnehmern bei 11-16 %,
    bei 20 bei 46 % - und daran haengt, ob ein Rennen nach Gedraenge
    aussieht statt nach Gaensemarsch.
    """

    def test_kennungen_und_namen_sind_eindeutig(self):
        keys = [c.key for c in theme.GROSSFELD]
        namen = [c.name for c in theme.GROSSFELD]
        self.assertEqual(len(set(keys)), len(keys), "doppelte Kennung")
        self.assertEqual(len(set(namen)), len(namen), "doppelter Name")

    def test_stammbesetzung_steht_vorn(self):
        """Die Show soll wie GRAVITY CUP aussehen, nicht wie ein anderes
        Format."""
        self.assertEqual(theme.GROSSFELD[:len(theme.COMPETITORS)],
                         theme.COMPETITORS)

    def test_namen_passen_in_die_rangliste(self):
        for c in theme.GROSSFELD:
            self.assertLessEqual(len(c.name), theme.NAME_MAX, c.name)

    def test_zusatzfarben_verschlechtern_nichts(self):
        """Der Kern der Palettenpruefung.

        Die elf zusaetzlichen Farben sind ausgerechnet, nicht ausgesucht -
        ein erster Versuch nach Augenmass hatte GOLD/AMBER bei 108 und
        SAND/PEACH bei 55. Diese Pruefung haelt fest, dass das Grossfeld
        unter Rot-Gruen-Schwaeche nicht schlechter dasteht als die
        Stammbesetzung, die ohnehin schon laeuft.
        """
        stamm = theme.engste_paarung(theme.COMPETITORS)[0]
        for n in (8, 12, 16):
            d, a, b = theme.engste_paarung(theme.grossfeld(n))
            self.assertGreaterEqual(
                d, stamm - 0.01,
                f"{n} Teilnehmer: {a}/{b} liegen bei {d:.1f} und damit enger "
                f"als das schlechteste Paar der Stammbesetzung ({stamm:.1f})")

    def test_farbabstand_kennt_rot_gruen_schwaeche(self):
        """Ein sattes Rot und ein sattes Gruen sind normalsichtig weit
        auseinander und bei Deuteranopie fast dasselbe. Faellt diese
        Pruefung, misst `unterscheidbarkeit` nur noch Normalsicht."""
        rot, gruen = (220, 0, 0), (0, 190, 0)
        self.assertGreater(theme.farbabstand(rot, gruen), 300)
        self.assertLess(theme.unterscheidbarkeit(rot, gruen), 200)

    def test_grossfeld_grenzen(self):
        with self.assertRaises(ValueError):
            theme.grossfeld(1)
        with self.assertRaises(ValueError):
            theme.grossfeld(len(theme.GROSSFELD) + 1)

    def test_besetzung_annimmt_grosses_feld(self):
        original = theme.competitors()
        try:
            theme.set_competitors(theme.grossfeld(16))
            self.assertEqual(len(theme.competitors()), 16)
        finally:
            theme.set_competitors(original)

    def test_besetzung_lehnt_unbrauchbares_ab(self):
        original = theme.competitors()
        try:
            with self.assertRaises(ValueError):
                theme.set_competitors(theme.grossfeld(2)[:1])
            doppelt = (theme.GROSSFELD[0], theme.GROSSFELD[0])
            with self.assertRaises(ValueError):
                theme.set_competitors(doppelt)
        finally:
            theme.set_competitors(original)


class TestAusgabeformat(unittest.TestCase):
    """Hochformat fuer die Kurzfolgen, Vollbild fuer die Show (30.07.2026)."""

    def setUp(self):
        self.vorher = theme.FORMAT

    def tearDown(self):
        theme.set_format(self.vorher)

    def test_hochformat_ist_unveraendert(self):
        """S01 und S02 laufen damit – hier darf sich NICHTS aendern."""
        theme.set_format("hoch")
        self.assertEqual((theme.WIDTH, theme.HEIGHT), (1080, 1920))
        self.assertEqual(
            (theme.SAFE_TOP, theme.SAFE_BOTTOM, theme.SAFE_LEFT,
             theme.SAFE_RIGHT), (150, 420, 40, 190))
        self.assertEqual(theme.HOOK_ZONE, (210, 470))
        self.assertEqual(theme.OVERLAY_FLOOR, 520)

    def test_umschalten_wirkt_und_ist_umkehrbar(self):
        theme.set_format("quer")
        self.assertEqual((theme.WIDTH, theme.HEIGHT), (1920, 1080))
        theme.set_format("hoch")
        self.assertEqual((theme.WIDTH, theme.HEIGHT), (1080, 1920))

    def test_unbekanntes_format_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            theme.set_format("querformat")

    def test_bild_hat_die_richtige_groesse(self):
        for name, groesse in (("hoch", (1080, 1920)), ("quer", (1920, 1080))):
            theme.set_format(name)
            c = draw.Canvas(scale=1)
            c.grid()
            self.assertEqual(c.finish().size, groesse, name)

    def test_rangliste_passt_in_beide_formate(self):
        """Sieben Zeilen sind im Hochformat ein Viertel der Hoehe und im
        Vollbild fast die Haelfte – deshalb haengt die Zeilenzahl am
        Format und nicht an einer Konstante."""
        for name in ("hoch", "quer"):
            theme.set_format(name)
            hoehe = (theme.SAFE_TOP
                     + theme.HUD_ROW_HEIGHT * theme.HUD_MAX_ROWS
                     + theme.PANEL_PAD * 2)
            self.assertLess(hoehe, theme.HEIGHT / 2,
                            f"{name}: Rangliste ueber der halben Bildhoehe")

    def test_einblendungen_bleiben_in_der_sicheren_zone(self):
        for name in ("hoch", "quer"):
            theme.set_format(name)
            self.assertLess(theme.HOOK_ZONE[0], theme.HOOK_ZONE[1], name)
            self.assertGreaterEqual(theme.HOOK_ZONE[0], theme.SAFE_TOP, name)
            self.assertLessEqual(theme.HOOK_ZONE[1], theme.OVERLAY_FLOOR, name)
            self.assertLess(theme.OVERLAY_FLOOR, theme.HEIGHT / 2, name)
            self.assertLess(theme.SAFE_TOP + theme.SAFE_BOTTOM,
                            theme.HEIGHT / 2, name)

    def test_zeichnen_im_vollbild_laeuft_durch(self):
        theme.set_format("quer")
        c = draw.Canvas(scale=1)
        c.grid()
        c.hud_ranking(list(range(16)), comps=theme.feld(16))
        c.hook("Last one out.", "64 enter, one leaves")
        c.result_card([0, 1, 2, 3, 4], comps=theme.feld(16))
        self.assertEqual(c.finish().size, (1920, 1080))


class TestKennungen(unittest.TestCase):
    """Farbe plus Muster – die Kennungen der Show (30.07.2026).

    64 unterscheidbare FARBEN gibt es nicht; die Stammbesetzung hat unter
    Rot-Gruen-Schwaeche schon bei fuenf ein engstes Paar von 61,7. Mit
    Muster reichen sechzehn Farben fuer ueber hundert Kennungen.
    """

    def test_feld_ist_eindeutig(self):
        comps = theme.feld(100)
        self.assertEqual(len(set(c.key for c in comps)), len(comps))
        self.assertEqual(len(set(c.name for c in comps)), len(comps))

    def test_die_ersten_sechzehn_sind_die_vollen_farben(self):
        self.assertEqual(theme.feld(16), theme.grossfeld(16))

    def test_feld_reicht_fuer_hundert(self):
        """Ausgelegt auf den spaeteren Sprung von 64 auf 100."""
        self.assertGreaterEqual(theme.FELD_MAX, 100)

    def test_namen_passen_in_die_rangliste(self):
        for c in theme.feld(theme.FELD_MAX):
            self.assertLessEqual(len(c.name), theme.NAME_MAX, c.name)

    def test_musterfarbe_hebt_sich_ab(self):
        """Der Fehler, den die Messung gefunden hat.

        Der erste Entwurf hatte feste Musterfarben. SNOW ist
        (245,245,245) und die helle Musterfarbe ebenfalls – weisses Muster
        auf weisser Kugel, gemessener Bildabstand 0,0. Der Kontrast muss
        aus der Grundfarbe folgen.
        """
        stamm = theme.engste_paarung(theme.COMPETITORS)[0]
        for c in theme.feld(theme.FELD_MAX):
            if c.muster == "voll":
                continue
            d = theme.unterscheidbarkeit(c.color, c.color2)
            self.assertGreater(
                d, stamm,
                f"{c.name}: Muster hebt sich nur mit {d:.0f} von der "
                f"Grundfarbe ab")

    def test_jedes_muster_wird_wirklich_gezeichnet(self):
        """Ein Tippfehler im Musternamen wuerde still eine volle Kugel
        zeichnen, und zwei Teilnehmer waeren ununterscheidbar."""
        def bild(comp):
            c = draw.Canvas(scale=1)
            c.marble(comp, theme.WIDTH / 2, theme.HEIGHT / 2, angle=0.6)
            return c.finish().tobytes()

        grund = theme.GROSSFELD[0]
        voll = bild(grund)
        for muster in theme.MUSTER:
            if muster == "voll":
                continue
            variante = theme.Competitor(
                grund.key, grund.name, grund.color, muster,
                theme.kontrastfarbe(grund.color))
            self.assertNotEqual(
                bild(variante), voll,
                f"Muster {muster!r} aendert das Bild nicht – wird es "
                f"in Canvas.muster ueberhaupt behandelt?")

    def test_muster_dreht_sich_mit(self):
        """Die Rotationsmarke gibt es seit B1, damit sichtbar ist, dass
        wirklich gerollt wird. Ein aufgeklebtes Muster widerspraeche dem."""
        comp = theme.feld(32)[16]          # erste Ring-Variante
        self.assertNotEqual(comp.muster, "voll")
        drehend = [m for m in theme.MUSTER if m not in ("voll", "ring",
                                                        "doppelring")]
        for muster in drehend:
            variante = theme.Competitor(
                "x", "X", comp.color, muster, theme.kontrastfarbe(comp.color))

            def bild(winkel):
                c = draw.Canvas(scale=1)
                c.marble(variante, theme.WIDTH / 2, theme.HEIGHT / 2,
                         angle=winkel)
                return c.finish().tobytes()

            self.assertNotEqual(bild(0.0), bild(1.2),
                                f"Muster {muster!r} dreht sich nicht mit")

    def test_umbenennen_behaelt_das_muster(self):
        """Sonst faellt bei jedem Namenswechsel das Muster auf die Vorgabe
        zurueck und zwei Teilnehmer waeren ab da gleich."""
        original = theme.competitors()
        try:
            theme.set_competitors(theme.feld(32))
            neu = theme.rename([f"N{i}" for i in range(32)])
            self.assertEqual([c.muster for c in neu],
                             [c.muster for c in theme.feld(32)])
        finally:
            theme.set_competitors(original)


class TestRanglisteGrossesFeld(unittest.TestCase):
    def test_kleines_feld_bleibt_vollstaendig(self):
        z = draw.Canvas.hud_zeilen([0, 1, 2, 3, 4])
        self.assertEqual([r for r, _ in z], [0, 1, 2, 3, 4])
        self.assertTrue(all(i is not None for _, i in z))

    def test_grosses_feld_zeigt_kopf_und_fuss(self):
        """Der Fuss ist der wichtigere Teil.

        Bei der Eliminierung faellt die Entscheidung hinten - wer als
        Letzter am Tor ankommt, ist raus. Eine Liste, die nur die Spitze
        zeigt, blendet genau das aus, worum es in der Disziplin geht.
        """
        order = list(range(16))
        z = draw.Canvas.hud_zeilen(order)
        self.assertLessEqual(len(z), theme.HUD_MAX_ROWS)
        gezeigt = [i for _, i in z if i is not None]
        self.assertIn(order[0], gezeigt, "Fuehrender fehlt")
        self.assertIn(order[-1], gezeigt, "LETZTER fehlt - der entscheidet")
        luecke = [r for r, i in z if i is None]
        self.assertEqual(len(luecke), 1)
        self.assertEqual(luecke[0], len(order) - len(gezeigt))

    def test_rangliste_bleibt_in_der_sicheren_zone(self):
        hoehe = theme.HUD_ROW_HEIGHT * theme.HUD_MAX_ROWS + theme.PANEL_PAD * 2
        self.assertLess(theme.SAFE_TOP + hoehe, theme.HEIGHT / 2,
                        "Rangliste reicht ueber die halbe Bildhoehe")

    def test_zeichnen_mit_sechzehn_laeuft_durch(self):
        c = draw.Canvas(scale=1)
        c.hud_ranking(list(range(16)), comps=theme.grossfeld(16),
                      raus={14, 15})
        self.assertEqual(c.finish().size, (theme.WIDTH, theme.HEIGHT))


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
