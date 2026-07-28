#!/usr/bin/env python3
"""
Tests fuer Baustein B5 (build.py).

Der teure Test am Ende baut wirklich eine MP4 – aus einem gekuerzten Lauf
und ohne Supersampling, damit er in Sekunden durchlaeuft. Er ueberspringt
sich selbst, wenn kein ffmpeg da ist.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gravitycup import build                                   # noqa: E402
from gravitycup.core import audio, draw, physics, theme        # noqa: E402
from gravitycup.disciplines import descent                     # noqa: E402

#: Ein Seed, der die Annahmekriterien erfuellt. Nicht fest verdrahtet –
#: eine Geometrieaenderung wuerde sonst diesen Test rot faerben statt die
#: Strecke zu pruefen (dieselbe Falle wie in test_b4_descent).
SEED = descent.find_seeds(1, grenze=40)[0][0]


def ffmpeg_da() -> bool:
    try:
        build.ffmpeg_pfad()
        return True
    except SystemExit:
        return False


class TestBildTonGleichLang(unittest.TestCase):
    """Der wichtigste Vertrag: Bild und Ton muessen exakt gleich lang sein.

    audio.build() bemisst den Puffer als len(frames)/fps + TAIL_SECONDS.
    build.py rendert len(frames) + outro_frames(). Laufen die beiden Zahlen
    auseinander, wandert die Tonspur gegen das Bild – bei einem Rennen, das
    von einem Aufprallgeraeusch lebt, faellt das sofort auf.
    """

    def test_nachlauf_entspricht_dem_tonnachlauf(self):
        self.assertEqual(build.outro_frames(theme.FPS),
                         round(audio.TAIL_SECONDS * theme.FPS))

    def test_gesamtlaengen_stimmen_ueberein(self):
        for bilder in (300, 601, 850, 1139):
            with self.subTest(bilder=bilder):
                video_s = (bilder + build.outro_frames()) / theme.FPS
                ton_s = int((bilder / theme.FPS + audio.TAIL_SECONDS)
                            * audio.SR) / audio.SR
                self.assertLess(abs(video_s - ton_s), 1.0 / theme.FPS,
                                f"{video_s:.4f}s Bild gegen {ton_s:.4f}s Ton")


class TestKamerafahrt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = descent.run(SEED)
        cls.tops = build.kamerafahrt(cls.r)

    def test_ein_wert_je_bild(self):
        self.assertEqual(len(self.tops), len(self.r.frames))

    def test_versatz_wird_vollstaendig_zurueckgenommen(self):
        """Sonst bliebe das Bild fuer den Rest des Rennens verschoben.

        Verglichen wird gegen dieselbe Kamerafahrt OHNE den
        Aufhaenger-Versatz, nicht gegen eine nachgebaute – seit B7 klemmt
        die Kamera zusaetzlich nach oben, und ein Nachbau haette das
        stillschweigend uebersehen.
        """
        alt = build.HOOK_KAMERA_VERSATZ
        try:
            build.HOOK_KAMERA_VERSATZ = 0.0
            ohne = build.kamerafahrt(self.r)
        finally:
            build.HOOK_KAMERA_VERSATZ = alt
        ende = build.HOOK_ENDE + build.HOOK_KAMERA_ZURUECK
        for f in range(ende + 60, len(ohne), 37):
            self.assertAlmostEqual(self.tops[f], ohne[f], places=3)

    def test_aufhaenger_verdeckt_keine_kugel(self):
        """Der Kasten fragt „welche Farbe gewinnt?" – dann muss man sie sehen.

        Vor dem Kameraversatz standen ueber 30 Seeds gemessen 461
        Kugelmittelpunkte hinter dem Kasten, zeitweise drei von fuenf
        gleichzeitig.
        """
        kasten = draw.Canvas(scale=1).hook_layout(*descent.HOOK)["box"]
        verdeckt = 0
        for seed, r in descent.find_seeds(6, grenze=40):
            tops = build.kamerafahrt(r)
            for f in range(min(len(tops), build.HOOK_ENDE + 1)):
                if draw.fade(f, build.HOOK_START, build.HOOK_EIN,
                             build.HOOK_HALT, build.HOOK_AUS) <= 0:
                    continue
                verdeckt += sum(1 for p in r.frames[f]
                                if kasten[1] < p[1] - tops[f] < kasten[3])
        self.assertEqual(verdeckt, 0, f"{verdeckt} Kugeln hinter dem Aufhaenger")

    def test_niemand_faellt_unten_aus_dem_bild(self):
        for seed, r in descent.find_seeds(6, grenze=40):
            tops = build.kamerafahrt(r)
            tiefste = max(max(p[1] - tops[f] for p in r.frames[f])
                          for f in range(min(len(tops),
                                             build.HOOK_ENDE + build.HOOK_KAMERA_ZURUECK)))
            self.assertLess(tiefste, theme.HEIGHT,
                            f"seed {seed}: Kugel bei y={tiefste:.0f}")


class TestAnzeige(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = descent.run(SEED)

    def test_rangliste_endet_auf_dem_echten_ergebnis(self):
        letzte = build.rangfolge_bei(self.r, len(self.r.frames) - 1)
        self.assertEqual(letzte, list(self.r.order))

    def test_rangliste_ist_immer_vollstaendig(self):
        for f in (0, 40, 200, len(self.r.frames) // 2, len(self.r.frames) - 1):
            rang = build.rangfolge_bei(self.r, f)
            self.assertEqual(sorted(rang), list(range(len(theme.competitors()))))

    def test_angekommene_rutschen_nicht_zurueck(self):
        """Nach dem Zieleinlauf sinken die Kugeln weiter ins Becken.

        Eine reine Tiefensortierung wuerde sie dort noch ueberholen lassen –
        die Rangliste zeigte dann eine andere Reihenfolge als die Wertung.
        """
        gesehen: dict[int, int] = {}
        for f in range(0, len(self.r.frames), 5):
            for platz, i in enumerate(build.rangfolge_bei(self.r, f)):
                zeit = self.r.finish_times.get(i)
                if zeit is not None and zeit <= f / self.r.fps:
                    if i in gesehen:
                        self.assertEqual(platz, gesehen[i],
                                         f"Teilnehmer {i} wechselt nach dem Ziel den Platz")
                    gesehen[i] = platz

    def test_nachleuchten_ist_chronologisch_und_begrenzt(self):
        s = build.spur(self.r, 200, 0)
        self.assertLessEqual(len(s), theme.TRAIL_LENGTH)
        self.assertEqual(s[-1], (self.r.frames[199][0][0], self.r.frames[199][0][1]))
        self.assertEqual(s[0], (self.r.frames[200 - theme.TRAIL_LENGTH][0][0],
                                self.r.frames[200 - theme.TRAIL_LENGTH][0][1]))

    def test_nachleuchten_am_anfang_leer_statt_negativ(self):
        self.assertEqual(build.spur(self.r, 0, 0), [])
        self.assertEqual(len(build.spur(self.r, 3, 0)), 3)

    def test_bild_hat_ausgabegroesse(self):
        tops = build.kamerafahrt(self.r)
        bild = build.zeichne_bild(self.r, 100, tops[100], descent.HOOK, 1,
                                  len(self.r.frames) - 30)
        self.assertEqual(bild.size, (theme.WIDTH, theme.HEIGHT))

    def test_nachlaufbild_friert_das_letzte_rennbild_ein(self):
        tops = build.kamerafahrt(self.r)
        letzte = len(self.r.frames) - 1
        a = build.zeichne_bild(self.r, letzte, tops[letzte], descent.HOOK, 1, 0)
        b = build.zeichne_bild(self.r, letzte + 20, tops[letzte], descent.HOOK, 1, 0)
        self.assertEqual(a.tobytes(), b.tobytes())


class TestKodierung(unittest.TestCase):
    """Die Roadmap nennt das Ausgabeformat ausdruecklich."""

    def setUp(self):
        self.befehl = build.ffmpeg_befehl("ffmpeg", Path("t.wav"), Path("o.mp4"),
                                          30, 19, "slow")

    def test_roadmap_vorgaben(self):
        b = self.befehl
        for erwartet in ("libx264", "yuv420p", "aac", "192k", "+faststart"):
            self.assertIn(erwartet, b, f"{erwartet} fehlt im ffmpeg-Aufruf")

    def test_rohbilder_haben_die_richtige_groesse(self):
        self.assertIn(f"{theme.WIDTH}x{theme.HEIGHT}", self.befehl)
        self.assertIn("rgb24", self.befehl)

    def test_tonrate_passt_zur_synthese(self):
        self.assertIn(str(audio.SR), self.befehl)


class TestAbbruch(unittest.TestCase):
    def test_unbrauchbarer_lauf_bricht_ab(self):
        """Lieber keine Datei als eine kaputte."""
        class Kaputt:
            NAME = "kaputt"
            HOOK = ("x", "y")
            build_track = staticmethod(descent.build_track)

            @staticmethod
            def run(seed):
                return descent.run(SEED)

            @staticmethod
            def check(result):
                return ["nicht im Ziel: alle – Rennen wirkt unfertig"]

        with tempfile.TemporaryDirectory() as d:
            ziel = Path(d) / "out.mp4"
            with self.assertRaises(SystemExit) as ctx:
                build.bauen(Kaputt, SEED, ziel, scale=1, cache_nutzen=False,
                            archiv=False, leise=True)
            self.assertIn("nicht im Ziel", str(ctx.exception))
            self.assertFalse(ziel.exists(), "trotz Abbruch eine Datei erzeugt")


class TestZwischenspeicher(unittest.TestCase):
    """Der Zwischenspeicher darf nie etwas Falsches ausliefern."""

    def test_fingerabdruck_reagiert_auf_die_geometrie(self):
        """Sonst entsteht ein Video aus einer Strecke, die es nicht mehr gibt.

        Die Streckenform wurde an einem Tag mehrfach umgebaut. Ein Cache,
        der nur Seed und Disziplinnamen kennt, haette danach den alten Lauf
        geliefert – und `--pruefen` haette die Folge als gefaelscht gemeldet.
        """
        vorher = build.lauf_fingerabdruck(descent, SEED)
        alt = descent.RAMP_END_MAX
        try:
            descent.RAMP_END_MAX = alt - 20
            descent.RAMP_END_RANGE = (descent.RAMP_END_MIN, descent.RAMP_END_MAX)
            self.assertNotEqual(build.lauf_fingerabdruck(descent, SEED), vorher)
        finally:
            descent.RAMP_END_MAX = alt
            descent.RAMP_END_RANGE = (descent.RAMP_END_MIN, alt)
        self.assertEqual(build.lauf_fingerabdruck(descent, SEED), vorher)

    def test_fingerabdruck_reagiert_auf_die_physik(self):
        vorher = build.lauf_fingerabdruck(descent, SEED)
        alt = physics.GRAVITY
        try:
            physics.GRAVITY = alt + 1.0
            self.assertNotEqual(build.lauf_fingerabdruck(descent, SEED), vorher)
        finally:
            physics.GRAVITY = alt

    def test_zu_kurze_wav_wird_verworfen(self):
        """DER Blocker: eine kurze WAV schnitt das Video stumm ab.

        ffmpeg endete dabei mit Code 0, der Aufbau meldete „100 %", und das
        Rundenarchiv beglaubigte per Pruefsumme ein Video, in dem das Rennen
        fehlte.
        """
        r = descent.run(SEED)
        with tempfile.TemporaryDirectory() as d:
            gut = Path(d) / "gut.wav"
            stereo, _ = audio.build(r)
            audio.write_wav(gut, stereo)
            self.assertTrue(build.wav_passt(gut, r))

            kurz = Path(d) / "kurz.wav"
            audio.write_wav(kurz, stereo[:len(stereo) // 2])
            self.assertFalse(build.wav_passt(kurz, r),
                             "halbe Tonspur wurde als gueltig durchgewinkt")

            kaputt = Path(d) / "kaputt.wav"
            kaputt.write_bytes(b"RIFF" + b"\x00" * 100)
            self.assertFalse(build.wav_passt(kaputt, r))

            self.assertFalse(build.wav_passt(Path(d) / "gibtsnicht.wav", r))

    def test_erwartete_tonlaenge_stimmt_mit_audio_ueberein(self):
        r = descent.run(SEED)
        stereo, _ = audio.build(r)
        self.assertEqual(build.ton_samples(r), len(stereo))


class TestZeichenfehler(unittest.TestCase):
    def test_lange_segmente_bleiben_sichtbar(self):
        """Die Seitenwaende laufen ueber die ganze Strecke.

        Die alte Pruefung fragte „ist ein ENDE sichtbar?". Bei beiden Enden
        weit ausserhalb war die Antwort nein – und die Waende verschwanden
        mitten im Rennen aus dem Bild.
        """
        cam = draw.Camera(top=3000.0)
        self.assertTrue(cam.overlaps(0.0, 5680.0),
                        "durchlaufende Wand gilt als unsichtbar")
        self.assertFalse(cam.overlaps(0.0, 100.0))
        self.assertFalse(cam.overlaps(5600.0, 5680.0))
        self.assertTrue(cam.overlaps(2900.0, 3100.0))

    def test_waende_sind_im_ganzen_rennen_gezeichnet(self):
        r = descent.run(SEED)
        tops = build.kamerafahrt(r)
        waende = [s for s in r.segments if s.x1 == s.x2]
        self.assertEqual(len(waende), 2, "Strecke hat keine zwei Seitenwaende")
        for f in range(0, len(r.frames), 97):
            cam = draw.Camera(top=tops[f], limit_bottom=r.finish_y)
            for w in waende:
                self.assertTrue(cam.overlaps(w.y1, w.y2),
                                f"Bild {f}: Seitenwand nicht gezeichnet")


@unittest.skipUnless(ffmpeg_da(), "ffmpeg fehlt")
class TestGanzerAblauf(unittest.TestCase):
    """Einmal wirklich durch – gekuerzt, damit es Sekunden statt Minuten dauert."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        cls.ziel = d / "test.mp4"

        class Kurz:
            NAME = descent.NAME
            HOOK = descent.HOOK
            build_track = staticmethod(descent.build_track)

            @staticmethod
            def run(seed):
                r = descent.run(seed)
                r.frames = r.frames[:120]      # 4 s statt 28 s
                return r

            @staticmethod
            def check(result):
                return []

        cls.manifest = build.bauen(Kurz, SEED, cls.ziel, scale=1,
                                   runde="S99R01", cache_nutzen=False,
                                   archiv=False, preset="ultrafast", crf=30,
                                   leise=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_datei_entsteht(self):
        self.assertTrue(self.ziel.exists())
        self.assertGreater(self.ziel.stat().st_size, 10_000)

    def test_manifest_haelt_fest_was_nachrechenbar_macht(self):
        m = self.manifest
        for feld in ("seed", "disziplin", "codestand", "versionen",
                     "ergebnis", "pruefsummen", "gestaltung"):
            self.assertIn(feld, m)
        for lib in ("python", "pymunk", "numpy", "pillow", "ffmpeg"):
            self.assertIn(lib, m["versionen"], f"{lib} fehlt im Manifest")
        self.assertEqual(len(m["ergebnis"]["reihenfolge"]),
                         len(theme.competitors()))
        self.assertEqual(m["ergebnis"]["sieger"], m["ergebnis"]["reihenfolge"][0])
        self.assertTrue(m["pruefsummen"]["mp4"])
        self.assertEqual(len(m["pruefsummen"]["mp4"]), 64)

    def test_manifest_ist_json(self):
        json.dumps(self.manifest, ensure_ascii=False)

    def test_harte_determinismus_zusagen_stehen_drin(self):
        """Der Pruefbericht verlangt sie ausdruecklich: state.json und
        Bildfolge hart, MP4 nur perzeptuell."""
        p = self.manifest["pruefsummen"]
        for feld in ("lauf", "bildfolge", "wav", "mp4", "geometrie"):
            self.assertEqual(len(p[feld]), 64, f"{feld} ist kein SHA-256")
        self.assertIn("nicht", p["hinweis"].lower())

    def test_videolaenge_steht_getrennt_von_der_renndauer(self):
        v = self.manifest["video"]
        self.assertEqual(v["bilder"],
                         self.manifest["ergebnis"]["bilder"] + build.outro_frames())
        self.assertGreater(v["dauer_s"], self.manifest["ergebnis"]["dauer_s"])

    def test_ausgabe_hat_bild_und_ton(self):
        exe = build.ffmpeg_pfad()
        aus = subprocess.run([exe, "-hide_banner", "-i", str(self.ziel)],
                             capture_output=True, text=True, timeout=60)
        text = aus.stdout + aus.stderr
        self.assertIn("h264", text)
        self.assertIn("yuv420p", text)
        self.assertIn("aac", text)
        self.assertIn(f"{theme.WIDTH}x{theme.HEIGHT}", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestAusgestrahlt(unittest.TestCase):
    """Der Vermerk entscheidet, ob ein Ergebnis oeffentlich werden darf."""

    def setUp(self):
        import tempfile
        self.archiv = Path(tempfile.mkdtemp())
        (self.archiv / "S01R01.json").write_text(
            json.dumps({"runde": "S01R01", "seed": 1}), encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.archiv, ignore_errors=True)

    def lies(self, runde="S01R01"):
        return json.loads((self.archiv / f"{runde}.json")
                          .read_text(encoding="utf-8"))

    def test_vermerk_wird_geschrieben(self):
        self.assertEqual(build.ausgestrahlt("S01R01", "abc123", self.archiv), 0)
        self.assertEqual(self.lies()["youtube_id"], "abc123")

    def test_der_lauf_bleibt_unveraendert(self):
        """Der Vermerk darf das Archivierte nicht anfassen – sonst waere die
        Runde nicht mehr die, die gerechnet wurde."""
        vorher = self.lies()
        build.ausgestrahlt("S01R01", "abc123", self.archiv)
        nachher = self.lies()
        del nachher["youtube_id"]
        self.assertEqual(vorher, nachher)

    def test_zweite_abweichende_kennung_wird_abgelehnt(self):
        """Zwei Kennungen fuer eine Runde heisst: dieselbe Folge wurde
        zweimal hochgeladen. Das still zu ueberschreiben verschleiert es."""
        build.ausgestrahlt("S01R01", "abc123", self.archiv)
        self.assertEqual(build.ausgestrahlt("S01R01", "xyz789", self.archiv), 1)
        self.assertEqual(self.lies()["youtube_id"], "abc123")

    def test_dieselbe_kennung_nochmal_ist_in_ordnung(self):
        build.ausgestrahlt("S01R01", "abc123", self.archiv)
        self.assertEqual(build.ausgestrahlt("S01R01", "abc123", self.archiv), 0)

    def test_fehlendes_manifest_meldet_fehler(self):
        self.assertEqual(build.ausgestrahlt("S01R99", "abc", self.archiv), 2)


class TestBeschreibung(unittest.TestCase):
    """Die Beschreibung ist der Ort, an dem der Kanal sein Versprechen
    einloest. Steht dort ein anderer Seed als im Archiv, ist es wertlos."""

    def manifest(self):
        return {
            "runde": "S01R07",
            "disziplin": "descent",
            "seed": 42,
            "codestand": {"commit": "abcdef1234567890", "sauber": True},
            "versionen": {"python": "3.12.10", "pymunk": "7.3.0"},
            "ergebnis": {"sieger": "JADE",
                         "reihenfolge": ["JADE", "RED", "GOLD", "BLUE", "VIOLET"]},
        }

    def test_seed_und_codestand_stehen_drin(self):
        text = build.beschreibung(self.manifest())
        self.assertIn("seed        42", text)
        self.assertIn("abcdef123456", text)
        self.assertIn("descent", text)

    def test_ergebnis_stimmt_mit_dem_manifest_ueberein(self):
        text = build.beschreibung(self.manifest())
        self.assertIn("Winner: JADE", text)
        self.assertIn("JADE → RED → GOLD → BLUE → VIOLET", text)

    def test_keine_spitzen_klammern(self):
        """YouTube nimmt die Beschreibung sonst nicht an.

        Gefunden beim ersten Testupload am 28.07.2026: die Rangfolge stand
        als "VIOLET > GOLD > ..." da, das Formular meldete "Spitze Klammern
        sind nicht zulaessig" und liess sich nicht absenden. Alle drei
        bereits erzeugten Beschreibungen waren betroffen.
        """
        from gravitycup.season import standings as st
        text = build.beschreibung(self.manifest(), st.berechne([]), ["x"])
        self.assertNotIn("<", text)
        self.assertNotIn(">", text)

    def test_klammern_aus_den_daten_werden_auch_ersetzt(self):
        """Der Riegel muss auch greifen, wenn die Klammer aus einem Wert
        kommt – Namen und Disziplinbezeichnungen aendert spaeter jemand,
        ohne an YouTube zu denken."""
        m = self.manifest()
        m["ergebnis"]["sieger"] = "<JADE>"
        m["disziplin"] = "a>b"
        text = build.beschreibung(m)
        self.assertNotIn("<", text)
        self.assertNotIn(">", text)
        self.assertIn("‹JADE›", text)

    def test_ohne_archiv_url_wird_keine_versprochen(self):
        """Auf eine Adresse zu verweisen, die niemand aufrufen kann, ist
        schlimmer als sie wegzulassen."""
        alt = build.ARCHIV_URL
        try:
            build.ARCHIV_URL = ""
            self.assertNotIn("--pruefen", build.beschreibung(self.manifest()))
            build.ARCHIV_URL = "https://example.invalid/gravitycup"
            text = build.beschreibung(self.manifest())
            self.assertIn("--pruefen", text)
            self.assertIn("example.invalid", text)
        finally:
            build.ARCHIV_URL = alt

    def test_saisonstand_wird_angehaengt(self):
        from gravitycup.season import standings as st
        tabelle = st.berechne([])
        text = build.beschreibung(self.manifest(), tabelle, ["x"])
        self.assertIn("Standings after 1 round", text)
        self.assertIn("points per place", text)

    def test_stand_zeigt_nur_runden_bis_zu_dieser(self):
        """Beim Neubau einer alten Folge liegen spaetere schon im Archiv.

        Die Beschreibung von Runde 1 zeigte dadurch den Stand nach Runde 3 –
        ein Ergebnis, das es zum Zeitpunkt dieser Folge noch nicht gab.
        """
        import json as _json
        from gravitycup.season import standings as st
        with tempfile.TemporaryDirectory() as d:
            for n, ordnung in ((1, [0, 1, 2, 3, 4]), (2, [4, 3, 2, 1, 0]),
                               (3, [1, 2, 3, 4, 0])):
                (Path(d) / f"S01R{n:02d}.json").write_text(_json.dumps({
                    "runde": f"S01R{n:02d}", "disziplin": "descent", "seed": n,
                    "ergebnis": {"reihenfolge_index": ordnung,
                                 "reihenfolge": [theme.competitor(i).name
                                                 for i in ordnung]},
                }), encoding="utf-8")
            alle = st.lade_runden(Path(d), 1)
            bis_zwei = [r for r in alle if r.nummer <= 2]
        self.assertEqual(len(alle), 3)
        self.assertEqual(len(bis_zwei), 2)
        text = build.beschreibung(self.manifest(), st.berechne(bis_zwei), bis_zwei)
        self.assertIn("Standings after 2 rounds", text)
        self.assertNotIn("after 3 rounds", text)
