"""bin/jev_router.py: prepare/approve/send/score with stub transports only -- no network, no key."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("jev_router", ROOT / "bin" / "jev_router.py")
jr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jr)

MENU = ["A2", "A5", "A7"]
SECRET = "sk-test-NOT-A-REAL-KEY-0123456789abcdef"
_ENV = None


def setUpModule():
    global _ENV
    tmp = tempfile.TemporaryDirectory()
    _ENV = (tmp, mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": tmp.name}))
    _ENV[1].start()


def tearDownModule():
    _ENV[1].stop()
    _ENV[0].cleanup()


def _answers(body, quality="A2", economy="A5", total=1.0):
    q = json.loads(body.decode("utf-8"))["questions"]

    def choice(pick):
        rest = (total - 0.5) / (len(MENU) - 1)
        return {"type": "choice", "choice": pick, "confidence": 0.4,
                "probabilities": {a: 0.5 if a == pick else rest for a in MENU}}
    legend = {str(i): t for i, t in enumerate(q["task_difficulty@v1"]["criteria"])}
    return {"route_quality@v1": choice(quality), "route_economy@v1": choice(economy),
            "task_difficulty@v1": {"type": "score", "legend": legend, "score": 3.0,
                                   "probabilities": {"0": 0.0, "1": 0.0, "2": 0.0, "3": 1.0,
                                                     "4": 0.0}, "confidence": 0.9},
            "needs_review@v1": {"type": "noul", "noul": 0.2}}


class Recorder:
    def __init__(self, store=None, study=None, status=200, error=None, **kw):
        self.calls, self.store, self.study = [], store, study
        self.status, self.error, self.kw = status, error, kw

    def __call__(self, url, body, key, timeout):
        self.calls.append((url, key, timeout))
        if self.store:
            st = jr.Study(self.store, self.study)
            marker = st.read_json(f"calls/T{3 + len(self.calls)}.json")
            assert marker and marker["status"] == "started", "marker must precede the send"
        if self.error:
            return self.status, None, self.error
        return self.status, {"model": "jev-test-1", "extra": "x",
                             "answers": _answers(body, **self.kw),
                             "usage": {"input_tokens": 100, "output_tokens": 2}}, None


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = self.tmp.name
        self.m = jr.prepare("s1", jr.EXPERIMENT_DIR, self.store, MENU, "jev-test-1")

    def tearDown(self):
        self.tmp.cleanup()

    def send(self, transport, **kw):
        kw.setdefault("max_calls", 6)
        with open(os.devnull, "w") as out:
            return jr.send("s1", self.store, self.m["approval_sha"], kw.pop("max_calls"), 10,
                           transport=transport, key_loader=lambda _f: SECRET, out=out, **kw)


class Prepare(Base):
    def test_payloads_match_manifest_and_bound_state(self):
        st = jr.Study(self.store, "s1")
        self.assertEqual(len(self.m["tasks"]), 6)
        for entry in self.m["tasks"].values():
            body = st.read(f"payloads/{entry['short']}.json")
            self.assertEqual(jr._sha(body), entry["sha256"])
            payload = json.loads(body)
            self.assertEqual(set(payload), {"state", "model", "questions"})
            self.assertTrue(all(len(str(v)) <= jr.STATE_CHUNK for v in payload["state"].values()))
            self.assertEqual(set(payload["questions"]["route_quality@v1"]["criteria"]), set(MENU))
        self.assertEqual(jr.manifest_sha(self.m), self.m["approval_sha"])

    def test_menu_never_carries_measured_results(self):
        body = jr.Study(self.store, "s1").read("payloads/T4.json").decode()
        for word in ("solve rate", "QS", "measured", "actual"):
            self.assertNotIn(word, body)

    def test_menu_bounds_and_unknown_arms_refused(self):
        with self.assertRaises(jr.RouterError):
            jr.prepare("s2", jr.EXPERIMENT_DIR, self.store, ["A2"], "m")
        with self.assertRaises(jr.RouterError):
            jr.prepare("s2", jr.EXPERIMENT_DIR, self.store, ["A2", "Z99"], "m")

    def test_prompt_is_redacted_before_chunking(self):
        task = {"id": "T4-x", "short": "T4", "title": "t", "kind": "feature",
                "prompt_text": "token ghp_" + "a" * 36 + " end"}
        state, red = jr.task_state(task)
        self.assertNotIn("ghp_" + "a" * 36, json.dumps(state))
        self.assertTrue(red["redactions"])


class Send(Base):
    def test_wrong_approval_sends_nothing(self):
        t = Recorder()
        with self.assertRaises(jr.RouterError):
            jr.send("s1", self.store, "0" * 64, 6, 10, transport=t,
                    key_loader=lambda _f: SECRET)
        self.assertEqual(t.calls, [])

    def test_call_cap_is_checked_before_any_send(self):
        t = Recorder()
        with self.assertRaises(jr.RouterError):
            self.send(t, max_calls=5)
        self.assertEqual(t.calls, [])

    def test_tampered_payload_refused(self):
        st = jr.Study(self.store, "s1")
        st.write("payloads/T5.json", b'{"changed":true}')
        t = Recorder()
        with self.assertRaises(jr.RouterError):
            self.send(t)
        self.assertEqual(t.calls, [])

    def test_send_once_marker_first_never_replayed(self):
        t = Recorder(store=self.store, study="s1")
        self.send(t)
        self.assertEqual(len(t.calls), 6)
        self.assertTrue(all(c == (jr._jev().DOCUMENTED_ENDPOINT, SECRET, 10) for c in t.calls))
        again = Recorder()
        self.send(again)
        self.assertEqual(again.calls, [])

    def test_failure_recorded_by_kind_and_not_retried(self):
        self.send(Recorder(status=429, error="rate-limited"))
        rec = jr.Study(self.store, "s1").read_json("calls/T4.json")
        self.assertEqual((rec["status"], rec["error"], rec["http_status"]),
                         ("failed", "rate-limited", 429))
        again = Recorder()
        self.send(again)
        self.assertEqual(again.calls, [])

    def test_key_never_persisted(self):
        self.send(Recorder())
        for path in Path(self.store).rglob("*"):
            if path.is_file():
                self.assertNotIn(SECRET, path.read_text(encoding="utf-8"))

    def test_picks_conformant_and_extra_fields_dropped_by_name(self):
        self.send(Recorder(quality="A7", economy="A5"))
        _, rows = jr.picks("s1", self.store)
        r = rows["T4-project-filters"]
        self.assertEqual((r["route_quality"], r["route_economy"], r["conformant"]),
                         ("A7", "A5", True))
        self.assertEqual((r["difficulty"], r["needs_review"]), ("hard", "false"))
        rec = jr.Study(self.store, "s1").read_json("calls/T4.json")
        self.assertIn("extra", rec["ignored_fields"])
        self.assertNotIn('"x"', json.dumps(rec))

    def test_nonconformant_distribution_labelled_not_repaired(self):
        self.send(Recorder(total=0.97))
        _, rows = jr.picks("s1", self.store)
        r = rows["T4-project-filters"]
        self.assertFalse(r["conformant"])
        self.assertEqual(r["route_quality"], "A2")


class Credential(unittest.TestCase):
    def test_env_var_wins_then_file_forms(self):
        self.assertEqual(jr.load_key(environ={jr.KEY_NAME: "a"}), "a")
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / ".env"
            for line, want in ((f"export {jr.KEY_NAME}='q1'", "q1"),
                               (f'{jr.KEY_NAME}="q2"', "q2"), (f"{jr.KEY_NAME}=q3", "q3")):
                f.write_text(f"OTHER=1\n{line}\n")
                self.assertEqual(jr.load_key(f, environ={}), want)
            f.write_text("OTHER=secretvalue\n")
            with self.assertRaises(jr.RouterError) as cm:
                jr.load_key(f, environ={})
            self.assertNotIn("secretvalue", str(cm.exception))

    def test_transport_refuses_plain_http(self):
        with self.assertRaises(jr.RouterError):
            jr.https_transport("http://api.typesafe.ai/v1/systemone", b"{}", "k", 1)


class Score(unittest.TestCase):
    def test_router_static_and_oracles(self):
        manifest = {"menu": ["A", "B"]}
        rows = {t: {"route_quality": "A", "route_economy": "B", "status": "ok",
                    "usage": {"input_tokens": 10, "output_tokens": 1}} for t in ("t1", "t2")}
        cells = {("t1", "A"): {"n": 1, "solve": 1.0, "qs": 90, "aic": 50, "wall_s": 1},
                 ("t1", "B"): {"n": 1, "solve": 1.0, "qs": 80, "aic": 5, "wall_s": 1},
                 ("t2", "A"): {"n": 1, "solve": 1.0, "qs": 70, "aic": 40, "wall_s": 1},
                 ("t2", "B"): {"n": 1, "solve": 0.0, "qs": 20, "aic": 4, "wall_s": 1}}
        out = jr.score(manifest, rows, cells)
        self.assertEqual(out["routers"]["jev-quality"]["qs"], 80)
        self.assertEqual(out["routers"]["jev-economy"]["solve"], 0.5)
        self.assertEqual(out["oracle"]["hindsight-economy"]["picks"], {"t1": "B", "t2": "A"})
        self.assertEqual(out["oracle"]["hindsight-quality"]["picks"], {"t1": "A", "t2": "A"})
        self.assertEqual(out["oracle"]["uniform-random"]["qs"], 65)
        self.assertEqual(out["jev_usage"]["input_tokens"], 20)

    def test_uncovered_pick_is_reported_not_imputed(self):
        rows = {"t1": {"route_quality": "Z", "route_economy": None, "status": "ok",
                       "usage": None}}
        out = jr.score({"menu": ["A", "B"]}, rows, {})
        self.assertEqual(out["routers"]["jev-quality"], {"covered": 0, "tasks": 1})
        self.assertEqual(out["oracle"], {})

    def test_live_args_dedupe(self):
        rows = {"t": {"short": "T4", "route_quality": "A5", "route_economy": "A5"},
                "u": {"short": "T5", "route_quality": "A2", "route_economy": "A30"}}
        trials, arms = jr.live_args({}, rows)
        self.assertEqual(trials, ["T4-A5-r1", "T5-A2-r1", "T5-A30-r1"])
        self.assertEqual(arms, ["A2", "A30", "A5"])


if __name__ == "__main__":
    unittest.main()
