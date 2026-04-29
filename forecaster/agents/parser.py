from forecaster.models import ParsedQuestion, ForeknowledgeRisk
from forecaster.config import ForecasterConfig
from forecaster.agents.base import LLMClient

SYSTEM_PROMPT = """You are a Prediction Question Analyst. Decompose a forecasting question into its structural components to guide systematic probabilistic research.

DO NOT forecast. DO NOT estimate any probability. Only analyze structure.

Your outputs:
1. RESOLUTION CRITERIA — exactly what must happen for YES. Be precise about thresholds, dates, and scope.
2. OUTSIDE VIEW — what is the natural reference class? (e.g. "Fed rate cuts after pauses", "tech company earnings beats", "incumbent party wins in election year"). Formulate the base rate query.
3. INSIDE VIEW FACTORS — what is specific about this instance that might update from the base rate? List 3-5 concrete factors.
4. KEY UNKNOWNS — what 2-4 pieces of information would most change your probability estimate if you knew them?
5. INITIAL SEARCH QUERIES — 3-5 specific searches to run first. Start with base rate searches, then current-state searches.
6. FOREKNOWLEDGE RISK — HIGH if this question may already be resolvable from public information (event may have occurred); MEDIUM if partial information is public; LOW if it is genuinely future.
7. AMBIGUITIES — any underspecified aspects of the question that could affect resolution.

Call submit_parsed_question when complete.
"""

_SUBMIT_TOOL = {
    "name": "submit_parsed_question",
    "description": "Submit the fully parsed question structure.",
    "input_schema": {
        "type": "object",
        "properties": {
            "resolution_criteria": {"type": "string"},
            "resolution_deadline": {"type": "string"},
            "relevant_timezone": {"type": "string"},
            "outside_view_reference_class": {
                "type": "string",
                "description": "The reference class for base rate estimation (e.g. 'Fed rate cuts following a pause period')",
            },
            "base_rate_queries": {
                "type": "array", "items": {"type": "string"},
                "description": "Specific search queries to find historical base rates",
            },
            "key_unknowns": {
                "type": "array", "items": {"type": "string"},
                "description": "2-4 pieces of information that would most change the probability estimate",
            },
            "inside_view_factors": {
                "type": "array", "items": {"type": "string"},
                "description": "Factors specific to this instance that update from the base rate",
            },
            "foreknowledge_risk": {"type": "string", "enum": ["low", "medium", "high"]},
            "ambiguity_notes": {"type": "array", "items": {"type": "string"}},
            "initial_search_queries": {
                "type": "array", "items": {"type": "string"},
                "description": "3-5 recommended initial searches, starting with base rate queries",
            },
        },
        "required": [
            "resolution_criteria", "outside_view_reference_class",
            "base_rate_queries", "key_unknowns", "inside_view_factors",
            "foreknowledge_risk", "initial_search_queries",
        ],
    },
}


def parse_question(
    question: str,
    context: str | None = None,
    config: ForecasterConfig | None = None,
) -> ParsedQuestion:
    if config is None:
        config = ForecasterConfig()

    llm = LLMClient(config)

    user_content = f"QUESTION: {question}"
    if context:
        user_content += f"\n\nADDITIONAL CONTEXT:\n{context}"

    response = llm.complete(
        SYSTEM_PROMPT,
        [{"role": "user", "content": user_content}],
        [_SUBMIT_TOOL],
        force_tool=True,
    )

    if not response.tool_blocks:
        raise ValueError("Question Parser did not call submit_parsed_question")

    inp = response.tool_blocks[0].input
    return ParsedQuestion(
        question=question,
        resolution_criteria=inp["resolution_criteria"],
        resolution_deadline=inp.get("resolution_deadline"),
        relevant_timezone=inp.get("relevant_timezone"),
        outside_view_reference_class=inp.get("outside_view_reference_class", ""),
        base_rate_queries=inp.get("base_rate_queries", []),
        key_unknowns=inp.get("key_unknowns", []),
        inside_view_factors=inp.get("inside_view_factors", []),
        foreknowledge_risk=ForeknowledgeRisk(inp["foreknowledge_risk"]),
        ambiguity_notes=inp.get("ambiguity_notes", []),
        initial_search_queries=inp.get("initial_search_queries", []),
    )
