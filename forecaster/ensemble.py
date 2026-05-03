"""
Two-phase ensemble:
  Phase 1 — N outside-view agents establish the base rate (max_ov_iterations each)
  Phase 2 — M inside-view agents update from the consensus (max_iv_iterations each)
  Supervisor reconciles IV agents with OV consensus as context.
Runs K independent passes; final probability = geometric mean of reconciled probabilities.
"""
from typing import Callable, Optional
from forecaster.models import (
    AgentForecast, OutsideViewForecast, OutsideViewConsensus,
    SupervisorReconciliation, ParsedQuestion,
)
from forecaster.config import ForecasterConfig
from forecaster.agents.outside_view_agent import run_outside_view_agent
from forecaster.agents.forecaster_agent import run_forecasting_agent
from forecaster.agents.supervisor import run_supervisor
from forecaster.calibration import ensemble_average, probability_spread


def _aggregate_outside_views(ov_forecasts: list[OutsideViewForecast]) -> OutsideViewConsensus:
    base_rate = ensemble_average([f.base_rate for f in ov_forecasts])
    best = max(ov_forecasts, key=lambda f: {"high": 2, "medium": 1, "low": 0}.get(f.confidence, 0))
    return OutsideViewConsensus(
        base_rate=base_rate,
        reference_class=best.reference_class,
        statistical_object=best.statistical_object,
        denominator_or_basis=best.denominator_or_basis,
        reference_class_limitations=best.reference_class_limitations,
        reasoning=best.reasoning,
        agent_forecasts=ov_forecasts,
    )


def run_single_pass(
    parsed_question: ParsedQuestion,
    config: ForecasterConfig,
    run_id: int,
    on_step: Optional[Callable] = None,
) -> tuple[list[OutsideViewForecast], OutsideViewConsensus, list[AgentForecast], SupervisorReconciliation]:
    # Phase 1: outside view
    ov_forecasts: list[OutsideViewForecast] = []
    for i in range(config.num_ov_agents):
        if on_step:
            on_step(f"Run {run_id+1} · OV Agent {i+1}/{config.num_ov_agents}", "running")
        ov_forecasts.append(run_outside_view_agent(parsed_question, agent_id=i, config=config))
        if on_step:
            on_step(f"Run {run_id+1} · OV Agent {i+1}/{config.num_ov_agents}", "done")

    ov_consensus = _aggregate_outside_views(ov_forecasts)
    if on_step:
        on_step("OV Phase", "complete", ov_consensus)

    # Phase 2: inside view
    iv_forecasts: list[AgentForecast] = []
    for i in range(config.num_iv_agents):
        if on_step:
            on_step(f"Run {run_id+1} · Agent {i+1}/{config.num_iv_agents}", "running")
        iv_forecasts.append(run_forecasting_agent(parsed_question, agent_id=i, ov_consensus=ov_consensus, config=config))
        if on_step:
            on_step(f"Run {run_id+1} · Agent {i+1}/{config.num_iv_agents}", "done")

    if on_step:
        on_step("IV Phase", "complete", iv_forecasts)

    if on_step:
        on_step(f"Run {run_id+1} · Supervisor", "running")
    reconciliation = run_supervisor(parsed_question, iv_forecasts, ov_consensus, config)
    if on_step:
        on_step(f"Run {run_id+1} · Supervisor", "done")

    return ov_forecasts, ov_consensus, iv_forecasts, reconciliation


def run_ensemble(
    parsed_question: ParsedQuestion,
    config: ForecasterConfig,
    on_step: Optional[Callable] = None,
) -> tuple[float, list[float], list[OutsideViewForecast], OutsideViewConsensus, list[AgentForecast], SupervisorReconciliation]:
    """
    Returns:
        raw_probability: geometric mean across K runs (before Platt scaling)
        run_probabilities: reconciled probability from each run
        final_ov_forecasts: OV agent forecasts from last run
        final_ov_consensus: aggregated outside view from last run
        final_iv_forecasts: IV agent forecasts from last run
        final_reconciliation: supervisor output from last run
    """
    run_probabilities: list[float] = []
    final_ov_forecasts: list[OutsideViewForecast] = []
    final_ov_consensus: OutsideViewConsensus | None = None
    final_iv_forecasts: list[AgentForecast] = []
    final_reconciliation: SupervisorReconciliation | None = None

    for k in range(config.num_ensemble_runs):
        ov_f, ov_c, iv_f, reconciliation = run_single_pass(parsed_question, config, run_id=k, on_step=on_step)
        run_probabilities.append(reconciliation.reconciled_probability)
        final_ov_forecasts = ov_f
        final_ov_consensus = ov_c
        final_iv_forecasts = iv_f
        final_reconciliation = reconciliation

    raw_probability = ensemble_average(run_probabilities)
    return raw_probability, run_probabilities, final_ov_forecasts, final_ov_consensus, final_iv_forecasts, final_reconciliation
