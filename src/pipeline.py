"""
Recruiting Copilot Pipeline
---------------------------
Five distinct, sequential LLM steps. Each step:
  - Has its own prompt (see src/prompts.py)
  - Makes its own LLM call (no collapsing)
  - Logs to the pipeline_trace

Step 4 implements a self-correction loop with two checks:
  (a) outreach_message length < 300 characters
  (b) outreach_message contains a specific detail extracted from the JD
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from src.llm_client import LLMClient
from src import prompts
from src.tools import validate_boolean_query, check_outreach_for_bias

logger = logging.getLogger(__name__)

MAX_OUTREACH_ATTEMPTS = 3
OUTREACH_CHAR_LIMIT = 300


class PipelineError(Exception):
    """Raised when the pipeline cannot continue."""


class RecruitingPipeline:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.trace: list[dict[str, Any]] = []

    # Trace helpers
    def _log_step(
        self,
        step: int,
        action: str,
        attempt: int,
        result: str,
        note: str = "",
    ) -> None:
        entry = {
            "step": step,
            "action": action,
            "attempt": attempt,
            "result": result,
            "note": note,
        }
        self.trace.append(entry)
        logger.info(
            "step=%d action=%s attempt=%d result=%s | %s",
            step,
            action,
            attempt,
            result,
            note,
        )

    # Step 1: extract_jd_signals
    def extract_jd_signals(self, jd: str, hm_notes: Optional[str]) -> dict[str, Any]:
        prompt = prompts.EXTRACT_JD_SIGNALS.format(
            jd=jd,
            hm_notes=hm_notes or "(none provided)",
        )
        try:
            signals = self.llm.call_json(prompt)
            self._log_step(
                1,
                "extract_jd_signals",
                1,
                "pass",
                f"role_type={signals.get('role_type', 'n/a')}",
            )
            return signals
        except Exception as exc:
            self._log_step(1, "extract_jd_signals", 1, "fail", str(exc))
            raise PipelineError(f"Step 1 failed: {exc}") from exc

    # Step 2: generate_search_strategy
    def generate_search_strategy(self, signals: dict[str, Any]) -> dict[str, Any]:
        prompt = prompts.GENERATE_SEARCH_STRATEGY.format(
            signals=json.dumps(signals, indent=2)
        )
        try:
            strategy = self.llm.call_json(prompt)

            # Seniority edge case: explicit decision documented in README.
            # If the model returned a vague or empty seniority, we surface that
            # decision in the trace so reviewers can see how it was handled.
            seniority = (strategy.get("seniority") or "").strip()
            note = f"seniority={seniority or 'unspecified'}"
            if not seniority or seniority.lower() in {"unspecified", "unknown", "n/a"}:
                strategy["seniority"] = (
                    "Mid to Senior (inferred; JD lacked explicit signal)"
                )
                note = (
                    "seniority unspecified in JD; defaulted to 'Mid to Senior (inferred)' "
                    "per documented policy"
                )
            self._log_step(2, "generate_search_strategy", 1, "pass", note)
            return strategy
        except Exception as exc:
            self._log_step(2, "generate_search_strategy", 1, "fail", str(exc))
            raise PipelineError(f"Step 2 failed: {exc}") from exc

    # Step 3: generate_boolean_query
    def generate_boolean_query(self, strategy: dict[str, Any]) -> dict[str, Any]:
        prompt = prompts.GENERATE_BOOLEAN_QUERY.format(
            strategy=json.dumps(strategy, indent=2)
        )
        try:
            result = self.llm.call_json(prompt)
            boolean_query = result.get("boolean_query", "").strip()

            # Bonus: function-style tool call to validate the query.
            validation = validate_boolean_query(boolean_query)
            note = (
                f"chars={len(boolean_query)} balanced_parens={validation['balanced_parens']} "
                f"has_and={validation['has_and']} has_or={validation['has_or']}"
            )
            if not validation["is_valid"]:
                note += f" | warning: {validation['warning']}"

            self._log_step(3, "generate_boolean_query", 1, "pass", note)
            return {"boolean_query": boolean_query, "_validation": validation}
        except Exception as exc:
            self._log_step(3, "generate_boolean_query", 1, "fail", str(exc))
            raise PipelineError(f"Step 3 failed: {exc}") from exc

    # Step 4: generate_outreach_message (with self-correction loop)
    def generate_outreach_message(
        self,
        signals: dict[str, Any],
        strategy: dict[str, Any],
        jd: str,
    ) -> dict[str, Any]:
        """
        Self-correction loop:
          - Up to 3 attempts.
          - Two validation checks per attempt:
              1. character_count < 300
              2. outreach_message contains a specific detail copied from the JD
          - On failure, the next attempt receives explicit feedback about what failed.
          - Each attempt is logged in pipeline_trace.
          - If all attempts fail, the step is marked "fail" and pipeline exits gracefully.
        """
        last_attempt: dict[str, Any] = {}
        feedback = ""

        for attempt in range(1, MAX_OUTREACH_ATTEMPTS + 1):
            prompt = prompts.GENERATE_OUTREACH.format(
                jd=jd,
                signals=json.dumps(signals, indent=2),
                strategy=json.dumps(strategy, indent=2),
                feedback=feedback or "(first attempt — no prior feedback)",
                char_limit=OUTREACH_CHAR_LIMIT,
            )
            try:
                result = self.llm.call_json(prompt)
            except Exception as exc:
                self._log_step(
                    4, "generate_outreach_message", attempt, "fail", str(exc)
                )
                feedback = (
                    f"Previous attempt threw an error: {exc}. Return valid JSON only."
                )
                last_attempt = {"error": str(exc)}
                continue

            message = (result.get("outreach_message") or "").strip()
            specific_detail = (result.get("specific_detail") or "").strip()
            char_count = len(message)

            # Validation
            length_ok = char_count <= OUTREACH_CHAR_LIMIT
            detail_ok = bool(specific_detail) and (
                specific_detail.lower() in jd.lower()
                or specific_detail.lower() in message.lower()
            )

            failure_reasons = []
            if not length_ok:
                failure_reasons.append(
                    f"message was {char_count} chars (limit: {OUTREACH_CHAR_LIMIT})"
                )
            if not detail_ok:
                failure_reasons.append(
                    "specific_detail was not actually present in the JD or message; "
                    "you must quote an exact phrase from the JD"
                )

            last_attempt = {
                "outreach_message": message,
                "specific_detail": specific_detail,
                "character_count": char_count,
                "attempts": attempt,
            }

            if length_ok and detail_ok:
                self._log_step(
                    4,
                    "generate_outreach_message",
                    attempt,
                    "pass",
                    f"chars={char_count}, detail='{specific_detail[:40]}'",
                )
                # Bonus guardrail: bias scan on the outreach text.
                bias_warning = check_outreach_for_bias(message)
                if bias_warning:
                    last_attempt["_guardrail_warning"] = bias_warning
                    logger.warning("Guardrail flagged outreach: %s", bias_warning)
                return last_attempt

            # Failed: build feedback for next attempt
            note = "; ".join(failure_reasons)
            self._log_step(4, "generate_outreach_message", attempt, "retry", note)
            feedback = (
                "Your previous attempt failed validation:\n  - "
                + "\n  - ".join(failure_reasons)
                + "\n\nRevise. Keep the message strictly under "
                + str(OUTREACH_CHAR_LIMIT)
                + " characters AND include an exact phrase from the JD in `specific_detail`."
            )

        # All attempts exhausted.
        self._log_step(
            4,
            "generate_outreach_message",
            MAX_OUTREACH_ATTEMPTS,
            "fail",
            f"all {MAX_OUTREACH_ATTEMPTS} attempts failed validation",
        )
        raise PipelineError(
            f"Outreach generation failed after {MAX_OUTREACH_ATTEMPTS} attempts. "
            f"Last attempt: {last_attempt}"
        )

    # Step 5: generate_candidate_summary
    def generate_candidate_summary(
        self,
        signals: dict[str, Any],
        strategy: dict[str, Any],
        boolean_query: str,
        outreach: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = prompts.GENERATE_CANDIDATE_SUMMARY.format(
            signals=json.dumps(signals, indent=2),
            strategy=json.dumps(strategy, indent=2),
            boolean_query=boolean_query,
            outreach_message=outreach.get("outreach_message", ""),
        )
        try:
            summary = self.llm.call_json(prompt)
            self._log_step(
                5,
                "generate_candidate_summary",
                1,
                "pass",
                f"candidate={summary.get('name', 'n/a')} @ {summary.get('current_company', 'n/a')}",
            )
            return summary
        except Exception as exc:
            self._log_step(5, "generate_candidate_summary", 1, "fail", str(exc))
            raise PipelineError(f"Step 5 failed: {exc}") from exc

    # Orchestration
    def run(self, jd: str, hm_notes: Optional[str] = None) -> dict[str, Any]:
        signals = self.extract_jd_signals(jd, hm_notes)
        strategy = self.generate_search_strategy(signals)
        boolean_result = self.generate_boolean_query(strategy)
        boolean_query = boolean_result["boolean_query"]
        outreach = self.generate_outreach_message(signals, strategy, jd)
        summary = self.generate_candidate_summary(
            signals, strategy, boolean_query, outreach
        )

        # Strip internal helper fields before serializing.
        clean_strategy = {k: v for k, v in strategy.items() if not k.startswith("_")}
        clean_outreach = {
            "outreach_message": outreach["outreach_message"],
            "specific_detail": outreach["specific_detail"],
            "character_count": outreach["character_count"],
            "attempts": outreach["attempts"],
        }

        return {
            "candidate_search_strategy": clean_strategy,
            "boolean_query": boolean_query,
            "outreach_message": clean_outreach,
            "candidate_summary": summary,
            "pipeline_trace": self.trace,
        }
