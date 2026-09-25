"""Synthetic J01 Jev adapter conformance; no network or credentials."""

import importlib.util
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


def _request(questions=None, *, privacy="vendor-eligible", state=None):
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
        "eligibility": {"project": "synthetic-project", "providers": ["jev"],
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
        levels = [f"level{i}" for i in range(11)]
        req = _request(questions=[_question("ordinal", "extent", levels)])
        self.assert_refused("unknown-value", jev.build_payload, req, model=MODEL,
                            endpoint=ENDPOINT)
        self.assert_refused("value-invalid", jev.build_payload, _request(), model=MODEL,
                            endpoint="http://example.invalid")
        self.assert_refused("value-invalid", jev.build_payload, _request(), model=MODEL,
                            endpoint="https://example.invalid/synthetic")


if __name__ == "__main__":
    unittest.main()
