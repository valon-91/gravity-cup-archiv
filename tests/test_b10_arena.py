#!/usr/bin/env python3
"""
Tests fuer die Arena (Disziplin 4, Langform-Show).

Jeder Test haelt einen Fehler fest, der am 30.07.2026 beim Bauen GEMESSEN
wurde. Die Arena hat mehr davon produziert als jede Disziplin davor, und
fast alle waren still: der Lauf sah nicht kaputt aus, er hatte nur immer
weniger Teilnehmer.

    python -m unittest tests.test_b10_arena -v
"""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gravitycup.core import physics, theme              # noqa: E402
from gravitycup.disciplines import arena                # noqa: E402


class ArenaFall(unittest.TestCase):
    """Gemeinsame Umgebung: Vollbild und grosses Feld."""

    @classmethod
    def setUpClass(cls):
        cls._format = theme.FORMAT
        cls._comps = theme.competitors()
        theme.set_format("quer")
        theme.set_competitors(theme.feld(64))

    @classmethod
    def tearDownClass(cls):
        theme.set_format(cls._format)
        theme.set_competitors(cls._comps)


class TestLeiter(ArenaFall):
    def test_eine_ausscheidung_je_kammer(self):
        st = arena.leiter(64)
        self.assertEqual(len(st), 63)
        self.assertEqual(st[0], 63)
        self.assertEqual(st[-1], 1)

    def test_letzte_kammer_laesst_genau_einen_durch(self):
        for n in (2, 5, 16, 64):
            self.assertEqual(arena.leiter(n)[-1], 1, n)

    def test_block_kuerzt_die_erste_kammer(self):
        st = arena.leiter(64, block=16)
        self.assertEqual(st[0], 48)
        self.assertEqual(st[-1], 1)

    def test_unbrauchbare_angaben_werden_abgelehnt(self):
        with self.assertRaises(ValueError):
            arena.leiter(1)
        with self.assertRaises(ValueError):
            arena.leiter(8, block=8)


class TestBauart(ArenaFall):
    def test_kammern_schrumpfen_mit_dem_feld(self):
        """Ohne Schrumpfen faellt der Kugel-Kugel-Anteil bei acht
        Teilnehmern von 49 auf 18 % – die Show wuerde zum Ende hin ruhiger,
        und das ist das Gegenteil eines Spannungsbogens."""
        formen = arena.kammerformen(64)
        breiten = [f.rechts - f.links for f in formen]
        self.assertEqual(breiten, sorted(breiten, reverse=True))
        self.assertGreater(breiten[0] / breiten[-1], 2.0)

    def test_ausgang_schrumpft_mit(self):
        """Drei Kugelbreiten sind fuer fuenf Kugeln kein Nadeloehr mehr;
        bei festem Ausgang lief ein 64er-Lauf in 2,3 statt 2,8 Minuten
        durch, weil die spaeten Kammern in Sekunden leer waren."""
        formen = arena.kammerformen(64)
        self.assertGreater(formen[0].ausgang, formen[-1].ausgang)
        for f in formen:
            self.assertGreater(f.ausgang, arena.MARBLE_D,
                               f"Kammer {f.nummer}: Ausgang enger als eine Kugel")

    def test_kammer_passt_ins_vollbild(self):
        """1800x950 lag bei 81 % statt 100 % – die groesste Kammer muss
        sicher hineinpassen, sonst braucht es wieder eine Verfolgerkamera."""
        theme.set_format("quer")
        b = arena.VORGABE
        self.assertLessEqual(b.breite_max + 2 * arena.MARBLE_D, theme.WIDTH)
        self.assertLessEqual(b.hoehe + 2 * arena.MARBLE_D, theme.HEIGHT)

    def test_zu_viele_etagen_werden_abgelehnt(self):
        """Bei 93 px Abstand und 44 px Bodendicke bleiben 49 px fuer eine
        64-px-Kugel, und kein einziger Lauf kam durch."""
        with self.assertRaises(ValueError):
            arena.Bauart(etagen=6).pruefen()

    def test_zu_schmale_kammer_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            arena.Bauart(breite_min=200.0).pruefen()


class TestGeometrie(ArenaFall):
    def test_keine_engstellen(self):
        for seed in (1, 2, 3, 7):
            track = arena.build_track(seed, 64)
            self.assertEqual(arena.pruefe_durchlaesse(track, 64), [], seed)

    def test_startplaetze_ueberlappen_nicht(self):
        """Ueberlappende Koerper schleudert pymunk im ersten Schritt
        auseinander – gemessen gingen dabei neun von 64 Kugeln verloren."""
        import math
        formen = arena.kammerformen(64)
        plaetze = arena.startplaetze(64, formen[0])
        self.assertEqual(len(plaetze), 64)
        for i, a in enumerate(plaetze):
            for b in plaetze[i + 1:]:
                self.assertGreaterEqual(math.dist(a, b), arena.MARBLE_D)

    def test_start_liegt_ueber_der_ersten_kammer(self):
        """Stand die Aufstellung IN der Kammer, frass sie 308 der 680
        nutzbaren Pixel."""
        formen = arena.kammerformen(64)
        for _, y in arena.startplaetze(64, formen[0]):
            self.assertLess(y, formen[0].oben)

    def test_waende_reichen_ueber_die_startkammer(self):
        track = arena.build_track(1, 64)
        formen = arena.kammerformen(64)
        oberster = min(y for _, y in arena.startplaetze(64, formen[0]))
        senkrecht = [s for s in track.segments if s.x1 == s.x2]
        self.assertTrue(any(s.y1 < oberster for s in senkrecht),
                        "keine Wand reicht ueber den obersten Startplatz")

    def test_rutsche_faengt_den_versatz_ab(self):
        """DER stille Fehler: der Ausgang wird je Seed bis zu 272 px aus der
        Mitte gerueckt, die Kammern werden nach unten aber immer schmaler.
        Ohne Rutsche fiel ein Teil des Feldes an der naechsten Kammer vorbei
        ins Nichts – 43 von 64 Kugeln verloren, 21 statt 63 Ausscheidungen,
        und der Lauf sah dabei nicht kaputt aus.
        """
        for seed in (1, 4, 9):
            r = arena.run(seed, 8)
            verloren = [i for i, p in enumerate(r.frames[-1])
                        if abs(p[0]) > 1e6 or abs(p[1]) > 1e6]
            self.assertEqual(verloren, [], f"seed {seed}: Kugeln im Nichts")


class TestRegel(ArenaFall):
    def test_ziellinie_wird_immer_mitgeschrieben(self):
        """Dieselbe Falle wie bei der Eliminierung: die Regel darf nicht
        erst hinsehen, wenn alle Kammern abgehakt sind. Der Ueberlebende
        raest den letzten Kammern davon und lag 146 px HINTER der Linie,
        bevor der Kammerzaehler ankam – der Lauf lief 480 s gegen die
        Notbremse, mit null Angekommenen.
        """
        formen = arena.kammerformen(4)
        regel = arena.Kammern(formen, finish_y=9000.0)
        regel.vorbereiten(4)
        self.assertLess(regel.kammer, len(formen))
        regel.schritt(0.0, 0.01, [8000.0] * 4,
                      [9100.0, 8900.0, 8800.0, 8700.0])
        self.assertIn(0, regel.zielzeiten,
                      "Zielquerung waehrend einer laufenden Kammer verworfen")

    def test_sperre_wartet_auf_die_nachzuegler(self):
        """Die Sperre haelt das Feld, bis ALLE da sind – aber keine Sekunde
        laenger.

        Als fester Timer war das ein Ladebildschirm: bei zwoelf Kugeln
        sassen alle nach vier Sekunden unten und warteten achtzehn weitere.
        Gemessen sank die Laufzeit bei zwoelf Teilnehmern danach von 3:11
        auf 0:39 – das war fast alles Warten.
        """
        formen = arena.kammerformen(4)
        regel = arena.Kammern(formen, finish_y=9e9, raeumzeit=99.0,
                              halt_beat=0.5)
        regel.vorbereiten(4)
        drin = formen[0].oben + 200
        # Einer haengt noch ueber der Kammer.
        noch_nicht = [drin, drin, drin, formen[0].oben - 300]
        for k in range(300):
            regel.schritt(k * 0.01, 0.01, noch_nicht, noch_nicht)
        self.assertEqual(regel.offene_tore(), set(),
                         "Sperre geht auf, obwohl noch jemand fehlt")
        # Jetzt sind alle drin.
        alle = [drin] * 4
        for k in range(300, 400):
            regel.schritt(k * 0.01, 0.01, alle, alle)
        self.assertIn(0, regel.offene_tore(),
                      "Sperre bleibt zu, obwohl alle da sind")

    def test_haltezeit_bleibt_die_obergrenze(self):
        """Bleibt einer haengen, darf die Kammer nicht ewig warten."""
        formen = arena.kammerformen(4)
        regel = arena.Kammern(formen, finish_y=9e9, raeumzeit=99.0)
        regel.vorbereiten(4)
        fehlt = [formen[0].oben + 200] * 3 + [formen[0].oben - 300]
        for k in range(int((formen[0].halt + 1) / 0.01)):
            regel.schritt(k * 0.01, 0.01, fehlt, fehlt)
        self.assertIn(0, regel.offene_tore(),
                      "Sperre wartet ueber die Obergrenze hinaus auf einen "
                      "Nachzuegler, der nicht mehr kommt")

    def test_raeumzeit_erzwingt_fortschritt(self):
        """Bleibt eine Kugel haengen, wartet die Kammer sonst ewig und
        blockiert die ganze Kaskade: gemessen 3 von 6 Laeufen mit bis zu
        30 Kugeln im Ziel und NULL Ausscheidungen."""
        formen = arena.kammerformen(4)
        regel = arena.Kammern(formen, finish_y=9e9, raeumzeit=1.0)
        regel.vorbereiten(4)
        oben = [formen[0].austritt - 500] * 4
        raus = set()
        for schritt in range(int((formen[0].halt + 3) / 0.01)):
            raus |= regel.schritt(schritt * 0.01, 0.01, oben, oben)
        self.assertTrue(raus, "Raeumzeit hat kein Tor ausgeloest")
        self.assertGreater(regel.kammer, 0)

    def test_letzte_kammer_muss_einen_uebrig_lassen(self):
        formen = arena.kammerformen(4)
        kaputt = list(formen[:-1])
        regel = arena.Kammern(kaputt, finish_y=9000.0)
        with self.assertRaises(ValueError):
            regel.vorbereiten(4)

    def test_wertung_ist_vollstaendig(self):
        r = arena.run(2, 12)
        self.assertEqual(sorted(r.order), list(range(12)))

    def test_ueberlebender_gewinnt(self):
        r = arena.run(2, 12)
        uebrig = [i for i in range(12) if i not in r.eliminated]
        self.assertEqual(uebrig, [r.winner])


class TestLauf(ArenaFall):
    """EIN vollstaendiger Lauf im echten Showformat.

    Bewusst mit 64 Teilnehmern und nicht mit einem kleinen Feld: die
    Kennzahlen der Disziplin haengen an der Feldgroesse, und ein Test mit
    zwoelf Kugeln pruefte etwas anderes als das, was gesendet wird.
    Gemessen: 64 Teilnehmer 30-35 % Kugel-Kugel, 24 nur noch 21 %,
    16 noch 19 %. Kostet rund zwanzig Sekunden.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.r = arena.run(2, 64)
        cls.k = arena.kennzahlen(cls.r)

    def test_alle_scheiden_aus_bis_auf_einen(self):
        self.assertEqual(self.k["ausgeschieden"], 63)
        self.assertEqual(len(self.r.finished), 1)

    def test_keine_kugel_geht_verloren(self):
        for i, p in enumerate(self.r.frames[-1]):
            self.assertLess(abs(p[0]), 1e6, i)
            self.assertLess(abs(p[1]), 1e6, i)

    def test_totzeit_bleibt_im_rahmen(self):
        """Ein Teil der Totzeit ist Absicht – waehrend die Sperre zu ist,
        faellt keine Entscheidung, aber das Feld staut sich sichtbar auf.
        Geprueft wird, dass nicht ZUSAETZLICH etwas haengenbleibt."""
        self.assertLessEqual(self.k["totzeit"], arena.MAX_TOTZEIT)

    def test_gedraenge_statt_gaensemarsch(self):
        """Die ausgestrahlten Folgen liegen bei 16 % Kugel-Kugel; die
        kaputten Arena-Laeufe lagen bei 18 bis 22 %.

        Gemessen haengt der Anteil an der FELDGROESSE: 64 Teilnehmer
        ergeben 30 bis 35 %, 24 nur noch 21 %, 16 noch 19 %. Das Kriterium
        gilt fuer die Show und wird deshalb am Showfeld geprueft.
        """
        arten = Counter(h.kind for h in self.r.hits)
        anteil = arten.get("marble", 0) / max(1, sum(arten.values()))
        self.assertGreater(anteil, arena.MIN_KUGEL_KUGEL, f"{anteil:.0%}")

    def test_ausgeschiedene_bleiben_stehen(self):
        for i, zeit in self.r.eliminated.items():
            f = min(len(self.r.frames) - 1, int(zeit * self.r.fps) + 5)
            spaeter = min(len(self.r.frames) - 1, f + 60)
            self.assertEqual(self.r.frames[f][i][:2],
                             self.r.frames[spaeter][i][:2],
                             f"Teilnehmer {i} bewegt sich nach dem Ausscheiden")


class _NurZusehen(physics.Regel):
    """Regel, die nichts tut – fuer Messungen an einzelnen Bauteilen.

    `ausgeschieden` wird gefuellt, damit `simulate` den Lauf nicht als
    „nichts passiert" verwirft; entfernt wird trotzdem niemand.
    """

    name = "zusehen"

    def schritt(self, zeit_von, dt, y_vorher, y_jetzt, x_jetzt=None):
        self.ausgeschieden.setdefault(-1, 0.0)
        return set()

    def rangfolge(self, letzte):
        return list(range(self.count))


class TestBildUndKamera(ArenaFall):
    """Was der Zuschauer sieht (30.07.2026)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.r = arena.run(3, 8)

    def test_lauf_fuehrt_die_sperren_mit(self):
        """Ohne Geometrie im Ergebnis kann `draw` sie nicht zeichnen – und
        dann staut sich das Feld im Video sichtbar an NICHTS auf."""
        self.assertEqual(len(self.r.tore), len(arena.leiter(8)))
        self.assertTrue(all(gruppe for gruppe in self.r.tore))

    def test_oeffnungszeiten_sind_im_ergebnis(self):
        auf = (self.r.extras or {}).get("tore_auf") or {}
        self.assertTrue(auf, "keine Oeffnungszeiten – draw kann die Sperre "
                             "nicht zum richtigen Zeitpunkt weglassen")
        for k, zeit in auf.items():
            self.assertGreaterEqual(float(zeit), 0.0, k)

    def test_sperren_ueberstehen_speichern_und_laden(self):
        zurueck = physics.from_dict(physics.to_dict(self.r))
        self.assertEqual(zurueck.tore, self.r.tore)

    def test_kammerkamera_wird_benutzt(self):
        """Die Verfolgerkamera aus dem Hochformat ist hier falsch: eine
        Kammer passt ganz ins Bild, es gibt nichts zu verfolgen."""
        from gravitycup import build
        self.assertIsNotNone(build.kammerkamera(self.r))
        tops = build.kamerafahrt(self.r)
        self.assertEqual(len(tops), len(self.r.frames))

    def test_kamera_laeuft_nur_vorwaerts(self):
        """Eine Kamera, die zurueckspringt, sieht aus wie ein Schnittfehler."""
        from gravitycup import build
        tops = build.kamerafahrt(self.r)
        for a, b in zip(tops, tops[1:]):
            self.assertGreaterEqual(b, a - 0.5)

    def test_bild_laeuft_durch(self):
        from gravitycup import build
        tops = build.kamerafahrt(self.r)
        for f in (0, len(self.r.frames) // 2, len(self.r.frames) - 1):
            bild = build.zeichne_bild(
                self.r, f, tops[f], ("LAST ONE OUT", "8 enter"), 1,
                karte_start=10 ** 9, comps=theme.feld(8), punkte=None, seed=3)
            self.assertEqual(bild.size, (theme.WIDTH, theme.HEIGHT))


class TestElastizitaet(unittest.TestCase):
    """Trampolin und Prellbock – die Grundlage dafuer (30.07.2026).

    Kam aus dem Vorschlag, drehende oder federnde Elemente einzubauen. Die
    Elastizitaet je Bauteil ist der billige Teil davon: eine Zahl, keine
    bewegte Geometrie, und damit weiterhin deterministisch.
    """

    def test_vorgabe_aendert_nichts(self):
        """Ohne Angabe gilt der Hauswert – sonst rechneten die neunzehn
        ausgestrahlten Runden ploetzlich anders."""
        self.assertIsNone(physics.Segment(0, 0, 100, 0).elastizitaet)
        self.assertIsNone(physics.Peg(0, 0).elastizitaet)

    def _ruecksprung(self, elast):
        """Wie hoch die Kugel nach dem ersten Aufprall zurueckkommt."""
        boden = physics.Segment(-600, 900, 600, 900, 20.0, elast)
        wand_l = physics.Segment(-600, -200, -600, 920, 20.0)
        wand_r = physics.Segment(600, -200, 600, 920, 20.0)
        track = physics.Track(segments=[boden, wand_l, wand_r], pegs=[],
                              starts=[(0.0, 0.0)], finish_y=100000.0)
        erg = physics.simulate(track, 1, regel=_NurZusehen(),
                               max_seconds=4.0, patience_seconds=1e9,
                               tail_seconds=0.1, count=1)
        ys = [p[0][1] for p in erg.frames]
        # Erster Aufprall: das Bild, ab dem die Kugel wieder steigt.
        auftreffen = next((i for i in range(1, len(ys)) if ys[i] < ys[i - 1]),
                          len(ys) - 1)
        # Ruecksprunghoehe: von dort bis zum hoechsten Punkt danach.
        return ys[auftreffen - 1] - min(ys[auftreffen:])

    def test_trampolin_wirft_hoeher_zurueck_als_eine_wand(self):
        wand = self._ruecksprung(None)
        trampolin = self._ruecksprung(1.35)
        self.assertGreater(
            trampolin, wand * 1.5,
            f"Trampolin {trampolin:.0f} px gegen Wand {wand:.0f} px – "
            "die Elastizitaet kommt nicht in der Simulation an")
