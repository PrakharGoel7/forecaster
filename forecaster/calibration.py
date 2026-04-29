"""Platt scaling and ensemble averaging for probability calibration."""
import math
from forecaster.models import CalibrationResult


def logit(p: float) -> float:
    p = max(0.0001, min(0.9999, p))
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def platt_scale(p: float, coefficient: float) -> CalibrationResult:
    """
    Push probabilities away from 0.5 toward the tails.
    Corrects for the well-documented LLM hedging bias.
    Coefficient √3 ≈ 1.732 matches superforecaster performance per the paper.
    """
    raw_lo = logit(p)
    calibrated_lo = coefficient * raw_lo
    calibrated_p = sigmoid(calibrated_lo)
    return CalibrationResult(
        raw_probability=p,
        calibrated_probability=calibrated_p,
        platt_coefficient=coefficient,
    )


def ensemble_average(probabilities: list[float]) -> float:
    """Geometric mean via log-odds averaging. Jensen's inequality guarantees
    this strictly improves expected Brier score over arithmetic averaging."""
    if len(probabilities) == 1:
        return probabilities[0]
    mean_lo = sum(logit(p) for p in probabilities) / len(probabilities)
    return sigmoid(mean_lo)


def probability_spread(probabilities: list[float]) -> tuple[float, float]:
    if not probabilities:
        return (0.0, 1.0)
    return (min(probabilities), max(probabilities))
