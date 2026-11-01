"""Shared arithmetic for fixed binary betting experiments, with flat unit stakes."""
from collections import defaultdict
from decimal import Decimal
import math
import random


def logistic(x):
    return 1 / (1 + math.exp(-x))


def fit_intercept(rows, positive_key, negative_key):
    """MLE offset calibration, using only the explicitly supplied training rows."""
    if not rows or not 0 < sum(r["win"] for r in rows) < len(rows):
        raise ValueError("Calibration needs both outcomes in a nonempty training set")
    low, high = -20.0, 20.0
    for _ in range(80):
        mid = (low + high) / 2
        residual = sum(logistic(math.log(r[negative_key] / r[positive_key]) + mid) - r["win"] for r in rows)
        if residual > 0:
            high = mid
        else:
            low = mid
    return (low + high) / 2


def split_by_date(rows):
    """First 2/3 of rows, moving the entire boundary date into the later period."""
    if len(rows) < 3:
        raise ValueError("Insufficient observations for chronological evaluation")
    if rows != sorted(rows, key=lambda r: (r["start_time_source"], r["match_row_id"])):
        raise ValueError("Observations must be sorted chronologically")
    cutoff = rows[len(rows) * 2 // 3]["start_time_source"][:10]
    train = [r for r in rows if r["start_time_source"][:10] < cutoff]
    later = [r for r in rows if r["start_time_source"][:10] >= cutoff]
    if not train or not later:
        raise ValueError("Chronological split needs at least two distinct dates")
    return cutoff, train, later


def summarize(rows, positive_key, *, bootstrap_iterations=10000):
    n = len(rows)
    if any(r["win"] not in (0, 1) or not math.isfinite(r[positive_key]) or r[positive_key] <= 1 for r in rows):
        raise ValueError("Expected binary outcomes and finite decimal odds > 1")
    wins = sum(r["win"] for r in rows)
    payouts = sum((Decimal(str(r[positive_key])) for r in rows if r["win"]), Decimal(0))
    profit = payouts - n
    if abs(float(profit) - sum(r["win"] * r[positive_key] - 1 for r in rows)) >= 1e-8:
        raise ArithmeticError("Decimal and floating point payout checks disagree")
    daily = defaultdict(lambda: [0, 0.0])
    for r in rows:
        daily[r["start_time_source"][:10]][0] += 1
        daily[r["start_time_source"][:10]][1] += r["win"] * r[positive_key] - 1
    clusters = list(daily.values())
    rng = random.Random(20261030)
    boot = []
    if clusters:
        for _ in range(bootstrap_iterations):
            sampled = rng.choices(clusters, k=len(clusters))
            boot.append(sum(p for _, p in sampled) / sum(k for k, _ in sampled))
        boot.sort()
    bounds = [boot[int(len(boot) * .025)], boot[int(len(boot) * .975) - 1]] if boot else None
    return {"bets": n, "wins": wins, "losses": n - wins,
            "hit_rate": wins / n if n else None,
            "staked_units": n, "returned_units": float(payouts), "profit_units": float(profit),
            "roi": float(profit / n) if n else None,
            "date_cluster_bootstrap_roi_percentiles_2_5_97_5": bounds,
            "dates": len(clusters), "first_source_time": rows[0]["start_time_source"] if n else None,
            "last_source_time": rows[-1]["start_time_source"] if n else None}


def analyze_rows(rows, positive_key, negative_key, *, bootstrap_iterations=10000):
    """Apply the same frozen evaluation procedure to one named binary outcome."""
    cutoff, train, later = split_by_date(rows)
    alpha = fit_intercept(train, positive_key, negative_key)
    observations = []
    for raw in rows:
        row = dict(raw)
        row["calibrated_p"] = logistic(math.log(row[negative_key] / row[positive_key]) + alpha)
        row["estimated_ev"] = row["calibrated_p"] * row[positive_key] - 1
        observations.append(row)
    predictions = [r for r in observations if r["start_time_source"][:10] >= cutoff]
    selected = [r for r in predictions if r["estimated_ev"] > 0]
    summary = lambda sample: summarize(sample, positive_key, bootstrap_iterations=bootstrap_iterations)
    return {"full_sample_flat_stakes": summary(rows), "training_flat_stakes": summary(train),
            "later_period_flat_stakes": summary(later), "date_cutoff_source": cutoff,
            "calibration": {
                "formula": f"p=logistic(log({negative_key}/{positive_key})+alpha); fit alpha only on earlier rows",
                "alpha": alpha, "selection_rule": f"p*{positive_key}-1>0",
                "later_period_selected": summary(selected),
                "later_period_ev_range": [min(r["estimated_ev"] for r in predictions),
                                          max(r["estimated_ev"] for r in predictions)]},
            "observations": observations}
