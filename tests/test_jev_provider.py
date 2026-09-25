"""Synthetic J01 Jev adapter conformance; no network or credentials."""

import ast
import hashlib
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin"
spec = importlib.util.spec_from_file_location("jev_decision_provider", BIN / "jev_decision_provider.py")
jev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jev)
dc = jev._contract()


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


al = _load("attempt_ledger")
kc = _load("kit_contract")
MODEL = "synthetic-model-v1"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"  # configuration only; never contacted


def _question(kind, qid, outcomes, *, sensitivity="public"):
    rubric = ({key: f"A distinct and complete description of {key} level"
               for key in outcomes} if kind != "boolean" else {})
    return {
        "id": qid, "version": "v1", "kind": kind,
        "question": f"Which defined {kind} answer best explains the supplied synthetic state?",
        "rubric": rubric, "outcomes": outcomes, "abstention": "forbidden",
        "dependencies": [], "sensitivity": sensitivity,
    }


def _request(questions=None, *, privacy="vendor-eligible", state=None,
             providers=("jev",)):
    questions = questions or [
        _question("boolean", "flag", ["false", "true"]),
        _question("choice", "category", ["alpha", "beta", "gamma"]),
        _question("ordinal", "extent", ["none", "some", "all"]),
    ]
    state = {"synthetic": "public example only"} if state is None else state
    payload = {
        "v": dc.CONTRACT_VERSION, "correlation_id": "synthetic-corr-1",
        "run": "synthetic-run", "task": "J01", "attempt": None,
        "intended_use": "shadow-comparison",
        "task_ref": al.make_ref("J01", version=kc.CONTRACT_VERSION),
        "acceptance_ref": al.make_ref("synthetic-acceptance", sha="a" * 64,
                                      version=kc.CONTRACT_VERSION),
        "state": state, "state_sha": dc.state_digest(state),
        "alternatives": ["hold"], "questions": questions,
        "questions_sha": dc.questions_digest([dc.parse_question(q) for q in questions]),
        "eligibility": {"project": "synthetic-project", "providers": list(providers),
                        "privacy": privacy},
        "deadline_s": 30,
        "resource_policy": {"operation_scope": "consult", "call_ceiling": 1,
                            "repair_ceiling": 0},
        "admission_ref": al.make_ref("synthetic-admission", version=kc.CONTRACT_VERSION),
    }
    return dc.parse_request(payload)


def _response():
    return {
        "model": MODEL,
        "answers": {
            "flag@v1": {"type": "noul", "noul": 0.8},
            "category@v1": {"type": "choice", "choice": "beta",
                            "probabilities": {"alpha": 0.1, "beta": 0.7, "gamma": 0.2},
                            "confidence": 0.6},
            "extent@v1": {"type": "score", "score": 1.1,
                          "legend": {"0": "A distinct and complete description of none level",
                                     "1": "A distinct and complete description of some level",
                                     "2": "A distinct and complete description of all level"},
                          "probabilities": {"0": 0.2, "1": 0.5, "2": 0.3},
                          "confidence": 0.4},
        },
        "usage": {"input_tokens": 12, "output_tokens": 7},
    }


def _synthetic_probe_request():
    """Public-only fixture for a possible, separately approved one-call probe."""
    should_escalate = _question("boolean", "should_escalate", ["false", "true"])
    should_escalate["question"] = (
        "Does this synthetic failure require a stronger reasoning model rather than an "
        "environment fix?")
    should_escalate["rubric"] = {
        "true": "A stronger model is required to continue the sample task.",
        "false": "The missing setting must be supplied; a stronger model is not required.",
    }
    failure_cause = _question("choice", "failure_cause",
                              ["environment", "missing_context", "capability_limit"])
    failure_cause["question"] = "Which category best explains the synthetic failure?"
    failure_cause["rubric"] = {
        "environment": "A required environment setting is absent.",
        "missing_context": "Task context is missing but the environment is ready.",
        "capability_limit": (
            "The environment and context are ready, but reasoning capacity is insufficient."),
    }
    remediation = _question("ordinal", "remediation_complexity",
                            ["simple", "moderate", "complex"])
    remediation["question"] = (
        "How complex is the next remediation step for this synthetic failure?")
    remediation["rubric"] = {
        "simple": "Supply one missing setting; no code changes.",
        "moderate": "Inspect and adjust several settings or interfaces.",
        "complex": "Design and verify a cross-module change.",
    }
    return _request(questions=[should_escalate, failure_cause, remediation],
                    state={"fixture": "synthetic-only", "failure": (
                        "A sample build stops before compiling because SAMPLE_SETTING is missing.")})


class JevProviderContractTests(unittest.TestCase):
    def assert_refused(self, code, fn, *args, **kwargs):
        with self.assertRaises(dc.ContractError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_payload_and_all_three_answer_shapes(self):
        request = _request()
        body = jev.build_payload(request, model=MODEL, endpoint=ENDPOINT)
        self.assertEqual(body["questions"]["flag@v1"]["type"], "noul")
        self.assertEqual(body["questions"]["category@v1"]["criteria"],
                         {key: f"A distinct and complete description of {key} level"
                          for key in ("alpha", "beta", "gamma")})
        self.assertEqual(body["questions"]["extent@v1"]["criteria"],
                         [f"A distinct and complete description of {key} level"
                          for key in ("none", "some", "all")])
        payload = jev.evaluate(request, model=MODEL, endpoint=ENDPOINT,
                               synthetic_response=_response())
        result = dc.parse_result(payload, request)
        self.assertEqual(result.answers["flag@v1"]["raw"], {"false": 0.19999999999999996,
                                                               "true": 0.8})
        self.assertIsNone(result.answers["flag@v1"]["vendor_confidence"])
        self.assertEqual(result.answers["category@v1"]["outcome"], "beta")
        self.assertEqual(result.answers["extent@v1"]["outcome"], "some")
        self.assertEqual(result.answers["extent@v1"]["raw"],
                         {"none": 0.2, "some": 0.5, "all": 0.3})
        self.assertIsNone(result.answers["extent@v1"]["calibrated"])
        self.assertIsNone(result.usage)
        self.assertIsNone(result.dispatched_provider)
        self.assertIsNone(result.observed_model)

    def test_accepts_a_request_parsed_by_another_contract_loader(self):
        other_contract = _load("decision_contract")
        request = other_contract.parse_request(_request().to_payload())
        payload = jev.evaluate(request, model=MODEL, endpoint=ENDPOINT,
                               synthetic_response=_response())
        self.assertEqual(other_contract.parse_result(payload, request).status, "ok")

    def test_score_tie_uses_first_declared_level(self):
        req = _request()
        response = _response()
        answer = response["answers"]["extent@v1"]
        answer["probabilities"] = {"0": 0.5, "1": 0.5, "2": 0.0}
        answer["score"] = 0.5
        mapped = jev.map_response(req, response, model=MODEL, endpoint=ENDPOINT)
        self.assertEqual(mapped["answers"]["extent@v1"]["outcome"], "none")

    def test_choice_tie_uses_first_declared_option(self):
        req = _request()
        response = _response()
        answer = response["answers"]["category@v1"]
        answer["probabilities"] = {"alpha": 0.5, "beta": 0.5, "gamma": 0.0}
        mapped = jev.map_response(req, response, model=MODEL, endpoint=ENDPOINT)
        self.assertEqual(mapped["answers"]["category@v1"]["outcome"], "alpha")

    def test_no_transport_argument_or_missing_fixture(self):
        request = _request()
        calls = []

        def stub(endpoint, body):
            calls.append((endpoint, body))
            return _response()

        with self.assertRaises(TypeError):
            jev.evaluate(request, model=MODEL, endpoint=ENDPOINT,
                         synthetic_response=_response(), transport=stub)
        self.assert_refused("missing-field", jev.evaluate, request, model=MODEL,
                            endpoint=ENDPOINT, synthetic_response=None)
        self.assertEqual(calls, [])

    def test_privacy_guards_refuse_payload_construction(self):
        self.assert_refused("unknown-value", jev.build_payload,
                            _request(providers=("rules",)), model=MODEL,
                            endpoint=ENDPOINT)
        self.assert_refused("unknown-value", jev.build_payload,
                            _request(privacy="project-local"), model=MODEL,
                            endpoint=ENDPOINT)
        for sensitivity in ("project-internal", "restricted"):
            question = _question("boolean", "flag", ["false", "true"],
                                 sensitivity=sensitivity)
            self.assert_refused("unknown-value", jev.build_payload,
                                _request(questions=[question]), model=MODEL,
                                endpoint=ENDPOINT)

    def test_malformed_distributions_and_extra_keys_rejected(self):
        req = _request()
        response = _response()
        response["answers"]["category@v1"]["probabilities"].pop("gamma")
        self.assert_refused("category-mismatch", jev.map_response, req, response,
                            model=MODEL, endpoint=ENDPOINT)
        response = _response()
        response["answers"]["flag@v1"]["confidence"] = 0.9
        self.assert_refused("value-invalid", jev.map_response, req, response,
                            model=MODEL, endpoint=ENDPOINT)
        response = _response()
        response["answers"]["extent@v1"]["score"] = 2.0
        self.assert_refused("value-invalid", jev.map_response, req, response,
                            model=MODEL, endpoint=ENDPOINT)

    def test_unsupported_score_cardinality_and_config(self):
        for count in (11, 16):
            with self.subTest(count=count):
                levels = [f"level{i}" for i in range(count)]
                req = _request(questions=[_question("ordinal", "extent", levels)])
                self.assert_refused("unknown-value", jev.build_payload, req,
                                    model=MODEL, endpoint=ENDPOINT)
        self.assert_refused("value-invalid", jev.build_payload, _request(), model=MODEL,
                            endpoint="http://example.invalid")
        self.assert_refused("value-invalid", jev.build_payload, _request(), model=MODEL,
                            endpoint="https://example.invalid/synthetic")

    def test_supported_choice_and_score_cardinality_boundaries(self):
        for count in (2, 16):
            with self.subTest(kind="choice", count=count):
                options = [f"option{i}" for i in range(count)]
                req = _request(questions=[_question("choice", "category", options)])
                body = jev.build_payload(req, model=MODEL, endpoint=ENDPOINT)
                self.assertEqual(list(body["questions"]["category@v1"]["criteria"]),
                                 options)
        for count in (2, 10):
            with self.subTest(kind="score", count=count):
                levels = [f"level{i}" for i in range(count)]
                req = _request(questions=[_question("ordinal", "extent", levels)])
                body = jev.build_payload(req, model=MODEL, endpoint=ENDPOINT)
                criteria = body["questions"]["extent@v1"]["criteria"]
                self.assertEqual(len(criteria), count)
                probabilities = {str(i): float(i == count - 1)
                                 for i in range(count)}
                response = {"model": MODEL, "answers": {
                    "extent@v1": {"type": "score", "score": count - 1,
                                  "legend": {str(i): criteria[i] for i in range(count)},
                                  "probabilities": probabilities, "confidence": 1.0}},
                    "usage": {"input_tokens": 12, "output_tokens": 7}}
                mapped = jev.map_response(req, response, model=MODEL,
                                          endpoint=ENDPOINT)
                self.assertEqual(mapped["answers"]["extent@v1"]["outcome"],
                                 levels[-1])

    def test_response_envelope_rejects_malformed_fields_without_live_identity(self):
        req = _request()
        response = _response()
        response["model"] = "synthetic-other-version"
        mapped = jev.map_response(req, response, model=MODEL, endpoint=ENDPOINT)
        self.assertEqual(mapped["requested_model"], MODEL)
        self.assertIsNone(mapped["dispatched_model"])
        self.assertIsNone(mapped["observed_model"])
        self.assertIsNone(mapped["usage"])

        for name, mutate, code in (
            ("missing answer", lambda r: r["answers"].pop("flag@v1"), "missing-answer"),
            ("extra answer", lambda r: r["answers"].update(extra={}), "missing-answer"),
            ("empty model", lambda r: r.update(model=""), "value-invalid"),
            ("negative usage", lambda r: r["usage"].update(input_tokens=-1), "value-invalid"),
            ("boolean usage", lambda r: r["usage"].update(input_tokens=True), "value-invalid"),
            ("extra usage", lambda r: r["usage"].update(billed=1), "value-invalid"),
            ("wrong answer type", lambda r: r["answers"]["flag@v1"].update(type="choice"),
             "unknown-value"),
            ("extra response field", lambda r: r.update(billed=True), "value-invalid"),
        ):
            with self.subTest(name=name):
                response = _response()
                mutate(response)
                self.assert_refused(code, jev.map_response, req, response,
                                    model=MODEL, endpoint=ENDPOINT)

    def test_untrusted_numeric_values_always_raise_contract_errors(self):
        req = _request()
        bad_values = (("nan", float("nan")), ("infinity", float("inf")),
                      ("negative", -0.1), ("above one", 1.1),
                      ("boolean", True), ("huge integer", 10 ** 400))
        for name, value in bad_values:
            with self.subTest(field="noul", value=name):
                response = _response()
                response["answers"]["flag@v1"]["noul"] = value
                self.assert_refused("value-invalid", jev.map_response, req,
                                    response, model=MODEL, endpoint=ENDPOINT)
            with self.subTest(field="choice confidence", value=name):
                response = _response()
                response["answers"]["category@v1"]["confidence"] = value
                self.assert_refused("value-invalid", jev.map_response, req,
                                    response, model=MODEL, endpoint=ENDPOINT)
        for name, value in (("nan", float("nan")), ("infinity", float("inf")),
                            ("boolean", True), ("huge integer", 10 ** 400)):
            with self.subTest(field="score", value=name):
                response = _response()
                response["answers"]["extent@v1"]["score"] = value
                self.assert_refused("value-invalid", jev.map_response, req,
                                    response, model=MODEL, endpoint=ENDPOINT)

    def test_distributions_and_score_semantics_fail_closed(self):
        req = _request()
        for name, mutate, code in (
            ("choice sum", lambda a: a["probabilities"].update(beta=0.8), "value-invalid"),
            ("choice extra option", lambda a: a["probabilities"].update(delta=0.0),
             "category-mismatch"),
            ("choice nonmaximum", lambda a: a.update(choice="alpha"), "value-invalid"),
            ("choice invalid probability", lambda a: a["probabilities"].update(beta=True),
             "value-invalid"),
        ):
            with self.subTest(name=name):
                response = _response()
                mutate(response["answers"]["category@v1"])
                self.assert_refused(code, jev.map_response, req, response,
                                    model=MODEL, endpoint=ENDPOINT)
        for name, mutate, code in (
            ("score missing level", lambda a: a["probabilities"].pop("2"),
             "category-mismatch"),
            ("score legend", lambda a: a["legend"].update({"1": "wrong"}),
             "category-mismatch"),
            ("score weighted value", lambda a: a.update(score=1.2), "value-invalid"),
            ("score confidence", lambda a: a.update(confidence=1.1), "value-invalid"),
        ):
            with self.subTest(name=name):
                response = _response()
                mutate(response["answers"]["extent@v1"])
                self.assert_refused(code, jev.map_response, req, response,
                                    model=MODEL, endpoint=ENDPOINT)

    def test_adapter_source_has_no_network_or_credential_imports(self):
        source = (BIN / "jev_decision_provider.py").read_text(encoding="utf-8")
        syntax = ast.parse(source)
        imported = []
        for node in ast.walk(syntax):
            if isinstance(node, ast.Import):
                imported.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module.split(".")[0])
        forbidden = {"os", "socket", "http", "urllib", "requests", "httpx",
                     "subprocess", "dotenv", "typesafe_sdk"}
        self.assertFalse(forbidden.intersection(imported))
        forbidden_calls = {"open", "home", "expanduser", "read_text", "read_bytes",
                           "getenv", "urlopen", "connect", "Popen"}
        calls = (node.func for node in ast.walk(syntax) if isinstance(node, ast.Call))
        self.assertFalse(forbidden_calls.intersection(
            node.id if isinstance(node, ast.Name) else node.attr
            for node in calls if isinstance(node, (ast.Name, ast.Attribute))))
        self.assertEqual(jev.evaluate.__code__.co_kwonlyargcount, 3)

    def test_proposed_probe_payload_is_exact_public_synthetic_fixture(self):
        request = _synthetic_probe_request()
        doc = (ROOT / "docs" / "JEV-ACCESS-CONTRACT.md").read_text(encoding="utf-8")
        start = "<!-- jev-probe-payload:start -->\n```json\n"
        end = "\n```\n<!-- jev-probe-payload:end -->"
        self.assertEqual(doc.count(start), 1)
        self.assertEqual(doc.count(end), 1)
        documented = doc.split(start, 1)[1].split(end, 1)[0]
        model = json.loads(documented)["model"]
        self.assertRegex(model, r"\Ajev-[0-9]+\.[0-9]+\.[0-9]+\Z")
        body = jev.build_payload(request, model=model, endpoint=ENDPOINT)
        self.assertEqual([item["type"] for item in body["questions"].values()],
                         ["noul", "choice", "score"])
        self.assertEqual(body["state"]["fixture"], "synthetic-only")
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        encoded = jev.serialize_payload(request, model=model, endpoint=ENDPOINT)
        self.assertEqual(encoded, canonical.encode("utf-8"))
        self.assertLessEqual(len(encoded), 2048)
        self.assertEqual(documented, canonical)
        documented_size = re.search(r"\*\*([0-9,]+) bytes\*\*", doc)
        documented_digest = re.search(r"SHA-256 `([0-9a-f]{64})`", doc)
        self.assertIsNotNone(documented_size)
        self.assertIsNotNone(documented_digest)
        self.assertEqual(len(encoded), int(documented_size.group(1).replace(",", "")))
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), documented_digest.group(1))

        score_criteria = body["questions"]["remediation_complexity@v1"]["criteria"]
        response = {"model": model, "answers": {
            "should_escalate@v1": {"type": "noul", "noul": 0.05},
            "failure_cause@v1": {
                "type": "choice", "choice": "environment",
                "probabilities": {"environment": 0.8, "missing_context": 0.1,
                                  "capability_limit": 0.1}, "confidence": 0.7},
            "remediation_complexity@v1": {
                "type": "score", "score": 0.3,
                "legend": {str(i): item for i, item in enumerate(score_criteria)},
                "probabilities": {"0": 0.7, "1": 0.3, "2": 0.0},
                "confidence": 0.6}},
            "usage": {"input_tokens": 900, "output_tokens": 50}}
        mapped = jev.map_response(request, response, model=model, endpoint=ENDPOINT)
        result = dc.parse_result(mapped, request)
        self.assertEqual(result.answers["should_escalate@v1"]["outcome"], "false")
        self.assertEqual(result.answers["failure_cause@v1"]["outcome"], "environment")
        self.assertEqual(result.answers["remediation_complexity@v1"]["outcome"], "simple")
        self.assertIsNone(result.observed_model)
        self.assertIsNone(result.usage)

    def test_wire_bytes_are_stable_across_state_key_order(self):
        first = _request(state={"fixture": "synthetic", "signal": "example"})
        second = _request(state={"signal": "example", "fixture": "synthetic"})
        self.assertEqual(jev.serialize_payload(first, model=MODEL, endpoint=ENDPOINT),
                         jev.serialize_payload(second, model=MODEL, endpoint=ENDPOINT))


if __name__ == "__main__":
    unittest.main()
