"""
Runs K independent ensemble runs, each with M forecasting agents + 1 supervisor.
Averages reconciled probabilities via geometric mean of log-odds.
"""
from typing import Callable, Optional
from forecaster.models import AgentForecast, SupervisorReconciliation, ParsedQuestion
from forecaster.config import ForecasterConfig
from forecaster.agents.forecaster_agent import run_forecasting_agent
from forecaster.agents.supervisor import run_supervisor
from forecaster.calibration import ensemble_average, probability_spread


def run_single_pass(
    parsed_question: ParsedQuestion,
    config: ForecasterConfig,
    run_id: int,
    on_step: Optional[Callable] = None,
) -> tuple[list[AgentForecast], SupervisorReconciliation]:
    """Run M independent agents + supervisor for one ensemble pass."""
    agent_forecasts: list[AgentForecast] = []

    for i in range(config.num_agents):
        if on_step:
            on_step(f"Run {run_id+1} · Agent {i+1}/{config.num_agents}", "running")
        forecast = run_forecasting_agent(parsed_question, agent_id=i, config=config)
        agent_forecasts.append(forecast)
        if on_step:
            on_step(f"Run {run_id+1} · Agent {i+1}/{config.num_agents}", "done")

    if on_step:
        on_step(f"Run {run_id+1} · Supervisor", "running")
    reconciliation = run_supervisor(parsed_question, agent_forecasts, config)
    if on_step:
        on_step(f"Run {run_id+1} · Supervisor", "done")

    return agent_forecasts, reconciliation


def run_ensemble(
    parsed_question: ParsedQuestion,
    config: ForecasterConfig,
    on_step: Optional[Callable] = None,
) -> tuple[float, list[float], list[AgentForecast], SupervisorReconciliation]:
    """
    Returns:
        raw_probability: geometric mean across K runs (before Platt scaling)
        run_probabilities: reconciled probability from each run
        final_agent_forecasts: agent forecasts from last run (for the memo)
        final_reconciliation: supervisor output from last run
    """
    run_probabilities: list[float] = []
    final_agent_forecasts: list[AgentForecast] = []
    final_reconciliation: SupervisorReconciliation | None = None

    for k in range(config.num_ensemble_runs):
        agents, reconciliation = run_single_pass(parsed_question, config, run_id=k, on_step=on_step)
        run_probabilities.append(reconciliation.reconciled_probability)
        final_agent_forecasts = agents
        final_reconciliation = reconciliation

    raw_probability = ensemble_average(run_probabilities)
    return raw_probability, run_probabilities, final_agent_forecasts, final_reconciliation
