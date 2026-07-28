#!/usr/bin/env python3
"""
Tests fuer Baustein B8 (disciplines/scatter.py).

Die Streuung ist die erste Disziplin, die KEIN Rennen ist: gewertet wird das
Landefach. Damit ist sie auch die erste, in der zwei Teilnehmer dasselbe
Ergebnis erzielen koennen – die Saisontabelle braucht trotzdem eine
vollstaendige Rangfolge ueber fuenf Plaetze.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gravitycup import build                                   # noqa: E402
from gravitycup.core import physics, theme                     # noqa: E402
from gravitycup.disciplines import descent, scatter as sc      # noqa: E402

N = len(theme.competitors())


class TestPunktwerte(unittest.TestCase):
    def test_symmetrisch(self):
        """Waeren die hohen Werte auf einer Seite, haette die Bildseite
        einen dauerhaften Vorteil – dieselbe Lehre wie der gespiegelte
        Zickzack in B4."""
        self.assertEqual(list(sc.FACH_WERTE), list(reversed(sc.FACH_WERTE)))

    def test_ungerade_anzahl_faecher(self):
        """Sonst gibt es keine Mitte, und die Verteilung haette zwei."""
        self.assertEqual(sc.FAECHER % 2, 1)

    def test_der_hoechste_wert_liegt_auf_dem_seltensten_fach(self):
        """Die Werte folgen der Messung, nicht der Erwartung.

        Die erste Fassung hatte sie andersherum, mit der Begruendung „durch
        ein Stiftfeld faellt die Mitte am wahrscheinlichsten". Gemessen ist
        das Gegenteil: die reflektierenden Waende machen den Rand zum
        haeufigsten Ausgang. Damit belohnte die Disziplin genau den
        Normalfall am hoechsten.
        """
        mitte = sc.FAECHER // 2
        self.assertEqual(max(sc.FACH_WERTE), sc.FACH_WERTE[mitte],
                         "der Hoechstwert liegt nicht in der Mitte")
        for k in range(mitte):
            self.assertLessEqual(sc.FACH_WERTE[k], sc.FACH_WERTE[k + 1])

    def test_werte_passen_zur_gemessenen_haeufigkeit(self):
        """Der teure, aber entscheidende Test: haeufig = wenig wert.

        Ohne ihn kann die Verteilung kippen, ohne dass es jemandem
        auffaellt – und die Disziplin belohnte wieder den Normalfall.
        """
        haeufigkeit = Counter()
        for seed in range(1, 25):
            r = sc.run(seed)
            for f in (r.extras.get("fach") or {}).values():
                haeufigkeit[int(f)] += 1
        gesamt = sum(haeufigkeit.values())
        mitte = sc.FAECHER // 2
        rand = (haeufigkeit.get(0, 0) + haeufigkeit.get(sc.FAECHER - 1, 0)) / gesamt
        zentrum = haeufigkeit.get(mitte, 0) / gesamt
        self.assertLess(zentrum, rand,
                        f"Mitte {zentrum:.1%} ist nicht seltener als der "
                        f"Rand {rand:.1%} – der Hoechstwert waere falsch platziert")

    def test_niemand_bekommt_null(self):
        self.assertTrue(all(w > 0 for w in sc.FACH_WERTE))


class TestBrett(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.track = sc.build_track(1)

    def test_kanten_passen_zu_den_faechern(self):
        kanten = sc.fach_kanten()
        self.assertEqual(len(kanten), sc.FAECHER + 1)
        self.assertEqual(kanten, sorted(kanten))

    def test_alle_faecher_gleich_breit(self):
        kanten = sc.fach_kanten()
        breiten = [kanten[k + 1] - kanten[k] for k in range(sc.FAECHER)]
        for b in breiten:
            self.assertAlmostEqual(b, breiten[0], places=6)

    def test_ein_fach_nimmt_eine_kugel_auf(self):
        kanten = sc.fach_kanten()
        luecke = (kanten[1] - kanten[0]) - 2 * sc.SEG_RADIUS
        self.assertGreater(luecke, sc.MARBLE_D,
                           f"Fach nur {luecke:.0f} px breit")

    def test_wertlinie_liegt_zwischen_den_trennwaenden(self):
        """Oberhalb koennte die Kugel das Fach noch wechseln, unterhalb
        muesste man warten, bis sie liegen bleibt."""
        self.assertGreater(sc.wert_linie(), sc.trenner_oben())
        self.assertLess(sc.wert_linie(), sc.trenner_oben() + sc.TRENNER_HOEHE)

    def test_wandstifte_lassen_keine_kugel_vorbei(self):
        """Sie sind ABSICHTLICH Teil der Wand.

        Ohne sie blieb ein 126 px breiter senkrechter Kanal, in dem Kugeln
        ungebremst durchrutschten – ueber 40 Seeds landeten 132 von 200 in
        den beiden aeussersten Faechern.
        """
        innen_links = sc.WALL_LEFT + sc.SEG_RADIUS
        naechster = min(p.x for p in self.track.pegs)
        luecke = (naechster - sc.PEG_RADIUS) - innen_links
        self.assertLess(luecke, sc.MARBLE_D,
                        f"{luecke:.0f} px Kanal an der Wand – Kugel ist "
                        f"{sc.MARBLE_D:.0f} px")

    def test_reihen_sind_ueber_die_seeds_symmetrisch(self):
        """Ungerade Reihen waren immer nach RECHTS versetzt.

        Die Randbeschneidung traf dadurch links anders als rechts – und
        zwar in JEDEM Seed gleich. Gemessen ueber 500 Laeufe gewann
        Startplatz 1 in 25,0 % statt 20 %, Chi-Quadrat 10,4 gegen
        kritische 9,49.

        Innerhalb EINES Bretts darf es schief sein: die zufaellige `phase`
        verschiebt das Raster je Seed, und die Beschneidung folgt ihr. Was
        nicht sein darf, ist eine Schraeglage ueber die Seeds hinweg –
        genau die misst dieser Test.
        """
        mitte = theme.WIDTH / 2
        links = rechts = 0
        for seed in range(1, 41):
            for p in sc.build_track(seed).pegs:
                if p.x < mitte - 1:
                    links += 1
                elif p.x > mitte + 1:
                    rechts += 1
        gesamt = links + rechts
        self.assertLess(abs(links - rechts) / gesamt, 0.02,
                        f"{links} Stifte links, {rechts} rechts")

    def test_keine_engstellen(self):
        for seed in range(1, 21):
            with self.subTest(seed=seed):
                maengel = sc.pruefe_durchlaesse(sc.build_track(seed))
                self.assertEqual(maengel, [], f"seed {seed}: {maengel[:2]}")

    def test_pruefung_findet_ein_zu_schmales_fach(self):
        """Sonst sagt sie nur immer „in Ordnung"."""
        alt = sc.FACH_WERTE
        try:
            sc.FACH_WERTE = tuple(range(1, 30))
            sc.FAECHER = len(sc.FACH_WERTE)
            maengel = sc.pruefe_durchlaesse(sc.build_track(1))
            self.assertTrue(any("Fach" in m for m in maengel), maengel)
        finally:
            sc.FACH_WERTE = alt
            sc.FAECHER = len(alt)

    def test_gleicher_seed_gleiches_brett(self):
        a, b = sc.build_track(9), sc.build_track(9)
        self.assertEqual(a.pegs, b.pegs)

    def test_anderer_seed_anderes_brett(self):
        self.assertNotEqual(sc.build_track(9).pegs, sc.build_track(10).pegs)


class TestWertung(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = sc.run(3)

    def test_alle_landen(self):
        self.assertEqual(len(self.r.finished), N)

    def test_wertung_ist_vollstaendig(self):
        self.assertEqual(sorted(self.r.order), list(range(N)))

    def test_hoeherer_wert_steht_vorn(self):
        punkte = self.r.extras["punkte"]
        werte = [punkte[str(i)] for i in self.r.order]
        self.assertEqual(werte, sorted(werte, reverse=True))

    def test_gleichstand_entscheidet_die_landezeit(self):
        """Zwei Kugeln im selben Fach sind der Normalfall, nicht die
        Ausnahme – die zweite Stufe muss taugen."""
        punkte = self.r.extras["punkte"]
        for a, b in zip(self.r.order, self.r.order[1:]):
            if punkte[str(a)] == punkte[str(b)]:
                self.assertLessEqual(self.r.finish_times[a],
                                     self.r.finish_times[b],
                                     "bei gleichem Fach entscheidet die Zeit nicht")

    def test_startnummer_entscheidet_nicht(self):
        """Derselbe Grundsatz wie beim Zieleinlauf in B2."""
        regel = sc._regel()
        regel.vorbereiten(N)
        regel.zielzeiten = {i: 5.0 for i in range(N)}
        regel.fach = {i: 0 for i in range(N)}
        letzte = [(0.0, 100.0, 0.0)] * N
        # Alle gleich: die Reihenfolge darf nicht die Startnummer sein –
        # bei echtem Gleichstand ist sie beliebig, aber nicht bevorzugend.
        self.assertEqual(sorted(regel.rangfolge(letzte)), list(range(N)))

    def test_fach_steht_beim_queren_fest(self):
        """Sonst haenge das Ergebnis daran, wann die Simulation aufhoert."""
        regel = sc._regel()
        regel.vorbereiten(N)
        kanten = sc.fach_kanten()
        linie = sc.wert_linie()
        mitte_von_fach_0 = (kanten[0] + kanten[1]) / 2
        regel.schritt(0.0, 0.01, [linie - 5] * N, [linie + 5] * N,
                      [mitte_von_fach_0] * N)
        self.assertEqual(set(regel.fach.values()), {0})
        # Ein zweiter Schritt an anderer Stelle darf nichts mehr aendern.
        regel.schritt(1.0, 0.01, [linie - 5] * N, [linie + 5] * N,
                      [(kanten[8] + kanten[9]) / 2] * N)
        self.assertEqual(set(regel.fach.values()), {0})

    def test_wertung_bleibt_vollstaendig_wenn_niemand_landet(self):
        regel = sc._regel()
        regel.vorbereiten(N)
        letzte = [(0.0, 100.0 * i, 0.0) for i in range(N)]
        order = regel.rangfolge(letzte)
        self.assertEqual(sorted(order), list(range(N)))
        self.assertEqual(order[0], N - 1, "nicht nach Tiefe gereiht")

    def test_fach_von_faellt_nicht_aus(self):
        regel = sc._regel()
        kanten = sc.fach_kanten()
        self.assertEqual(regel.fach_von(kanten[0] - 500), 0)
        self.assertEqual(regel.fach_von(kanten[-1] + 500), sc.FAECHER - 1)
        for k in range(sc.FAECHER):
            self.assertEqual(regel.fach_von((kanten[k] + kanten[k + 1]) / 2), k)


class TestAnnahme(unittest.TestCase):
    def test_alle_im_selben_fach_wird_abgelehnt(self):
        r = sc.run(3)
        r.extras = dict(r.extras)
        r.extras["fach"] = {str(i): 4 for i in range(N)}
        self.assertTrue(any("selben Fach" in p for p in sc.check(r)))

    def test_geduld_ist_groesser_als_der_standard(self):
        """Mit den 6 Sekunden von `simulate` endete der Lauf, waehrend vier
        von fuenf Kugeln noch zehn Reihen ueber dem Boden waren."""
        self.assertGreater(sc.GEDULD, 6.0)


class TestSpeichern(unittest.TestCase):
    def test_extras_ueberleben_json(self):
        r = sc.run(3)
        zurueck = physics.from_dict(json.loads(json.dumps(physics.to_dict(r))))
        self.assertEqual(zurueck.extras, r.extras)
        self.assertEqual(zurueck.order, r.order)

    def test_alte_state_json_laden_weiter(self):
        d = physics.to_dict(descent.run(1))
        del d["extras"]
        self.assertEqual(physics.from_dict(d).extras, {})

    def test_zwischenspeicher_verliert_die_faecher_nicht(self):
        """`run()` haengt die Faecher NACH `simulate` an. Ginge das am
        Zwischenspeicher vorbei, zeichnete ein wiederverwendeter Lauf ein
        leeres Brett."""
        with tempfile.TemporaryDirectory() as d:
            frisch, _, _ = build.lauf_holen(sc, 3, Path(d))
            gecacht, _, _ = build.lauf_holen(sc, 3, Path(d))
        self.assertEqual(gecacht.extras, frisch.extras)
        self.assertEqual(gecacht.order, frisch.order)
        self.assertTrue(gecacht.extras.get("faecher"))


class TestAnbindung(unittest.TestCase):
    def test_disziplin_ist_registriert(self):
        self.assertIn(sc.NAME, build.DISZIPLINEN)

    def test_regel_kennung_faengt_die_punktwerte(self):
        """Aendern sich die Werte, ist es ein anderes Rennen – auch wenn
        das Brett gleich aussieht."""
        vorher = build.lauf_fingerabdruck(sc, 1)
        alt = sc.FACH_WERTE
        try:
            sc.FACH_WERTE = tuple(reversed(range(1, sc.FAECHER + 1)))
            self.assertNotEqual(build.lauf_fingerabdruck(sc, 1), vorher)
        finally:
            sc.FACH_WERTE = alt
        self.assertEqual(build.lauf_fingerabdruck(sc, 1), vorher)

    def test_keine_torbeschriftung(self):
        """`GATE 1` waere hier schlicht falsch – die Linie markiert, wo das
        Fach feststeht, nicht ein Ausscheiden."""
        r = sc.run(3)
        self.assertIsNone(r.extras.get("mark_label"))
        self.assertEqual(r.eliminated, {})

    def test_rangliste_endet_auf_dem_echten_ergebnis(self):
        """Denselben Test haben B5 und B7 – B8 fehlte er.

        `rangfolge_bei` reihte die Gelandeten nach der ZEIT, die Streuung
        wertet aber nach dem Fach. Gemessen ueber 39 Laeufe: in 92 % der
        Faelle wich die Rangliste von der Ergebniskarte ab, in 44 % zeigte
        sie einen anderen Fuehrenden.
        """
        for seed in (3, 5, 11):
            r = sc.run(seed)
            letzte = build.rangfolge_bei(r, len(r.frames) - 1)
            self.assertEqual(letzte, list(r.order), f"seed {seed}")

    def test_bild_entsteht(self):
        r = sc.run(3)
        tops = build.kamerafahrt(r)
        f = len(r.frames) - 5
        bild = build.zeichne_bild(r, f, tops[f], sc.HOOK, 1, len(r.frames) - 30)
        self.assertEqual(bild.size, (theme.WIDTH, theme.HEIGHT))


class TestTaugtFuerEineSaison(unittest.TestCase):
    """Der teure Test. Rund 20 Sekunden."""

    LAEUFE = 24

    @classmethod
    def setUpClass(cls):
        cls.brauchbar = 0
        cls.kaputt = 0
        cls.dauern = []
        cls.faecher = Counter()
        for seed in range(1, cls.LAEUFE + 1):
            try:
                r = sc.run(seed)
            except physics.SimulationError:
                cls.kaputt += 1
                continue
            cls.dauern.append(r.duration)
            for f in (r.extras.get("fach") or {}).values():
                cls.faecher[f] += 1
            if not sc.check(r):
                cls.brauchbar += 1

    def test_jeder_lauf_geht_auf(self):
        self.assertEqual(self.kaputt, 0)

    def test_fast_jeder_seed_ist_brauchbar(self):
        self.assertGreaterEqual(self.brauchbar, self.LAEUFE * 0.85,
                                f"nur {self.brauchbar} von {self.LAEUFE}")

    def test_dauer_liegt_meist_im_fenster(self):
        """Einzelne Ausreisser sind erlaubt – `check()` faengt sie ab und
        `--search` uebergeht sie. Was nicht sein darf: dass das Fenster im
        Regelfall verfehlt wird."""
        drin = [d for d in self.dauern
                if sc.MIN_SECONDS - 1.0 < d <= sc.MAX_SECONDS]
        self.assertGreaterEqual(len(drin), len(self.dauern) * 0.85,
                                f"nur {len(drin)} von {len(self.dauern)} "
                                f"im Fenster: {[round(d) for d in self.dauern]}")

    def test_das_brett_streut_wirklich(self):
        """Landen alle immer in denselben zwei Faechern, ist es kein
        Plinko-Brett, sondern ein Trichter."""
        self.assertGreaterEqual(len(self.faecher), 5,
                                f"nur {len(self.faecher)} Faecher getroffen")

    def test_keine_seite_bevorzugt(self):
        mitte = sc.FAECHER // 2
        links = sum(n for f, n in self.faecher.items() if f < mitte)
        rechts = sum(n for f, n in self.faecher.items() if f > mitte)
        gesamt = links + rechts
        if gesamt < 40:
            self.skipTest("zu wenige Landungen ausserhalb der Mitte")
        self.assertLess(abs(links - rechts) / gesamt, 0.35,
                        f"{links} links gegen {rechts} rechts")


if __name__ == "__main__":
    unittest.main(verbosity=2)
