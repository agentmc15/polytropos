#!/usr/bin/env python3
"""Central Codex orchestration and worker-assignment policy.

All model identities and tier bindings come from ``data/pricing.codex.json``.  This
module is deliberately pure: the execution driver owns process dispatch and logging.
"""

TIER_ORDER = ("cheap", "mid", "strong", "frontier")


class PolicyError(ValueError):
    """The requested assignment would violate the configured orchestration policy."""


def _policy(pricing):
    policy = pricing.get("orchestration_policy")
    if not isinstance(policy, dict):
        raise PolicyError("pricing data has no orchestration_policy; execution is disabled")
    return policy


def _available(info):
    return info.get("available", True) is not False


def resolve_orchestrator(pricing):
    """Return the configured orchestration model, or fail closed."""
    policy = _policy(pricing)
    model_id = policy.get("orchestrator_model")
    models = pricing.get("models", {})
    if not isinstance(model_id, str) or not model_id:
        raise PolicyError("orchestration_policy.orchestrator_model is missing")
    info = models.get(model_id)
    if not isinstance(info, dict):
        raise PolicyError(
            f"configured orchestrator {model_id!r} is absent from the Codex roster; execution is disabled"
        )
    if not _available(info):
        raise PolicyError(f"configured orchestrator {model_id!r} is unavailable; execution is disabled")
    if info.get("tier") != policy.get("orchestrator_tier"):
        raise PolicyError(f"configured orchestrator {model_id!r} does not occupy the reserved tier")
    return model_id


def _first_model(pricing, tier):
    reserved = resolve_orchestrator(pricing)
    for model_id, info in pricing.get("models", {}).items():
        if model_id != reserved and info.get("tier") == tier and _available(info):
            return model_id
    raise PolicyError(f"no available Codex worker is configured for tier {tier!r}")


def _resolve_worker_tier(pricing, tier):
    """Resolve a worker tier, skipping upward only within the worker ladder."""
    tiers = _worker_tiers(pricing)
    if tier not in tiers:
        raise PolicyError(f"tier {tier!r} is not eligible for ordinary implementation")
    for candidate in tiers[tiers.index(tier):]:
        try:
            return _first_model(pricing, candidate)
        except PolicyError as exc:
            if "no available Codex worker" not in str(exc):
                raise
    raise PolicyError(f"no available Codex worker exists at or above tier {tier!r}")


def _worker_tiers(pricing):
    tiers = _policy(pricing).get("worker_tiers")
    orchestrator_tier = _policy(pricing).get("orchestrator_tier")
    if (
        not isinstance(tiers, list) or not tiers
        or len(set(tiers)) != len(tiers)
        or any(t not in TIER_ORDER for t in tiers)
        or orchestrator_tier in tiers
        or tiers != sorted(tiers, key=TIER_ORDER.index)
    ):
        raise PolicyError("orchestration_policy.worker_tiers is missing or invalid")
    return tiers


def validate_recovery(evidence, pricing=None):
    """Validate machine-visible evidence that unlocks direct recovery work."""
    if not isinstance(evidence, dict):
        raise PolicyError("Astra recovery requires structured machine-visible failure evidence")
    task_id = evidence.get("task_id")
    attempts = evidence.get("attempts")
    if not isinstance(task_id, str) or not task_id.strip():
        raise PolicyError("recovery evidence requires a task_id")
    if not isinstance(attempts, list) or not attempts:
        raise PolicyError("recovery evidence requires at least one prior lower-tier attempt")
    if any(not isinstance(a, dict) or not a.get("dispatched_model") for a in attempts):
        raise PolicyError("every recovery attempt must identify its dispatched_model")
    if pricing is not None:
        orchestrator = resolve_orchestrator(pricing)
        if any(a["dispatched_model"] == orchestrator for a in attempts):
            raise PolicyError("Astra cannot count as a prior lower-tier recovery attempt")

    kind = evidence.get("kind")
    if pricing is not None:
        configured_kinds = _policy(pricing).get("recovery_evidence_kinds")
        if not isinstance(configured_kinds, list) or kind not in configured_kinds:
            raise PolicyError("recovery evidence kind is not enabled by orchestration_policy")
        workers = set(eligible_models(pricing, "implementer"))
        unknown = [a["dispatched_model"] for a in attempts if a["dispatched_model"] not in workers]
        if unknown:
            raise PolicyError(
                "recovery attempts must be available eligible workers; invalid: "
                + ", ".join(unknown)
            )
    if kind == "verify_failure":
        rc = evidence.get("verify_exit_code")
        if not isinstance(rc, int) or isinstance(rc, bool) or rc == 0:
            raise PolicyError("verify_failure requires a nonzero integer verify_exit_code")
    elif kind == "integration_conflict":
        if (
            evidence.get("unresolved") is not True
            or not evidence.get("conflict_id")
            or not isinstance(evidence.get("details"), str)
            or not evidence["details"].strip()
        ):
            raise PolicyError(
                "integration_conflict requires unresolved=true, conflict_id, and nonempty details"
            )
    elif kind == "lower_tier_correction_failed":
        final = attempts[-1]
        failed = final.get("result") in {"failed", "blocked"}
        failed = failed or (
            isinstance(final.get("verify_exit_code"), int)
            and not isinstance(final.get("verify_exit_code"), bool)
            and final["verify_exit_code"] != 0
        )
        if not failed:
            raise PolicyError("lower_tier_correction_failed requires a failed final attempt")
    else:
        raise PolicyError("unsupported recovery evidence kind")
    return dict(evidence)


def resolve_assignment(pricing, planned_model=None, role="implementer", evidence=None):
    """Resolve a planned assignment under the reserved-orchestrator invariant."""
    orchestrator = resolve_orchestrator(pricing)  # fail closed even for worker dispatch
    policy = _policy(pricing)
    requested = planned_model
    migration = None
    normalized_evidence = None

    if role in {"orchestrator", "coordinator"}:
        resolved_role, model_id = "orchestrator", orchestrator
    elif role == "recovery":
        normalized_evidence = validate_recovery(evidence, pricing=pricing)
        resolved_role, model_id = "recovery", orchestrator
    elif role in {"verifier", "independent_verifier"}:
        tier = policy.get("verification_tier")
        if tier not in _worker_tiers(pricing):
            raise PolicyError("verification_tier must name a configured worker tier")
        resolved_role, model_id = "verifier", _resolve_worker_tier(pricing, tier)
    elif role == "implementer":
        worker_tiers = _worker_tiers(pricing)
        if planned_model is None:
            tier = policy.get("default_worker_tier")
            migration = "legacy-unpinned-to-default-worker"
        elif planned_model == policy.get("orchestrator_tier"):
            tier = policy.get("maximum_worker_tier")
            migration = "legacy-reserved-tier-to-maximum-worker"
        elif planned_model in TIER_ORDER:
            tier = planned_model
        elif planned_model in pricing.get("models", {}):
            if planned_model == orchestrator:
                raise PolicyError("the reserved orchestrator cannot perform ordinary implementation")
            tier = pricing["models"][planned_model].get("tier")
        else:
            raise PolicyError(f"unknown planned Codex model or tier {planned_model!r}")
        if tier not in worker_tiers:
            raise PolicyError(f"tier {tier!r} is not eligible for ordinary implementation")
        resolved_role, model_id = "implementer", _resolve_worker_tier(pricing, tier)
        if planned_model in pricing.get("models", {}) and planned_model != model_id:
            # Exact worker pins remain exact when available.
            info = pricing["models"][planned_model]
            if info.get("tier") == tier and _available(info):
                model_id = planned_model
    else:
        raise PolicyError(f"unknown Codex assignment role {role!r}")

    return {
        "requested": requested,
        "planned": planned_model,
        "resolved_role": resolved_role,
        "model_id": model_id,
        "migration": migration,
        "recovery_evidence": normalized_evidence,
    }


def eligible_models(pricing, role):
    """List models eligible for a role without treating eligibility as recovery evidence."""
    orchestrator = resolve_orchestrator(pricing)
    models = pricing.get("models", {})
    if role in {"orchestrator", "coordinator", "recovery"}:
        return [orchestrator]
    if role in {"verifier", "independent_verifier"}:
        tier = _policy(pricing).get("verification_tier")
        return [mid for mid, info in models.items()
                if mid != orchestrator and info.get("tier") == tier and _available(info)]
    if role == "implementer":
        tiers = set(_worker_tiers(pricing))
        return [mid for mid, info in models.items()
                if mid != orchestrator and info.get("tier") in tiers and _available(info)]
    raise PolicyError(f"unknown Codex assignment role {role!r}")


def policy_status(pricing):
    """Return diagnostic policy state without weakening fail-closed assignment behavior."""
    try:
        orchestrator = resolve_orchestrator(pricing)
        workers = eligible_models(pricing, "implementer")
    except PolicyError as exc:
        return {"ready": False, "orchestrator_model": None, "worker_models": [], "error": str(exc)}
    policy = _policy(pricing)
    return {
        "ready": True,
        "orchestrator_model": orchestrator,
        "orchestrator_pool": policy.get("orchestrator_pool", "reserved"),
        "worker_models": workers,
        "verification_models": eligible_models(pricing, "verifier"),
        "actual_usage_separate_from_plan": policy.get("actual_usage_separate_from_plan") is True,
        "error": None,
    }


def worker_ladder(pricing, model_id):
    """Return available higher-capability workers, excluding the orchestrator."""
    resolve_orchestrator(pricing)
    tiers = _worker_tiers(pricing)
    info = pricing.get("models", {}).get(model_id)
    if not info or info.get("tier") not in tiers:
        raise PolicyError(f"{model_id!r} is not an eligible worker")
    start = tiers.index(info["tier"])
    ladder = []
    for tier in tiers[start + 1:]:
        try:
            ladder.append(_first_model(pricing, tier))
        except PolicyError as exc:
            if "no available Codex worker" not in str(exc):
                raise
    return ladder


# ---- named routing policies (step 19) -------------------------------------------------------------
#
# Everything above is the RESERVED policy: Astra held back for orchestration, acceptance, and
# evidence-gated recovery; workers for implementation; a frontier plan migrated down; and --
# measured before this section existed -- every worker assignment coupled to the orchestrator
# resolving, so `resolve_assignment(pricing, "mid")` raised "execution is disabled" when Astra
# was marked unavailable, though the mid worker needed nothing from Astra. That behaviour keeps
# its name and stays the default. `route` puts a second, opt-in policy beside it, ADAPTIVE,
# which reads the roster directly (never through `resolve_orchestrator`) and may send a hard
# task straight to an eligible capable model, the frontier included, without a failed cheaper
# attempt first. The decision shape, filters, and explanation live in `bin/routing_policy.py`
# and are harness-neutral; this section is the Codex catalog and the Codex request.

_ROUTING = None
_CAPABILITIES = None
_PRICING_ENGINE = None


def _sibling(name):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"polytropos_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rp():
    global _ROUTING
    if _ROUTING is None:
        _ROUTING = _sibling("routing_policy")
    return _ROUTING


def catalog(pricing, estimator=None):
    """The Codex roster as harness-neutral catalog rows, straight from the pricing dict.

    Never calls `resolve_orchestrator`: the reserved model is a ROW with `reserved=True`, and
    whether that row may implement is the policy's decision, not the catalog's. Cost-only and
    non-routing entries are present and marked not routable, so an explanation can name them.
    """
    policy = pricing.get("orchestration_policy") or {}
    return _rp().catalog_from_pricing(
        pricing, "codex", TIER_ORDER, reserved_model=policy.get("orchestrator_model"),
        estimator=estimator,
    )


def default_estimator(pricing, profile):
    """The pricing engine's own per-model estimate for `profile`, or None with no profile.

    `codex_pricing.est_cost` is the ONE source of Codex dollar figures; this only adapts its
    return shape. A subscription run has no bill, so the figure is API-equivalent and the
    decision labels it so. No profile, no estimate: a size assumption is not something to
    invent silently.
    """
    if not profile:
        return None
    global _PRICING_ENGINE
    if _PRICING_ENGINE is None:
        _PRICING_ENGINE = _sibling("codex_pricing")
    if profile not in (pricing.get("task_profiles") or {}):
        raise PolicyError(
            f"unknown task profile {profile!r}; valid: {sorted(pricing.get('task_profiles') or {})}"
        )

    def estimate(model_id):
        cost = _PRICING_ENGINE.est_cost(pricing, profile, model_id)
        return {"api_equivalent_usd": cost["usd_api"], "profile": profile}

    return estimate


def capability_states():
    """`{name: effective state}` for the Codex adapter from the shared registry, or `{}`."""
    global _CAPABILITIES
    if _CAPABILITIES is None:
        try:
            ha = _sibling("harness_adapter")
            rows = ha.registry_capabilities("codex")
            _CAPABILITIES = {name: ha.effective(row) for name, row in rows.items()}
        except (OSError, ValueError, KeyError, AttributeError):
            _CAPABILITIES = {}
    return dict(_CAPABILITIES)


def _first_available(pricing, tier, exclude=()):
    for model_id, info in pricing.get("models", {}).items():
        if model_id not in exclude and info.get("tier") == tier and _available(info):
            return model_id
    return None


def request_for(task, role="implementer", effort=None, profile=None, prior_failures=0,
                in_kit=True, budget=None, shape=None, pricing=None):
    """The routing request for one task: its signals, plus what the Codex catalog needs.

    `pricing` fills the harness facts (tier order, default worker tier, the review and
    acceptance models when available). Nothing here is a decision; it is what the decision
    is made from, and it is recorded beside the decision so the explanation is complete.
    """
    policy = (pricing or {}).get("orchestration_policy") or {}
    orchestrator = policy.get("orchestrator_model")
    orch_info = (pricing or {}).get("models", {}).get(orchestrator) if orchestrator else None
    return {
        "harness": "codex",
        "task_id": task.get("id"),
        "planned": task.get("model"),
        "role": role,
        "effort": effort,
        "profile": profile,
        "prior_failures": int(prior_failures or 0),
        "evidence": task.get("evidence"),
        "brief_chars": len(task.get("brief") or ""),
        "excludes": [],
        "budget": budget,
        "capabilities": capability_states(),
        "tiers": TIER_ORDER,
        "default_tier": policy.get("default_worker_tier"),
        "in_kit": bool(in_kit),
        "shape": shape,
        "review_model": _first_available(pricing or {}, policy.get("verification_tier"),
                                         exclude=(orchestrator,) if orchestrator else ()),
        "acceptance_model": orchestrator if (orch_info and _available(orch_info)) else None,
    }


def route(pricing, request, policy=None, preference=None, estimator=None):
    """Route one request under a named policy -> a `routing_policy` decision.

    `reserved` (the default) keeps every existing rule by delegating the model to
    `resolve_assignment` and the ladder to `worker_ladder`, then records and explains that
    pick; it still fails closed when the orchestrator is unavailable, exactly as before.
    `adaptive` routes from the catalog: hard filters, then the preference; the reserved row is
    an ordinary candidate; an unavailable orchestrator disables nothing a worker path does not
    need. Roles other than implementer route as reserved under both policies -- verification
    and acceptance assignments are the policy's, not the task's.
    """
    rp = _rp()
    policy = policy or rp.DEFAULT_POLICY
    preference = preference or rp.DEFAULT_PREFERENCE
    if policy not in rp.POLICIES:
        raise PolicyError(f"unknown routing policy {policy!r}; valid: {', '.join(rp.POLICIES)}")
    if preference not in rp.PREFERENCES:
        raise PolicyError(
            f"unknown routing preference {preference!r}; valid: {', '.join(rp.PREFERENCES)}"
        )
    if estimator is None and request.get("profile"):
        estimator = default_estimator(pricing, request["profile"])
    rows = catalog(pricing, estimator=estimator)
    role = request.get("role", "implementer")
    if policy == "reserved" or role != "implementer":
        assignment = resolve_assignment(pricing, request.get("planned"), role=role)
        ladder = (worker_ladder(pricing, assignment["model_id"])
                  if assignment["resolved_role"] == "implementer" else [])
        decision = rp.decide(rows, request, policy="reserved", preference=preference,
                             chosen=assignment["model_id"], ladder=ladder)
        decision["assignment"] = {**assignment, "policy": "reserved"}
        if policy != "reserved":
            decision["shape_notes"] = list(decision["shape_notes"]) + [
                f"role {role} routes as reserved under every policy"
            ]
        return decision
    try:
        decision = rp.decide(rows, request, policy="adaptive", preference=preference)
    except rp.RoutingError as exc:
        raise PolicyError(str(exc)) from exc
    decision["assignment"] = {
        "requested": request.get("planned"),
        "planned": request.get("planned"),
        "resolved_role": "implementer",
        "model_id": decision["model"],
        "migration": None,
        "recovery_evidence": None,
        "policy": "adaptive",
    }
    return decision
