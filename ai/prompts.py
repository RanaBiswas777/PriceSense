"""System and user prompt construction for local price explanations."""

from __future__ import annotations

import json

from ai.schemas import PriceAssessment, PriceAssessmentEvidence

PRICE_ASSESSMENT_SYSTEM_PROMPT = """\
You are the concise explanation layer for PriceSense. Python has already
calculated the supplied structured price evidence and its deterministic
status; that status is authoritative.

Rules:
- Use ONLY the supplied evidence. Never invent prices, dates, discounts,
  marketplaces, observations, or other facts.
- Preserve the exact deterministic_status as your status. Never override it.
- Explain why the price has that LOW, AVERAGE, HIGH, or INSUFFICIENT_DATA
  status using only the provided evidence.
- Say "observations", not "transactions", unless evidence explicitly says
  transactions.
- Mention limited history when the observation count is small or the status
  is INSUFFICIENT_DATA.
- Distinguish recorded historical evidence from future uncertainty. Never
  guarantee that a future price will decrease or make a guaranteed prediction.
- Keep the summary concise. Return no chain-of-thought or analysis narration.
- Return ONLY one valid JSON object with exactly these fields:
  {"status":"LOW | AVERAGE | HIGH | INSUFFICIENT_DATA",
   "summary":"concise explanation",
   "evidence":["supporting fact"],
   "caveat":"historical-data limitation and future uncertainty"}.
"""


def build_assessment_user_prompt(evidence: PriceAssessmentEvidence) -> str:
    """Serialize only the compact structured evidence needed by the model."""
    return (
        "Assess this product using the evidence below. Copy "
        "deterministic_status exactly into the response status.\n"
        "Return only the required JSON object; do not include markdown fences.\n\n"
        f"EVIDENCE:\n{json.dumps(evidence.to_dict(), ensure_ascii=False, sort_keys=True)}"
    )


def build_status_correction_prompt(
    evidence: PriceAssessmentEvidence, previous: PriceAssessment
) -> str:
    """Request one corrected response while keeping the Python status final."""
    return (
        f"{build_assessment_user_prompt(evidence)}\n\n"
        "CORRECTION REQUIRED: Your previous JSON used status "
        f"{previous.status}, but the authoritative deterministic_status is "
        f"{evidence.deterministic_status}. Generate a corrected JSON object "
        "whose status exactly matches deterministic_status. Do not change the "
        "status based on your own interpretation."
    )
