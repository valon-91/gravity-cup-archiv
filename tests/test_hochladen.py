"""Der Upload – alles, was sich ohne Netz pruefen laesst.

Der Upload selbst ist nicht testbar, ohne ein Video auf den Kanal zu legen.
Testbar ist alles davor: was hochgeladen WUERDE, und die Weigerungen.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from gravitycup.tools import hochladen as h


class TestTitelUndText(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def schreibe(self, inhalt):
        p = self.tmp / "folge.txt"
        p.write_text(inhalt, encoding="utf-8")
        return p

    def test_erste_zeile_ist_der_titel_der_rest_bleibt_dabei(self):
        """Die Beschreibung wird NICHT hier zusammengebaut – sie kommt
        fertig aus dem Rundenmanifest. Wer sie hier formatiert, schafft eine
        zweite Wahrheit neben dem Archiv."""
        titel, text = h.titel_und_text(
            self.schreibe("GRAVITY CUP · Season 1, Round 2\n\nWinner: RED\n"))
        self.assertEqual(titel, "GRAVITY CUP · Season 1, Round 2")
        self.assertIn("Winner: RED", text)
        self.assertTrue(text.startswith(titel))

    def test_zu_langer_titel_wird_abgelehnt(self):
        with self.assertRaises(SystemExit):
            h.titel_und_text(self.schreibe("X" * (h.TITEL_MAX + 1) + "\n"))

    def test_zu_lange_beschreibung_wird_abgelehnt(self):
        with self.assertRaises(SystemExit):
            h.titel_und_text(
                self.schreibe("Titel\n" + "y" * h.BESCHREIBUNG_MAX))

    def test_leere_erste_zeile_wird_abgelehnt(self):
        with self.assertRaises(SystemExit):
            h.titel_und_text(self.schreibe("\n\nText\n"))

    def test_spitze_klammern_werden_abgefangen(self):
        """YouTube weist das Formular sonst zurueck. `build` verhindert das
        bereits – dies ist der zweite Riegel, kurz vor dem Absenden."""
        with self.assertRaises(SystemExit):
            h.titel_und_text(self.schreibe("Titel\n\nRED > GOLD\n"))


class TestSchlagworte(unittest.TestCase):

    def test_hashtags_werden_zu_schlagworten(self):
        self.assertEqual(
            h.schlagworte("Text\n\n#marblerace #physics #shorts"),
            ["marblerace", "physics", "shorts"])

    def test_ohne_hashtags_keine_schlagworte(self):
        self.assertEqual(h.schlagworte("nur Text"), [])

    def test_einzelnes_rautenzeichen_zaehlt_nicht(self):
        self.assertEqual(h.schlagworte("a # b"), [])


class TestOffeneRunden(unittest.TestCase):
    """Welche Runde ist als naechste dran?"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.alt = h.ARCHIV
        h.ARCHIV = self.tmp

    def tearDown(self):
        h.ARCHIV = self.alt
        shutil.rmtree(self.tmp, ignore_errors=True)

    def schreibe(self, runde, youtube_id=None):
        m = {"runde": runde, "seed": 1, "disziplin": "descent",
             "codestand": {"sauber": True}}
        if youtube_id:
            m["youtube_id"] = youtube_id
        (self.tmp / f"{runde}.json").write_text(json.dumps(m),
                                                encoding="utf-8")

    def test_gesendete_runden_fallen_raus(self):
        self.schreibe("S01R01", "abc123")
        self.schreibe("S01R02")
        self.schreibe("S01R03")
        self.assertEqual(h.offene_runden(), ["S01R02", "S01R03"])

    def test_reihenfolge_ist_die_der_runden_nicht_die_des_dateisystems(self):
        for r in ("S01R10", "S01R02", "S02R01", "S01R09"):
            self.schreibe(r)
        self.assertEqual(h.offene_runden(),
                         ["S01R02", "S01R09", "S01R10", "S02R01"])

    def test_alles_gesendet_ergibt_leere_liste(self):
        self.schreibe("S01R01", "abc")
        self.assertEqual(h.offene_runden(), [])


class TestFesteEinstellungen(unittest.TestCase):
    """Zwei Dinge duerfen nicht konfigurierbar sein.

    Ein Fehler im Ablauf, der eine Folge zu frueh oeffentlich stellt,
    verraet den Saisonausgang – das ist nicht rueckholbar. Und „Fuer Kinder
    gemacht: Nein" ist der einzige Rechtspunkt, der ab dem ersten Upload
    gilt.
    """

    def test_nur_der_upload_bereich_wird_angefordert(self):
        self.assertEqual(h.SCOPES,
                         ["https://www.googleapis.com/auth/youtube.upload"])

    def test_quelltext_setzt_unlisted_und_kein_kinderinhalt(self):
        quelle = Path(h.__file__).read_text(encoding="utf-8")
        self.assertIn('"privacyStatus": "unlisted"', quelle)
        self.assertIn('"selfDeclaredMadeForKids": False', quelle)
        self.assertNotIn('"public"', quelle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
