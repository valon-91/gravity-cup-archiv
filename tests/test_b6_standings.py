#!/usr/bin/env python3
"""
Tests fuer Baustein B6 (season/standings.py + season/card.py).

Der Punktestand IST das Produkt des Kanals – ein Rechenfehler hier faellt
niemandem auf und entwertet trotzdem jede Folge rueckwirkend. Deshalb
prueft dieser Satz vor allem die Faelle, in denen still falsch gerechnet
werden koennte: doppelte Runden, unvollstaendige Manifeste, Gleichstand.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gravitycup import build                                   # noqa: E402
from gravitycup.core import theme                              # noqa: E402
from gravitycup.disciplines import descent                     # noqa: E402
from gravitycup.season import card, standings                  # noqa: E402
from gravitycup.tools import make_branding                     # noqa: E402

N = len(theme.competitors())


def manifest(runde: str, reihenfolge: list[int], seed: int = 1) -> dict:
    return {
        "kanal": "GRAVITY CUP",
        "runde": runde,
        "disziplin": "descent",
        "seed": seed,
        "erzeugt": "2026-07-28T00:00:00+00:00",
        "ergebnis": {
            "reihenfolge": [theme.competitor(i).name for i in reihenfolge],
            "reihenfolge_index": reihenfolge,
        },
    }


def archiv(*runden: dict) -> tempfile.TemporaryDirectory:
    tmp = tempfile.TemporaryDirectory()
    for m in runden:
        (Path(tmp.name) / f"{m['runde']}.json").write_text(
            json.dumps(m), encoding="utf-8")
    return tmp


class TestPunkteschluessel(unittest.TestCase):
    def test_deckt_alle_plaetze_ab(self):
        self.assertGreaterEqual(len(standings.PUNKTE), N)

    def test_faellt_monoton(self):
        werte = standings.PUNKTE[:N]
        self.assertEqual(list(werte), sorted(werte, reverse=True))
        self.assertGreater(werte[0], werte[1],
                           "ein Sieg muss mehr wert sein als Platz zwei")

    def test_niemand_steht_auf_null(self):
        """Auch der Letzte nimmt etwas mit – sonst faellt er aus der Tabelle."""
        self.assertGreater(standings.PUNKTE[N - 1], 0)

    def test_sieg_hebt_sich_deutlich_ab(self):
        """Der Kanal fragt „Which color wins?" – dann muss ein Sieg zaehlen.

        Bei 5-4-3-2-1 waere ein Sieg genau einen Punkt mehr wert als Platz
        zwei; das entwertet die Frage, mit der jedes Video anfaengt.
        """
        erster, zweiter = standings.PUNKTE[0], standings.PUNKTE[1]
        self.assertGreaterEqual(erster, zweiter * 1.4,
                                f"{erster} gegen {zweiter} ist zu wenig Abstand")


class TestArchivLesen(unittest.TestCase):
    def test_normale_runde(self):
        with archiv(manifest("S01R01", [4, 1, 0, 3, 2])) as d:
            runden = standings.lade_runden(Path(d))
        self.assertEqual(len(runden), 1)
        self.assertEqual(runden[0].saison, 1)
        self.assertEqual(runden[0].nummer, 1)
        self.assertEqual(runden[0].sieger, 4)

    def test_reihenfolge_nach_saison_und_nummer(self):
        with archiv(manifest("S01R10", list(range(N))),
                    manifest("S01R02", list(range(N))),
                    manifest("S02R01", list(range(N)))) as d:
            runden = standings.lade_runden(Path(d))
        self.assertEqual([r.name for r in runden], ["S01R02", "S01R10", "S02R01"])

    def test_saison_filtert(self):
        with archiv(manifest("S01R01", list(range(N))),
                    manifest("S02R01", list(range(N)))) as d:
            self.assertEqual(len(standings.lade_runden(Path(d), saison=2)), 1)

    def test_probelauf_ohne_runde_zaehlt_nicht(self):
        """`--runde` weggelassen heisst: das war ein Test, keine Folge."""
        m = manifest("S01R01", list(range(N)))
        m["runde"] = None
        with archiv(manifest("S01R02", list(range(N)))) as d:
            (Path(d) / "probe.json").write_text(json.dumps(m), encoding="utf-8")
            runden = standings.lade_runden(Path(d))
        self.assertEqual([r.name for r in runden], ["S01R02"])

    def test_doppelte_runde_bricht_ab(self):
        """Sonst zaehlt eine Folge zweimal, und niemand sieht es."""
        a = manifest("S01R01", list(range(N)))
        with archiv(a) as d:
            (Path(d) / "kopie.json").write_text(json.dumps(a), encoding="utf-8")
            with self.assertRaises(standings.ArchivFehler) as ctx:
                standings.lade_runden(Path(d))
        self.assertIn("zweimal", str(ctx.exception))

    def test_unvollstaendige_rangfolge_bricht_ab(self):
        m = manifest("S01R01", [0, 1, 2])
        with archiv(m) as d:
            with self.assertRaises(standings.ArchivFehler):
                standings.lade_runden(Path(d))

    def test_rangfolge_mit_doppeltem_teilnehmer_bricht_ab(self):
        m = manifest("S01R01", [0, 0, 1, 2, 3])
        with archiv(m) as d:
            with self.assertRaises(standings.ArchivFehler):
                standings.lade_runden(Path(d))

    def test_fehlendes_ergebnis_bricht_ab(self):
        m = manifest("S01R01", list(range(N)))
        del m["ergebnis"]["reihenfolge_index"]
        with archiv(m) as d:
            with self.assertRaises(standings.ArchivFehler):
                standings.lade_runden(Path(d))

    def test_krumme_rundenbezeichnung_bricht_ab(self):
        with archiv(manifest("Folge-3", list(range(N)))) as d:
            with self.assertRaises(standings.ArchivFehler):
                standings.lade_runden(Path(d))

    def test_kaputtes_json_bricht_ab(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "S01R01.json").write_text("{kaputt", encoding="utf-8")
            with self.assertRaises(standings.ArchivFehler):
                standings.lade_runden(Path(d))

    def test_leeres_archiv_ist_kein_fehler(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(standings.lade_runden(Path(d)), [])
        self.assertEqual(standings.lade_runden(Path("gibtsnicht")), [])


class TestRechnung(unittest.TestCase):
    def test_punkte_stimmen(self):
        with archiv(manifest("S01R01", [0, 1, 2, 3, 4]),
                    manifest("S01R02", [1, 0, 2, 3, 4])) as d:
            tabelle = standings.berechne(standings.lade_runden(Path(d)))
        nach_index = {e.teilnehmer: e for e in tabelle}
        p = standings.PUNKTE
        self.assertEqual(nach_index[0].punkte, p[0] + p[1])
        self.assertEqual(nach_index[1].punkte, p[1] + p[0])
        self.assertEqual(nach_index[4].punkte, p[4] * 2)

    def test_plaetze_werden_gezaehlt(self):
        with archiv(manifest("S01R01", [0, 1, 2, 3, 4]),
                    manifest("S01R02", [0, 2, 1, 3, 4])) as d:
            tabelle = standings.berechne(standings.lade_runden(Path(d)))
        sieger = next(e for e in tabelle if e.teilnehmer == 0)
        self.assertEqual(sieger.siege, 2)
        self.assertEqual(sieger.plaetze[0], 2)
        self.assertEqual(sieger.runden, 2)

    def test_alle_teilnehmer_stehen_in_der_tabelle(self):
        """Auch wer nie gefahren ist – sonst fehlt jemand ohne Erklaerung."""
        with archiv(manifest("S01R01", list(range(N)))) as d:
            tabelle = standings.berechne(standings.lade_runden(Path(d)))
        self.assertEqual(sorted(e.teilnehmer for e in tabelle), list(range(N)))

    def test_ohne_runden_stehen_alle_auf_null(self):
        tabelle = standings.berechne([])
        self.assertTrue(all(e.punkte == 0 and e.runden == 0 for e in tabelle))


class TestGleichstand(unittest.TestCase):
    """In 8 % der gemessenen Saisons entscheidet diese Regel den Saisonsieg."""

    def test_mehr_siege_gewinnt_bei_punktgleichheit(self):
        """Ein Sieger und zwei letzte Plaetze gegen drei mittlere Plaetze.

        Beide kommen auf dieselbe Punktzahl. Wer gewonnen hat, steht vorn –
        sonst waere die Frage „welche Farbe gewinnt?" fuer die Tabelle
        bedeutungslos.
        """
        with archiv(manifest("S01R01", [0, 1, 2, 3, 4]),      # 0: 1., 1: 2.
                    manifest("S01R02", [2, 3, 1, 4, 0]),      # 0: 5., 1: 3.
                    manifest("S01R03", [2, 3, 4, 1, 0])) as d:  # 0: 5., 1: 4.
            tabelle = standings.berechne(standings.lade_runden(Path(d)))
        nach_index = {e.teilnehmer: e for e in tabelle}
        self.assertEqual(nach_index[0].punkte, nach_index[1].punkte,
                         "Testaufbau erzeugt keinen Punktgleichstand mehr")
        self.assertEqual(nach_index[0].siege, 1)
        self.assertEqual(nach_index[1].siege, 0)
        self.assertLess([e.teilnehmer for e in tabelle].index(0),
                        [e.teilnehmer for e in tabelle].index(1),
                        "bei Punktgleichheit muss der Sieg entscheiden")

    def test_punktgleichheit_wird_gemeldet(self):
        with archiv(manifest("S01R01", [0, 1, 2, 3, 4]),
                    manifest("S01R02", [1, 0, 2, 3, 4])) as d:
            tabelle = standings.berechne(standings.lade_runden(Path(d)))
        self.assertTrue(standings.punktgleich_an_der_spitze(tabelle))
        self.assertEqual(tabelle[0].punkte, tabelle[1].punkte)

    def test_es_gibt_immer_einen_ersten(self):
        """Nicht selbstverstaendlich, deshalb festgenagelt.

        In einer Runde belegen nie zwei Teilnehmer denselben Platz. Damit
        unterscheiden sich zwei Eintraege spaetestens im `letzter_platz` –
        die Tabelle kann also nach einer gelaufenen Runde nie mehrdeutig
        sein, egal wie knapp es nach Punkten steht.
        """
        with archiv(manifest("S01R01", [0, 1, 2, 3, 4]),
                    manifest("S01R02", [1, 0, 2, 3, 4])) as d:
            tabelle = standings.berechne(standings.lade_runden(Path(d)))
        schluessel = [standings.sortierschluessel(e) for e in tabelle]
        self.assertEqual(len(set(schluessel)), len(tabelle),
                         "zwei Eintraege sind nicht unterscheidbar")
        # Wer die juengste Runde gewonnen hat, steht vorn.
        self.assertEqual(tabelle[0].teilnehmer, 1)

    def test_startnummer_entscheidet_nicht(self):
        """Derselbe Grundsatz wie beim Zieleinlauf in B2.

        Kaeme die Startnummer als letztes Kriterium zum Zug, gaebe es einen
        Vorteil, den niemand erlaufen hat – und die Tabelle waere genau das,
        was der Kanal nicht sein will.
        """
        a = standings.Eintrag(teilnehmer=0, punkte=10, runden=1,
                              plaetze=[1, 0, 0, 0, 0], letzter_platz=0)
        b = standings.Eintrag(teilnehmer=4, punkte=10, runden=1,
                              plaetze=[1, 0, 0, 0, 0], letzter_platz=0)
        self.assertEqual(standings.sortierschluessel(a),
                         standings.sortierschluessel(b))

    def test_juengste_runde_bricht_den_gleichstand(self):
        a = standings.Eintrag(teilnehmer=0, punkte=10, runden=2,
                              plaetze=[1, 0, 0, 0, 1], letzter_platz=0)
        b = standings.Eintrag(teilnehmer=1, punkte=10, runden=2,
                              plaetze=[1, 0, 0, 0, 1], letzter_platz=4)
        self.assertLess(standings.sortierschluessel(a),
                        standings.sortierschluessel(b))


class TestMomentaufnahme(unittest.TestCase):
    def test_ist_json_und_nennt_die_quelle(self):
        with archiv(manifest("S01R01", list(range(N)))) as d:
            runden = standings.lade_runden(Path(d))
        tabelle = standings.berechne(runden)
        daten = standings.als_dict(tabelle, runden, saison=1)
        json.dumps(daten, ensure_ascii=False)
        self.assertIn("runs/*.json", daten["quelle"])
        self.assertEqual(daten["punkteschluessel"], list(standings.PUNKTE))
        self.assertEqual(len(daten["tabelle"]), N)
        self.assertEqual(daten["tabelle"][0]["platz"], 1)


class TestGrafik(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with archiv(manifest("S01R01", [4, 1, 0, 3, 2]),
                    manifest("S01R02", [1, 4, 2, 0, 3])) as d:
            cls.runden = standings.lade_runden(Path(d))
        cls.tabelle = standings.berechne(cls.runden)

    def test_videoformat(self):
        bild = card.videokarte(self.tabelle, 1, len(self.runden), scale=1)
        self.assertEqual(bild.size, (theme.WIDTH, theme.HEIGHT))

    def test_bannerformat(self):
        bild = card.bannerkarte(self.tabelle, 1)
        self.assertEqual(bild.size,
                         (make_branding.BANNER_W, make_branding.BANNER_H))

    def _banner_aufruf(self, tabelle, saison=1, runden=None):
        """Banner zeichnen und mitschreiben, womit es gefuettert wurde."""
        gerufen = {}
        echt = make_branding.banner

        def merken(standings=None, season=None, rang=None, runden=None):
            gerufen.update(punkte=standings, rang=rang, runden=runden)
            return echt(standings, season, rang, runden)

        make_branding.banner = merken
        try:
            card.bannerkarte(tabelle, saison, runden)
        finally:
            make_branding.banner = echt
        return gerufen

    def test_banner_bekommt_die_punkte_nach_startnummer(self):
        """Das Banner indiziert nach Teilnehmer, die Tabelle nach Platz.

        Wer das verwechselt, zeigt im Banner die richtigen Zahlen bei den
        falschen Farben – und das faellt erst auf, wenn es online steht.
        """
        gerufen = self._banner_aufruf(self.tabelle)
        erwartet = [0] * N
        for e in self.tabelle:
            erwartet[e.teilnehmer] = e.punkte
        self.assertEqual(gerufen["punkte"], erwartet)

    def test_banner_uebernimmt_die_reihenfolge_der_tabelle(self):
        """DER Fehler, den die Pruefung gefunden hat.

        Vorher bekam das Banner nur die Punkte und sortierte selbst. Ein
        stabiler Sort allein nach Punkten laesst bei Gleichstand die
        kleinere Startnummer vorn – genau das Kriterium, das
        `sortierschluessel` ausschliesst. Gemessen: die Videokarte nannte
        GOLD als Fuehrenden, das Banner RED. Ohne Fehlermeldung, auf dem
        oeffentlichsten Stueck des Kanals.
        """
        # Zwei Runden, gespiegelt: Teilnehmer 0 und 1 stehen punktgleich,
        # aber 1 hat die juengste Runde gewonnen und fuehrt damit.
        with archiv(manifest("S01R01", [0, 1, 2, 3, 4]),
                    manifest("S01R02", [1, 0, 2, 3, 4])) as d:
            tabelle = standings.berechne(standings.lade_runden(Path(d)))
        self.assertEqual(tabelle[0].punkte, tabelle[1].punkte,
                         "Testaufbau erzeugt keinen Punktgleichstand")
        self.assertEqual(tabelle[0].teilnehmer, 1)

        gerufen = self._banner_aufruf(tabelle)
        self.assertEqual(gerufen["rang"], [e.teilnehmer for e in tabelle],
                         "Banner bekommt die Tabellenreihenfolge nicht")
        # Und das Banner darf sie auch nicht wieder verwerfen:
        nur_punkte = sorted(range(N), key=lambda i: -gerufen["punkte"][i])
        self.assertNotEqual(
            nur_punkte, gerufen["rang"],
            "Testaufbau taugt nicht – Punktsortierung und Tabelle sind gleich")

    def test_banner_nennt_die_rundenzahl(self):
        gerufen = self._banner_aufruf(self.tabelle, runden=len(self.runden))
        self.assertEqual(gerufen["runden"], len(self.runden))


class TestHinweise(unittest.TestCase):
    """Faelle, in denen die Tabelle richtig rechnet und trotzdem erklaert
    gehoert. Ein Abbruch waere falsch – Schweigen aber auch."""

    def test_luecke_in_der_nummerierung(self):
        with archiv(manifest("S01R01", list(range(N))),
                    manifest("S01R02", list(range(N))),
                    manifest("S01R04", list(range(N)))) as d:
            runden = standings.lade_runden(Path(d))
        text = " ".join(standings.hinweise(runden))
        self.assertIn("R03", text)

    def test_luecke_wird_nicht_erfunden(self):
        with archiv(manifest("S01R01", list(range(N))),
                    manifest("S01R02", list(range(N)))) as d:
            runden = standings.lade_runden(Path(d))
        self.assertEqual(standings.hinweise(runden), [])

    def test_mit_trotzdem_gebaute_runde_wird_gemeldet(self):
        m = manifest("S01R01", list(range(N)))
        m["annahme"] = ["nicht im Ziel: JADE – Rennen wirkt unfertig"]
        with archiv(m) as d:
            runden = standings.lade_runden(Path(d))
        text = " ".join(standings.hinweise(runden))
        self.assertIn("trotz Maengeln", text)

    def test_nachtraeglich_geaenderter_schluessel_wird_gemeldet(self):
        """Sonst schreibt eine Zeile Code jede veroeffentlichte Tabelle um."""
        m = manifest("S01R01", list(range(N)))
        m["punkteschluessel"] = [5, 4, 3, 2, 1]
        with archiv(m) as d:
            runden = standings.lade_runden(Path(d))
        text = " ".join(standings.hinweise(runden))
        self.assertIn("5-4-3-2-1", text)

    def test_gleicher_schluessel_meldet_nichts(self):
        m = manifest("S01R01", list(range(N)))
        m["punkteschluessel"] = list(standings.PUNKTE)
        with archiv(m) as d:
            runden = standings.lade_runden(Path(d))
        self.assertEqual(standings.hinweise(runden), [])


class TestSaisontrennung(unittest.TestCase):
    def test_card_mischt_die_saisons_nicht(self):
        """Vorher: ohne --saison wurde alles summiert und als „SEASON 2"
        beschriftet – die Grafik wich von `standings --saison 2` ab."""
        import io
        import contextlib

        with archiv(manifest("S01R01", [0, 1, 2, 3, 4]),
                    manifest("S01R02", [0, 1, 2, 3, 4]),
                    manifest("S02R01", [4, 3, 2, 1, 0])) as d:
            with tempfile.TemporaryDirectory() as out:
                argv = sys.argv
                sys.argv = ["card", "--archiv", d, "--out", out,
                            "--supersample", "1"]
                try:
                    with contextlib.redirect_stdout(io.StringIO()) as puffer:
                        self.assertEqual(card.main(), 0)
                finally:
                    sys.argv = argv
                self.assertTrue((Path(out) / "tabelle-S02-video.png").exists())

            # Die gezeichnete Tabelle muss der von Saison 2 entsprechen.
            nur_s2 = standings.berechne(standings.lade_runden(Path(d), saison=2))
        ausgabe = puffer.getvalue()
        self.assertIn("Saison 2, 1 Runden", ausgabe)
        for e in nur_s2:
            self.assertIn(f"{e.name:<8} {e.punkte:>3}", ausgabe)
        # Teilnehmer 4 gewinnt Saison 2, Teilnehmer 0 die Allzeitwertung.
        self.assertEqual(nur_s2[0].teilnehmer, 4)


class TestSichereZone(unittest.TestCase):
    def test_tabelle_bleibt_unter_der_shorts_leiste(self):
        """Rechts ist die sichere Zone breiter als links (Knopfleiste).

        Eine symmetrische Tabelle ragte 104 px darunter, die Punktzahlen
        58 px – ausgerechnet die Spalte, auf die es ankommt.
        """
        self.assertLessEqual(card.rand_rechts(), theme.WIDTH - theme.SAFE_RIGHT)
        self.assertGreaterEqual(card.rand(), theme.SAFE_LEFT)

    def test_tabelle_folgt_dem_ausgabeformat(self):
        """Die Raender waren bis zum 30.07.2026 Modulkonstanten und froren
        `theme.WIDTH` beim Import ein. Im Vollbild waere die Tabelle danach
        weiterhin 1080 px breit gewesen, mit den Raendern des Hochformats.
        """
        vorher = theme.FORMAT
        try:
            theme.set_format("quer")
            self.assertLessEqual(card.rand_rechts(),
                                 theme.WIDTH - theme.SAFE_RIGHT)
            self.assertGreater(card.rand_rechts(), theme.HOCH.width,
                               "Tabelle nutzt die Vollbildbreite nicht")
        finally:
            theme.set_format(vorher)

    def test_tabelle_passt_in_die_hoehe(self):
        hoehe = card.ZEILE * N + theme.PANEL_PAD * 2
        unterkante = card.TABELLE_OBEN + hoehe + 92 + 52
        self.assertLess(unterkante, theme.HEIGHT - theme.SAFE_BOTTOM,
                        "Fusszeile liegt unter der Shorts-Bedienleiste")
        self.assertGreater(card.TABELLE_OBEN, theme.SAFE_TOP)


class TestVideoAnbindung(unittest.TestCase):
    def test_rundenmarke(self):
        self.assertEqual(build._rundenmarke("S01R01"), "S01 · R01")
        self.assertEqual(build._rundenmarke("s2r13"), "S02 · R13")
        self.assertIsNone(build._rundenmarke(None))
        self.assertEqual(build._rundenmarke("probe"), "PROBE")

    def test_endkarte_bekommt_den_schluessel(self):
        self.assertEqual(standings.punkte_je_platz(), list(standings.PUNKTE))
        self.assertIsNot(standings.punkte_je_platz(), standings.PUNKTE,
                         "Kopie zurueckgeben, nicht den Schluessel selbst")

    def test_krumme_rundenbezeichnung_wird_beim_bauen_abgelehnt(self):
        """Sonst legt EIN verschriebener Name die ganze Tabelle stumm.

        `standings.lade_runden()` bricht ueber dem gesamten Archiv ab, wenn
        eine einzige Datei nicht auf SxxRyy passt. Der Fehler gehoert also
        dorthin, wo er entsteht.
        """
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit) as ctx:
                build.bauen(descent, 1, Path(d) / "x.mp4", scale=1,
                            runde="Folge 3", cache_nutzen=False,
                            archiv=False, leise=True)
            self.assertIn("SxxRyy", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
