import json
from pathlib import Path
from typing import Callable, Optional

from forecaster.models import ForecastMemo, ParsedQuestion
from forecaster.config import ForecasterConfig
from forecaster.agents.parser import parse_question
from forecaster.ensemble import run_ensemble
from forecaster.calibration import platt_scale, probability_spread

ProgressCallback = Optional[Callable[[str, str], None]]


class ForecasterSystem:
    def __init__(self, config: ForecasterConfig | None = None):
        self.config = config or ForecasterConfig()

    def forecast(
        self,
        question: str,
        context: str | None = None,
        on_step: ProgressCallback | None = None,
        series_ticker: str | None = None,
        event_title: str | None = None,
        ev_sub: str | None = None,
        ev_category: str | None = None,
    ) -> ForecastMemo:
        cfg = self.config

        def step(name: str, fn):
            if on_step:
                on_step(name, "running")
            result = fn()
            if on_step:
                on_step(name, "done")
            return result

        parsed: ParsedQuestion = step(
            "Question Parser",
            lambda: parse_question(question, context, cfg,
                                   series_ticker=series_ticker,
                                   event_title=event_title,
                                   ev_sub=ev_sub,
                                   ev_category=ev_category),
        )

        raw_prob, run_probs, ov_forecasts, ov_consensus, agent_forecasts, reconciliation = run_ensemble(
            parsed, cfg, on_step=on_step
        )

        calibration = platt_scale(raw_prob, cfg.platt_coefficient)
        spread = probability_spread(run_probs)

        all_for = [f for agent in agent_forecasts for f in agent.key_factors_for]
        all_against = [f for agent in agent_forecasts for f in agent.key_factors_against]
        inside_views = [a.inside_view_reasoning for a in agent_forecasts]

        return ForecastMemo(
            question=question,
            final_probability=calibration.calibrated_probability,
            raw_probability=raw_prob,
            ensemble_run_probabilities=run_probs,
            probability_spread=spread,
            calibration=calibration,
            parsed_question=parsed,
            ov_forecasts=ov_forecasts,
            agent_forecasts=agent_forecasts,
            supervisor_reconciliation=reconciliation,
            inside_view_summary=reconciliation.reconciliation_reasoning,
            outside_view_summary=ov_consensus.reasoning,
            key_evidence_summary=f"Factors for YES: {'; '.join(all_for[:5])}. "
                                  f"Factors against YES: {'; '.join(all_against[:5])}.",
            open_questions=parsed.key_unknowns,
            foreknowledge_flags=(
                [f"Foreknowledge risk: {parsed.foreknowledge_risk.value}"]
                if parsed.foreknowledge_risk.value != "low" else []
            ),
            num_agents=cfg.num_ov_agents + cfg.num_iv_agents,
            num_ensemble_runs=cfg.num_ensemble_runs,
        )

    def save_memo(self, memo: ForecastMemo, path: Path) -> None:
        path.write_text(json.dumps(memo.model_dump(mode="json"), indent=2, default=str))
