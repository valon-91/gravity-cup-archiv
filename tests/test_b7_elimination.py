#!/usr/bin/env python3
"""
Tests fuer Baustein B7 (disciplines/elimination.py) und die Regel-Naht in
physics.py.

B7 ist der Baustein, an dem sich zeigt, ob die Struktur traegt: die zweite
Disziplin bringt eine andere Siegbedingung mit. Deshalb prueft dieser Satz
zwei Dinge getrennt – dass die Eliminierung stimmt, UND dass das Sturzrennen
davon nichts merkt.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gravitycup import build                                   # noqa: E402
from gravitycup.core import physics, theme                     # noqa: E402
from gravitycup.disciplines import descent, elimination as el   # noqa: E402

N = len(theme.competitors())


class TestRegelNaht(unittest.TestCase):
    """Die Naht, die B2 verspricht und bis B7 nicht existierte.

    `simulate` hatte „wer zuerst unten ist" fest verdrahtet. Die
    Eliminierung war der erste Fall, der die Naht wirklich gebraucht hat.
    """

    def test_ohne_regel_gilt_die_ziellinie(self):
        r = physics.simulate(physics.demo_track(7), 7)
        self.assertEqual(sorted(r.order), list(range(N)))
        self.assertEqual(r.eliminated, {})

    def test_regel_wird_durchgereicht(self):
        class Umgekehrt(physics.RaceToLine):
            name = "umgekehrt"

            def rangfolge(self, letzte):
                return list(reversed(super().rangfolge(letzte)))

        track = physics.demo_track(7)
        normal = physics.simulate(track, 7)
        gedreht = physics.simulate(track, 7, regel=Umgekehrt(track.finish_y))
        self.assertEqual(gedreht.order, list(reversed(normal.order)))

    def test_unvollstaendige_wertung_bricht_ab(self):
        """Eine Regel, die jemanden vergisst, darf nicht durchkommen."""
        class Schlampig(physics.RaceToLine):
            name = "schlampig"

            def rangfolge(self, letzte):
                return super().rangfolge(letzte)[:-1]

        track = physics.demo_track(7)
        with self.assertRaises(physics.SimulationError) as ctx:
            physics.simulate(track, 7, regel=Schlampig(track.finish_y))
        self.assertIn("unvollstaendige Wertung", str(ctx.exception))


class TestStreckenaufbau(unittest.TestCase):
    def test_reihenfolge_im_abschnitt(self):
        """Rutschen, Stifte, Trichter, Kontrollpunkt – in dieser Folge.

        Der Kontrollpunkt lag einmal UEBER dem Tor. Er entschied dann,
        bevor das Tor ueberhaupt gewirkt hatte.
        """
        self.assertLess(el.RUTSCHE_OBEN, el.STIFTE_OBEN)
        self.assertLess(el.STIFTE_OBEN, el.TRICHTER_OBEN)
        self.assertLess(el.TRICHTER_OBEN + el.TRICHTER_HOEHE, el.KONTROLLPUNKT)
        self.assertLess(el.KONTROLLPUNKT, el.ABSCHNITT)

    def test_rutschen_fallen_nicht_aufeinander(self):
        """Ohne Gefaelle-Deckel blieben 18 px zwischen zwei Rutschen."""
        rest = el.RUTSCHE_ABSTAND - el.RUTSCHE_DROP_MAX
        self.assertGreaterEqual(rest, el.MARBLE_D + 2 * el.SEG_RADIUS,
                                f"nur {rest:.0f} px zwischen zwei Rutschen")

    def test_ein_kontrollpunkt_je_tor(self):
        self.assertEqual(len(el.kontrollpunkte()), N - 1)
        punkte = el.kontrollpunkte()
        self.assertEqual(punkte, sorted(punkte))

    def test_segmentaufbau_ist_wie_dokumentiert(self):
        """`tor_paare` verlaesst sich auf diese Reihenfolge."""
        track = el.build_track(1)
        self.assertEqual(len(track.segments),
                         el.TORE * el.SEGMENTE_JE_ABSCHNITT + 3)

    def test_tore_werden_gefunden(self):
        """Die erste Fassung erwischte mit einer Reissverschluss-Paarung
        NIE ein Trichterpaar – und meldete trotzdem „in Ordnung"."""
        paare = el.tor_paare(el.build_track(1))
        self.assertEqual(len(paare), el.TORE)
        for a, b in paare:
            self.assertEqual(a.y2, b.y2, "Trichterhaelften enden versetzt")
            luecke = abs(b.x2 - a.x2) - a.radius - b.radius
            self.assertAlmostEqual(luecke, el.TOR_WEITE - 2 * el.SEG_RADIUS,
                                   places=6)

    def test_tor_ist_breiter_als_eine_kugel_und_enger_als_drei(self):
        luecke = el.TOR_WEITE - 2 * el.SEG_RADIUS
        self.assertGreater(luecke, el.MARBLE_D,
                           "durch das Tor passt keine Kugel")
        self.assertLess(luecke, 3 * el.MARBLE_D,
                        "das Tor draengt das Feld nicht mehr zusammen")

    def test_keine_engstellen(self):
        for seed in range(1, 41):
            with self.subTest(seed=seed):
                maengel = el.pruefe_durchlaesse(el.build_track(seed))
                self.assertEqual(maengel, [], f"seed {seed}: {maengel[:2]}")

    def test_pruefung_findet_ein_zu_enges_tor(self):
        """Sonst sagt sie nur immer „in Ordnung"."""
        track = el.build_track(1)
        a, b = el.tor_paare(track)[0]
        track.segments = list(track.segments)
        basis = el.RUTSCHEN_JE_ABSCHNITT
        track.segments[basis + 1] = physics.Segment(
            b.x1, b.y1, a.x2 + 40, b.y2, b.radius)
        maengel = el.pruefe_durchlaesse(track)
        self.assertTrue(any("Tor 1" in m for m in maengel), maengel)

    def test_gleicher_seed_gleiche_strecke(self):
        a, b = el.build_track(9), el.build_track(9)
        self.assertEqual(a.segments, b.segments)
        self.assertEqual(a.pegs, b.pegs)

    def test_anderer_seed_andere_strecke(self):
        self.assertNotEqual(el.build_track(9).segments,
                            el.build_track(10).segments)

    def test_rutschrichtung_wird_gespiegelt(self):
        """Feste Richtung hiesse: eine Bildseite ist dauerhaft im Vorteil."""
        from collections import Counter
        richtungen = Counter()
        for seed in range(1, 81):
            erste = el.build_track(seed).segments[0]
            richtungen[erste.x2 > erste.x1] += 1
        self.assertGreater(min(richtungen.values()), 20, dict(richtungen))


class TestEliminierung(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = el.run(1)

    def test_genau_ein_ueberlebender(self):
        self.assertEqual(len(self.r.eliminated), N - 1)

    def test_wertung_ist_vollstaendig(self):
        self.assertEqual(sorted(self.r.order), list(range(N)))

    def test_ueberlebender_gewinnt(self):
        ueberlebt = [i for i in range(N) if i not in self.r.eliminated]
        self.assertEqual(ueberlebt, [self.r.winner])

    def test_rueckwaerts_nach_ausscheiden_gewertet(self):
        """Wer zuletzt rausflog, wird Zweiter – wer zuerst, Letzter."""
        nach_zeit = sorted(self.r.eliminated, key=lambda i: self.r.eliminated[i])
        self.assertEqual(self.r.order[1:], list(reversed(nach_zeit)))

    def test_ausgeschiedene_bleiben_stehen(self):
        """Aus dem Spiel heisst raus aus dem Raum – sonst waeren sie ein
        Hindernis, das der Zuschauer nicht erklaeren kann."""
        for i, zeit in self.r.eliminated.items():
            f = int(zeit * self.r.fps) + 3
            spaeter = min(len(self.r.frames) - 1, f + 60)
            self.assertEqual(self.r.frames[f][i][:2],
                             self.r.frames[spaeter][i][:2],
                             f"Teilnehmer {i} bewegt sich nach dem Ausscheiden")

    def test_ausscheidungen_liegen_auseinander(self):
        zeiten = sorted(self.r.eliminated.values())
        for a, b in zip(zeiten, zeiten[1:]):
            self.assertGreaterEqual(b - a, el.MIN_ABSTAND_TORE)

    def test_vorgabe_bauart_aendert_die_strecke_nicht(self):
        """Die Bauart-Umstellung darf keine gesendete Folge beruehren.

        Das Rundenmanifest speichert einen Fingerabdruck der Geometrie, und
        `--pruefen` meldet jede Abweichung. Beim Umstellen am 30.07.2026
        wurde aus dem Literal `0` in der Wandkoordinate ein `0.0` – gleiche
        Zahl, aber der Fingerabdruck hasht JSON, und dort ist `0` ein
        anderer Text als `0.0`. Alle 19 Archivrunden meldeten daraufhin
        „die Strecke hat sich seither geaendert", obwohl sich kein einziger
        Wert geaendert hatte.
        """
        track = el.build_track(3)
        wand = track.segments[-1]
        self.assertIsInstance(
            wand.y1, int,
            "Wandkoordinate ist keine ganze Zahl mehr – der "
            "Geometrie-Fingerabdruck jeder gesendeten Folge weicht damit ab")

    def test_startplaetze_bleiben_bei_fuenf_wie_frueher(self):
        """Fuenf Teilnehmer stehen in EINER Reihe, wie seit B2."""
        plaetze = el.startplaetze(5)
        self.assertEqual(len(set(y for _, y in plaetze)), 1,
                         "gestaffelte Startaufstellung – B2 hat die abgeschafft")
        mitte = theme.WIDTH / 2
        self.assertEqual([x for x, _ in plaetze],
                         [mitte + (i - 2) * el.START_SPACING for i in range(5)])

    def test_grosses_feld_passt_in_den_schacht(self):
        """Sechzehn Startplaetze, alle innerhalb der Waende, keine Ueberlappung."""
        b = el.SHOW
        plaetze = el.startplaetze(el.SHOW_TEILNEHMER, b)
        self.assertEqual(len(plaetze), el.SHOW_TEILNEHMER)
        innen_links = b.wand_links + el.SEG_RADIUS + theme.MARBLE_RADIUS
        innen_rechts = b.wand_rechts - el.SEG_RADIUS - theme.MARBLE_RADIUS
        for x, _ in plaetze:
            self.assertGreaterEqual(x, innen_links)
            self.assertLessEqual(x, innen_rechts)
        for i, a in enumerate(plaetze):
            for b2 in plaetze[i + 1:]:
                abstand = math.dist(a, b2)
                self.assertGreaterEqual(
                    abstand, el.MARBLE_D,
                    "Startplaetze ueberlappen – pymunk schleudert die Kugeln "
                    "beim ersten Schritt auseinander")

    def test_notbremse_waechst_mit_der_torzahl(self):
        """Die Vorgabe von 60 s ist auf vier Tore ausgelegt.

        Bei fuenfzehn schneidet sie mitten durch: die ersten Show-Laeufe
        endeten mit 6 von 15 Ausscheidungen und niemandem im Ziel, und
        nichts daran sah nach einem Fehler aus.
        """
        self.assertGreaterEqual(el.notbremse(el.TORE), physics.MAX_SECONDS)
        self.assertGreater(el.notbremse(15), 15 * 5.9,
                           "Notbremse kuerzer als ein normaler 15-Tore-Lauf")

    def test_bauart_lehnt_unbaubare_masse_ab(self):
        with self.assertRaises(ValueError):
            el.Bauart(wand_links=480.0, wand_rechts=600.0).pruefen()
        with self.assertRaises(ValueError):
            el.Bauart(rutsche_abstand=100.0).pruefen()

    def test_regel_verlangt_passende_torzahl(self):
        regel = el.Elimination([100.0, 200.0], 900.0)
        with self.assertRaises(ValueError):
            regel.vorbereiten(N)

    def test_alle_queren_im_selben_schritt(self):
        """Der Fall, in dem sonst niemand ausscheidet.

        Queren alle gleichzeitig, ist `aktiv - durch` leer. Ohne den
        Sonderfall waere das Tor verbraucht, ohne jemanden auszuscheiden –
        am Ende haette der Lauf mehr Teilnehmer als Tore.
        """
        regel = el.Elimination([100.0, 200.0, 300.0, 400.0], 900.0)
        regel.vorbereiten(N)
        raus = regel.schritt(0.0, 0.01, [90.0] * N,
                             [101.0, 102.0, 103.0, 104.0, 105.0])
        self.assertEqual(len(raus), 1)
        # Wer am spaetesten quert, ist raus – hier der mit dem groessten y.
        self.assertEqual(raus, {0})

    def test_tor_feuert_auch_wenn_es_vorzeitig_passiert_wurde(self):
        """Der Fall, an dem die Disziplin bei 30 Teilnehmern haengenblieb.

        Die erste Fassung zaehlte Querungen nur fuer das GERADE AKTUELLE
        Tor. Wer ein Tor passierte, bevor die Regel darauf umschaltete,
        wurde nie gezaehlt – und weil das Tor auf `len(aktiv) - 1`
        Querungen wartet, wartete es dann fuer immer.

        Bei fuenf Teilnehmern kann das nicht eintreten: das Feld ist enger
        als ein Abschnitt (Median 255 px, Maximum 1474 bei 1984 px
        Abschnittshoehe). Die Voraussetzung stand nirgends und wurde
        nirgends geprueft. Gemessen am 30.07.2026 mit 30 Teilnehmern:
        2 von 29 Ausscheidungen, danach Stillstand, obwohl alle 28
        verbliebenen Kugeln laengst unter der Linie standen, auf die die
        Regel wartete. Nach der Reparatur: 29 von 29, an drei Seeds.

        Hier nachgestellt mit fuenf: im ersten Schritt springen vier
        Teilnehmer ueber Tor 1 UND Tor 2 hinweg. Tor 1 feuert. Tor 2 darf
        danach nicht auf Querungen warten, die schon passiert sind.
        """
        regel = el.Elimination([100.0, 200.0, 300.0, 400.0], 900.0)
        regel.vorbereiten(N)

        # Schritt 1: vier ueberspringen beide Tore, einer bleibt oben.
        raus = regel.schritt(0.0, 0.01, [50.0] * N,
                             [250.0, 260.0, 270.0, 280.0, 90.0])
        self.assertEqual(raus, {4}, "Tor 1 hat den Letzten nicht erwischt")
        self.assertEqual(regel.tor, 1)

        # Schritt 2: niemand quert JETZT Tor 2 – alle sind laengst drunter.
        raus = regel.schritt(0.01, 0.01,
                             [250.0, 260.0, 270.0, 280.0, 90.0],
                             [251.0, 261.0, 271.0, 281.0, 90.0])
        self.assertEqual(len(raus), 1,
                         "Tor 2 feuert nicht, obwohl alle es passiert haben – "
                         "die Regel wartet auf ein Ereignis, das vorbei ist")
        # Wer am spaetesten gequert hat, ist raus: Teilnehmer 0 kam mit dem
        # kuerzesten Sprung ueber die Linie und damit als Letzter.
        self.assertEqual(raus, {0})
        self.assertEqual(regel.tor, 2)

    def test_wertung_bleibt_vollstaendig_wenn_der_lauf_abbricht(self):
        """Notbremse mit drei noch Aktiven: trotzdem fuenf Plaetze."""
        regel = el.Elimination(el.kontrollpunkte(), 9999.0)
        regel.vorbereiten(N)
        regel.ausgeschieden = {3: 1.0, 4: 2.0}
        regel.reihenfolge_raus = [3, 4]
        regel.aktiv = {0, 1, 2}
        letzte = [(0.0, 500.0, 0.0), (0.0, 700.0, 0.0), (0.0, 600.0, 0.0),
                  (0.0, 100.0, 0.0), (0.0, 200.0, 0.0)]
        order = regel.rangfolge(letzte)
        self.assertEqual(sorted(order), list(range(N)))
        self.assertEqual(order[:3], [1, 2, 0], "Aktive nicht nach Tiefe gereiht")
        self.assertEqual(order[3:], [4, 3])


class TestSpeichern(unittest.TestCase):
    def test_ausscheidungen_ueberleben_json(self):
        import json
        r = el.run(1)
        zurueck = physics.from_dict(json.loads(json.dumps(physics.to_dict(r))))
        self.assertEqual(zurueck.eliminated, r.eliminated)
        self.assertEqual(zurueck.marks, r.marks)
        self.assertEqual(zurueck.order, r.order)

    def test_alte_state_json_laden_weiter(self):
        """Die Felder kamen erst mit B7 dazu – ohne Standardwerte waeren
        alle bisherigen Zwischenspeicher unlesbar."""
        d = physics.to_dict(descent.run(1))
        del d["eliminated"]
        del d["marks"]
        r = physics.from_dict(d)
        self.assertEqual(r.eliminated, {})
        self.assertEqual(r.marks, [])


class TestAnzeige(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = el.run(1)

    def test_rangliste_endet_auf_dem_echten_ergebnis(self):
        letzte = build.rangfolge_bei(self.r, len(self.r.frames) - 1)
        self.assertEqual(letzte, list(self.r.order))

    def test_ausgeschiedene_stehen_hinten(self):
        mitte = len(self.r.frames) * 3 // 4
        rang = build.rangfolge_bei(self.r, mitte)
        raus = build.ausgeschieden_bei(self.r, mitte)
        self.assertTrue(raus, "zu diesem Zeitpunkt ist noch niemand raus")
        plaetze = {i: rang.index(i) for i in range(N)}
        for i in raus:
            for j in range(N):
                if j not in raus:
                    self.assertGreater(plaetze[i], plaetze[j],
                                       "Ausgeschiedener steht vor einem Aktiven")

    def test_jede_ausscheidung_ist_im_bild(self):
        """DER Befund der Pruefung.

        Die Kamera hing allein am Fuehrenden, ausgeschieden wird aber
        immer HINTEN. Gemessen ueber 20 Laeufe waren nur 64 % der
        Ausscheidungen ueberhaupt im Bild – der Zuschauer sah bloss, wie
        in der Rangliste ein Name durchgestrichen wurde. Genau die
        Entscheidung, um die es in dieser Disziplin geht, fehlte im Bild.
        """
        for seed, r in ((s, el.run(s)) for s in range(1, 9)):
            tops = build.kamerafahrt(r)
            for i, zeit in r.eliminated.items():
                f = min(int(zeit * r.fps), len(r.frames) - 1)
                y = r.frames[f][i][1] - tops[min(f, len(tops) - 1)]
                self.assertGreaterEqual(y, 0, f"seed {seed}: {i} ueber dem Bild")
                self.assertLessEqual(y, theme.HEIGHT,
                                     f"seed {seed}: {i} unter dem Bild")

    def test_der_letzte_bleibt_im_bild(self):
        """Die Bedingung, aus der die Sichtbarkeit folgt."""
        tops = build.kamerafahrt(self.r)
        for f in range(0, len(self.r.frames), 17):
            aktiv = [p[1] for i, p in enumerate(self.r.frames[f])
                     if i not in build.ausgeschieden_bei(self.r, f)]
            if not aktiv:
                continue
            self.assertGreaterEqual(min(aktiv) - tops[f], 0,
                                    f"Bild {f}: Letzter ueber dem Bildrand")

    def test_der_fuehrende_bleibt_trotzdem_im_bild(self):
        """Die Klemmung nach oben darf den Fuehrenden nicht kosten.

        Bei KAMERA_RAND_OBEN = 420 ist beides zugleich zu haben – gemessen
        ueber 20 Laeufe: 100 % der Ausscheidungen im Bild UND kein einziges
        Bild ohne den Fuehrenden.
        """
        draussen = gesamt = 0
        tops = build.kamerafahrt(self.r)
        for f in range(len(self.r.frames)):
            aktiv = [p[1] for i, p in enumerate(self.r.frames[f])
                     if i not in build.ausgeschieden_bei(self.r, f)]
            if not aktiv:
                continue
            gesamt += 1
            if max(aktiv) - tops[f] > theme.HEIGHT:
                draussen += 1
        self.assertLess(draussen / gesamt, 0.02,
                        f"{draussen} von {gesamt} Bildern ohne Fuehrenden")

    def test_bild_entsteht(self):
        tops = build.kamerafahrt(self.r)
        f = len(self.r.frames) // 2
        bild = build.zeichne_bild(self.r, f, tops[f], el.HOOK, 1,
                                  len(self.r.frames) - 30)
        self.assertEqual(bild.size, (theme.WIDTH, theme.HEIGHT))


class TestSturzrennenUnveraendert(unittest.TestCase):
    """B7 hat physics.py angefasst. B4 darf davon nichts merken."""

    def test_gleiche_reihenfolge_wie_im_archiv(self):
        import json
        pfad = Path(__file__).resolve().parents[1] / "runs" / "S01R01.json"
        if not pfad.exists():
            self.skipTest("kein Rundenarchiv vorhanden")
        m = json.loads(pfad.read_text(encoding="utf-8"))
        r = descent.run(m["seed"])
        self.assertEqual(list(r.order), m["ergebnis"]["reihenfolge_index"],
                         "die veroeffentlichte Runde ist nicht mehr nachrechenbar")

    def test_sturzrennen_hat_keine_ausscheidungen(self):
        r = descent.run(1)
        self.assertEqual(r.eliminated, {})
        self.assertEqual(r.marks, [])


class TestTaugtFuerEineSaison(unittest.TestCase):
    """Der teure Test. Rund 15 Sekunden."""

    LAEUFE = 40

    @classmethod
    def setUpClass(cls):
        cls.brauchbar = 0
        cls.kaputt = 0
        cls.tore = []
        cls.dauern = []
        for seed in range(1, cls.LAEUFE + 1):
            try:
                r = el.run(seed)
            except physics.SimulationError:
                cls.kaputt += 1
                continue
            cls.tore.append(len(r.eliminated))
            cls.dauern.append(r.duration)
            if not el.check(r):
                cls.brauchbar += 1

    def test_jeder_lauf_geht_auf(self):
        self.assertEqual(self.kaputt, 0)
        self.assertTrue(all(t == N - 1 for t in self.tore),
                        f"Ausscheidungen je Lauf: {sorted(set(self.tore))}")

    def test_fast_jeder_seed_ist_brauchbar(self):
        self.assertGreaterEqual(self.brauchbar, self.LAEUFE * 0.85,
                                f"nur {self.brauchbar} von {self.LAEUFE}")

    def test_dauer_liegt_im_fenster(self):
        for d in self.dauern:
            self.assertGreaterEqual(d, el.MIN_SECONDS)
            self.assertLessEqual(d, el.MAX_SECONDS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
