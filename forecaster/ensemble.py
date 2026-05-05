"""
Two-phase ensemble:
  Phase 1 — three independent outside-view agents establish candidate base rates
            and an outside-view reconciler blends them into one prior
  Phase 2 — M inside-view agents update from the reconciled prior
  Supervisor reconciles IV agents with the reconciled outside view as context.
Runs K independent passes; final probability = geometric mean of reconciled probabilities.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional
from forecaster.models import (
    AgentForecast, OutsideViewEstimate, ReconciledOutsideView,
    SupervisorReconciliation, ParsedQuestion,
)
from forecaster.config import ForecasterConfig
from forecaster.agents.outside_view_agent import (
    run_outside_view_agent_a,
    run_outside_view_agent_b,
    run_outside_view_agent_c,
    reconcile_outside_view,
)
from forecaster.agents.forecaster_agent import run_forecasting_agent
from forecaster.agents.supervisor import run_supervisor
from forecaster.calibration import ensemble_average


def _run_parallel_agents(
    count: int,
    label_fmt: str,
    worker_fn,
    on_step: Optional[Callable] = None,
):
    results = [None] * count
    if count <= 0:
        return results

    with ThreadPoolExecutor(max_workers=count) as executor:
        future_to_idx = {}
        for i in range(count):
            if on_step:
                on_step(label_fmt(i), "running")
            future = executor.submit(worker_fn, i)
            future_to_idx[future] = i

        for future in as_completed(future_to_idx):
            i = future_to_idx[future]
            results[i] = future.result()
            if on_step:
                on_step(label_fmt(i), "done")

    return results


def run_single_pass(
    parsed_question: ParsedQuestion,
    config: ForecasterConfig,
    run_id: int,
    related_markets: list[dict] | None = None,
    on_step: Optional[Callable] = None,
) -> tuple[list[OutsideViewEstimate], ReconciledOutsideView, list[AgentForecast], SupervisorReconciliation]:
    # Phase 1: outside view
    ov_workers = [
        ("Agent A", lambda: run_outside_view_agent_a(parsed_question, related_markets=related_markets or [], config=config)),
        ("Agent B", lambda: run_outside_view_agent_b(parsed_question, related_markets=related_markets or [], config=config)),
        ("Agent C", lambda: run_outside_view_agent_c(parsed_question, related_markets=related_markets or [], config=config)),
    ]
    ov_forecasts = _run_parallel_agents(
        len(ov_workers),
        lambda i: f"Run {run_id+1} · OV {ov_workers[i][0]}",
        lambda i: ov_workers[i][1](),
        on_step=on_step,
    )

    if on_step:
        on_step(f"Run {run_id+1} · OV Reconciler", "running")
    ov_consensus = reconcile_outside_view(parsed_question, ov_forecasts, config=config)
    if on_step:
        on_step(f"Run {run_id+1} · OV Reconciler", "done")

    if on_step:
        on_step("OV Phase", "complete", ov_consensus)

    # Phase 2: inside view
    iv_forecasts = _run_parallel_agents(
        config.num_iv_agents,
        lambda i: f"Run {run_id+1} · Agent {i+1}/{config.num_iv_agents}",
        lambda i: run_forecasting_agent(
            parsed_question,
            agent_id=i,
            ov_reconciliation=ov_consensus,
            related_markets=related_markets or [],
            config=config,
        ),
        on_step=on_step,
    )

    if on_step:
        on_step("IV Phase", "complete", iv_forecasts)

    if on_step:
        on_step(f"Run {run_id+1} · Supervisor", "running")
    reconciliation = run_supervisor(
        parsed_question,
        iv_forecasts,
        ov_consensus,
        related_markets=related_markets or [],
        config=config,
    )
    if on_step:
        on_step(f"Run {run_id+1} · Supervisor", "done")

    return ov_forecasts, ov_consensus, iv_forecasts, reconciliation


def run_ensemble(
    parsed_question: ParsedQuestion,
    config: ForecasterConfig,
    related_markets: list[dict] | None = None,
    on_step: Optional[Callable] = None,
) -> tuple[float, list[float], list[OutsideViewEstimate], ReconciledOutsideView, list[AgentForecast], SupervisorReconciliation]:
    """
    Returns:
        raw_probability: geometric mean across K runs (before Platt scaling)
        run_probabilities: reconciled probability from each run
        final_ov_forecasts: OV agent estimates from last run
        final_ov_consensus: reconciled outside view from last run
        final_iv_forecasts: IV agent forecasts from last run
        final_reconciliation: supervisor output from last run
    """
    run_probabilities: list[float] = []
    final_ov_forecasts: list[OutsideViewEstimate] = []
    final_ov_consensus: ReconciledOutsideView | None = None
    final_iv_forecasts: list[AgentForecast] = []
    final_reconciliation: SupervisorReconciliation | None = None

    for k in range(config.num_ensemble_runs):
        ov_f, ov_c, iv_f, reconciliation = run_single_pass(
            parsed_question,
            config,
            run_id=k,
            related_markets=related_markets or [],
            on_step=on_step,
        )
        run_probabilities.append(reconciliation.reconciled_probability)
        final_ov_forecasts = ov_f
        final_ov_consensus = ov_c
        final_iv_forecasts = iv_f
        final_reconciliation = reconciliation

    raw_probability = ensemble_average(run_probabilities)
    return raw_probability, run_probabilities, final_ov_forecasts, final_ov_consensus, final_iv_forecasts, final_reconciliation
