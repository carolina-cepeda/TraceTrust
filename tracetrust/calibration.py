"""Trust Score weight sensitivity analysis."""

from __future__ import annotations

from .trust_score import DEFAULT_WEIGHTS, calculate_trust_score


def sensitivity_analysis(entity_ids, events, matches, findings, step: float = 0.05) -> dict:
    baseline = {entity_id: calculate_trust_score(entity_id, events, matches, findings).score for entity_id in entity_ids}
    variants = {}
    for factor in DEFAULT_WEIGHTS:
        weights = dict(DEFAULT_WEIGHTS)
        if weights[factor] + step > 1:
            continue
        weights[factor] += step
        remainder = 1.0 - weights[factor]
        old_remainder = 1.0 - DEFAULT_WEIGHTS[factor]
        for other in weights:
            if other != factor:
                weights[other] = DEFAULT_WEIGHTS[other] * remainder / old_remainder
        variants[factor] = {
            entity_id: calculate_trust_score(entity_id, events, matches, findings, weights=weights).score
            for entity_id in entity_ids
        }
    max_delta = max(
        (abs(score - baseline[entity_id]) for variant in variants.values() for entity_id, score in variant.items()),
        default=0.0,
    )
    return {"baseline": baseline, "variants": variants, "max_absolute_score_delta": round(max_delta, 6),
            "step": step}
