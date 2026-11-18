"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def _label(value: str) -> str:
    return str(value).strip().upper()


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError(f"human and judge labels differ in length: {len(human)} != {len(judge)}")
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for h, j in zip(human, judge):
        h, j = _label(h), _label(j)
        if h == POS:
            cm["tp" if j == POS else "fn"] += 1
        else:
            cm["fp" if j == POS else "tn"] += 1
    return cm


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    precision = cm["tp"] / (cm["tp"] + cm["fp"]) if cm["tp"] + cm["fp"] else 0.0
    recall = cm["tp"] / (cm["tp"] + cm["fn"]) if cm["tp"] + cm["fn"] else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    n = len(human)
    if n == 0 or n != len(judge):
        raise ValueError("kappa undefined for empty or mismatched label lists")
    cm = confusion(human, judge)
    p_observed = (cm["tp"] + cm["tn"]) / n
    p_fail_human = (cm["tp"] + cm["fn"]) / n
    p_fail_judge = (cm["tp"] + cm["fp"]) / n
    p_expected = p_fail_human * p_fail_judge + (1 - p_fail_human) * (1 - p_fail_judge)
    if 1 - p_expected == 0:
        raise ValueError("kappa undefined: p_e == 1 (constant judge has no signal)")
    return (p_observed - p_expected) / (1 - p_expected)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denominator = sensitivity + specificity - 1
    corrected = observed_rate if denominator == 0 else (observed_rate + specificity - 1) / denominator
    return min(1.0, max(0.0, corrected))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy.stats import bootstrap

    left = np.asarray(list(a), dtype=float)
    right = np.asarray(list(b), dtype=float)
    if left.shape != right.shape:
        raise ValueError(f"paired samples differ in length: {left.size} != {right.size}")
    if left.size == 0:
        return (0.0, 0.0, 0.0)
    delta = float(left.mean() - right.mean())
    if np.array_equal(left, right):
        return (0.0, 0.0, 0.0)
    result = bootstrap(
        (left, right),
        lambda x, y: np.mean(x) - np.mean(y),
        paired=True,
        vectorized=False,
        n_resamples=n_resamples,
        method="percentile",
        confidence_level=confidence,
        rng=np.random.default_rng(rng),
    )
    interval = result.confidence_interval
    return (delta, float(interval.low), float(interval.high))


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    # TODO M6
    raise NotImplementedError


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    # TODO M6
    raise NotImplementedError
