#!/usr/bin/env python3
"""Statistics for trigger-eval comparisons.

Pure functions, no I/O, stdlib only. Every accept/reject verdict in the
description-optimization loop routes through this module, which is why it is
separated out: these are the only parts of the system that can be checked without
spending money on nested `claude -p` sessions.

The problem this exists to prevent: at the historical default of 3 runs per query
over 10 positive queries, two descriptions must differ by 25 percentage points of
trigger mass before the difference is readable. A run that reports "16/20 vs 14/20"
at that sample size is reporting noise, and acting on it means adopting a
description on the strength of four coin flips.

Self-check:

    python3 -m scripts.stats                     # unit tests
    python3 -m scripts.stats a.json b.json ...   # replay stored eval results
"""

import json
import math
import sys

Z95 = 1.96


def counts(row: dict, default_runs: int | None = None) -> tuple[int, int]:
    """(triggers, runs) for one query, tolerating both result shapes.

    `run_eval.py` writes `triggers` and `runs` directly, where `runs` already
    excludes runs lost to contamination. Older files carry only `trigger_rate`
    plus a `fired` list with one entry per run.
    """
    if "triggers" in row and "runs" in row:
        return int(row["triggers"]), int(row["runs"])

    fired = row.get("fired")
    n = len(fired) if isinstance(fired, list) else default_runs
    if not n:
        raise ValueError(
            f"cannot determine run count for query {row.get('query', '?')!r}: "
            "no 'runs', no 'fired' list, and no default supplied"
        )
    return round(row["trigger_rate"] * n), n


def aggregate_rate(
    results: list[dict], positives_only: bool = True, default_runs: int | None = None
) -> tuple[float, int]:
    """Trigger rate over all observations, and the observation count.

    Weighted by observations rather than averaged over queries. Two reasons: a
    query whose runs were lost to contamination contributes proportionally less
    instead of distorting the mean, and the result is a straight Bernoulli
    proportion, so the confidence interval below is the right one for it.

    Defaults to positives because over-triggering is a separate, one-sided
    question that is cheap to measure and usually already settled.
    """
    rows = [r for r in results if r["should_trigger"]] if positives_only else list(results)
    triggers = 0
    n = 0
    for row in rows:
        t, runs = counts(row, default_runs)
        triggers += t
        n += runs
    return (triggers / n if n else 0.0), n


def wilson_ci(rate: float, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a proportion.

    Wilson rather than the normal approximation because trigger rates sit at 0.0
    and 1.0 constantly -- every near-miss query in a healthy eval set scores 0.00.
    The normal approximation returns a zero-width interval there, and can return
    bounds below 0 or above 1 nearby. Wilson stays inside [0, 1] and keeps a
    sensible width at the extremes. At p=0.5 the two agree.
    """
    if n <= 0:
        return 0.0, 1.0
    denom = 1 + z * z / n
    center = (rate + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n))
    return max(0.0, center - half), min(1.0, center + half)


def mde(n_obs: int, p: float = 0.5, z: float = Z95) -> float:
    """Minimum detectable effect between two arms of `n_obs` observations each.

    Fixed p=0.5 by default, which maximises Bernoulli variance and therefore
    reports the worst-case detection floor. Estimating p from the data would
    report a smaller, more flattering floor exactly when the observed rates are
    extreme and least stable -- i.e. when the flattery is least deserved.
    """
    if n_obs <= 0:
        return 1.0
    # Capped at 1.0: the effect is a difference of proportions, so it cannot
    # exceed 1.0 however small the sample. Uncapped, tiny n reports a "detectable
    # difference" of 1.39, which reads as a number rather than as "this sample
    # can detect nothing".
    return min(1.0, z * math.sqrt(2 * p * (1 - p) / n_obs))


def compare(
    incumbent: tuple[float, int], candidate: tuple[float, int], z: float = Z95
) -> dict:
    """Verdict on whether `candidate` beats `incumbent`.

    The verdict uses the conservative fixed-variance floor from `mde()`, not the
    interval derived from the observed rates. That is deliberate: the loop
    optimizes for not shipping a false positive, and the observed-variance test
    is the more permissive of the two whenever rates are away from 0.5. The
    observed interval is still reported as `delta_ci`, and
    `significant_by_observed` flags the cases where the two tests disagree --
    which is the signal to collect more runs, not to overrule the floor.
    """
    p_inc, n_inc = incumbent
    p_can, n_can = candidate
    delta = p_can - p_inc
    floor = mde(min(n_inc, n_can), z=z)

    se_diff = math.sqrt(
        (p_inc * (1 - p_inc) / n_inc if n_inc else 0.25)
        + (p_can * (1 - p_can) / n_can if n_can else 0.25)
    )
    lo, hi = delta - z * se_diff, delta + z * se_diff

    if delta > floor:
        verdict = "improved"
    elif delta < -floor:
        verdict = "worse"
    else:
        verdict = "inconclusive"

    return {
        "verdict": verdict,
        "delta": delta,
        "mde": floor,
        "delta_ci": (lo, hi),
        "significant_by_observed": lo > 0 or hi < 0,
        "incumbent": {"rate": p_inc, "n": n_inc, "ci": wilson_ci(p_inc, n_inc, z)},
        "candidate": {"rate": p_can, "n": n_can, "ci": wilson_ci(p_can, n_can, z)},
    }


def runs_needed(target_effect: float, p: float = 0.5, z: float = Z95) -> int:
    """Observations per arm required to detect `target_effect`.

    Inverse of `mde()`. Preflight uses this to turn "what improvement is worth
    detecting?" into a session count before anything is spent.
    """
    if target_effect <= 0:
        raise ValueError("target_effect must be positive")
    return math.ceil(2 * p * (1 - p) * (z / target_effect) ** 2)


# --------------------------------------------------------------------------
# Self-check
# --------------------------------------------------------------------------

def _test() -> None:
    def close(a, b, tol=1e-3):
        assert abs(a - b) < tol, f"{a} != {b}"

    # MDE at the sample sizes that matter. 3 runs x 10 positives = 30.
    close(mde(30), 0.2530)
    close(mde(100), 0.1386)
    close(mde(200), 0.0980)
    assert mde(0) == 1.0
    # Never exceeds 1.0 -- a difference of proportions is bounded. Uncapped,
    # mde(1) would be 1.386; mde(2) is 0.98 and needs no cap.
    assert mde(1) == 1.0
    close(mde(2), 0.98)
    # A sample that can detect nothing can never yield a verdict.
    assert compare((0.0, 1), (1.0, 1))["verdict"] == "inconclusive"

    # 0.10 target -> ~192 observations per arm -> 20 runs over 10 positives.
    assert runs_needed(0.10) == 193, runs_needed(0.10)
    assert mde(runs_needed(0.10)) <= 0.10

    # Wilson agrees with the normal approximation at p=0.5 ...
    lo, hi = wilson_ci(0.5, 200)
    close(lo, 0.4307)
    close(hi, 0.5693)
    # ... and stays inside [0, 1] at the extremes, where the normal one does not.
    lo, hi = wilson_ci(0.0, 30)
    assert lo == 0.0 and 0.0 < hi < 0.15, (lo, hi)
    lo, hi = wilson_ci(1.0, 30)
    assert hi == 1.0 and 0.85 < lo < 1.0, (lo, hi)

    # Observation-weighted aggregate, both result shapes.
    new_shape = [
        {"should_trigger": True, "triggers": 6, "runs": 10},
        {"should_trigger": True, "triggers": 2, "runs": 5},   # lost runs
        {"should_trigger": False, "triggers": 0, "runs": 10},  # excluded
    ]
    rate, n = aggregate_rate(new_shape)
    close(rate, 8 / 15)
    assert n == 15
    # Averaging over queries instead would give (0.6+0.4)/2 = 0.5, not 0.533.

    legacy = [
        {"should_trigger": True, "trigger_rate": 1.0, "fired": ["s", "s", "s"]},
        {"should_trigger": True, "trigger_rate": 0.0, "fired": ["", "", ""]},
    ]
    rate, n = aggregate_rate(legacy)
    close(rate, 0.5)
    assert n == 6

    # Verdict boundaries.
    r = compare((0.500, 200), (0.615, 200))
    assert r["verdict"] == "improved", r
    r = compare((0.500, 200), (0.525, 200))
    assert r["verdict"] == "inconclusive", r
    r = compare((0.615, 200), (0.400, 200))
    assert r["verdict"] == "worse", r

    # The case this module exists for: identical rates are never a win.
    r = compare((0.500, 30), (0.500, 30))
    assert r["verdict"] == "inconclusive" and r["delta"] == 0.0

    # And the apparent "2-point win" from 2026-08-06 is not one.
    r = compare((0.400, 30), (0.500, 30))
    assert r["verdict"] == "inconclusive", r
    close(r["delta"], 0.100)
    close(r["mde"], 0.2530)

    print("stats.py: all checks passed")


def _replay(paths: list[str]) -> None:
    """Recompute verdicts from stored eval-result files, spending nothing."""
    arms = {}
    for path in paths:
        data = json.loads(open(path).read())
        results = data["results"] if isinstance(data, dict) else data
        default_runs = data.get("runs_per_query") if isinstance(data, dict) else None
        rate, n = aggregate_rate(results, default_runs=default_runs)
        lo, hi = wilson_ci(rate, n)
        arms[path] = (rate, n)
        print(f"{path}\n  positive rate {rate:.3f}  [{lo:.3f}-{hi:.3f}]  n={n}")

    names = list(arms)
    if len(names) < 2:
        return
    print()
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            r = compare(arms[names[i]], arms[names[j]])
            lo, hi = r["delta_ci"]
            print(
                f"{names[i]}\n  vs {names[j]}\n"
                f"  delta {r['delta']:+.3f}  [{lo:+.3f},{hi:+.3f}]  "
                f"MDE {r['mde']:.3f}  -> {r['verdict'].upper()}"
            )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        _replay(sys.argv[1:])
    else:
        _test()
