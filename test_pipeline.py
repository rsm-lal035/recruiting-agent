"""
Mock test of the self-correction loop in Step 4.

Verifies:
  - Attempt 1 returns a too-long message -> retry logged
  - Attempt 2 returns a message without the JD detail -> retry logged
  - Attempt 3 returns valid -> pass logged
  - Final attempts count == 3
  - Trace order is correct

This does NOT call the real LLM. It substitutes a mock client.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Mock anthropic before importing llm_client so we don't need the real package.
class _MockAnthropicModule:
    class APIConnectionError(Exception): ...
    class RateLimitError(Exception): ...
    class APIStatusError(Exception): ...
    class Anthropic:
        def __init__(self, *a, **kw): pass

sys.modules["anthropic"] = _MockAnthropicModule()

from src.pipeline import RecruitingPipeline


class MockLLM:
    """Returns scripted responses in order."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def call_json(self, prompt, system=None):
        self.calls += 1
        return self.responses.pop(0)


JD = "We're hiring a Senior Backend Engineer to build the inference routing system at our Series A startup."

def test_self_correction_loop():
    mock = MockLLM([
        # Step 4 attempt 1: too long
        {
            "outreach_message": "X" * 350,
            "specific_detail": "inference routing system",
        },
        # Step 4 attempt 2: short, but detail NOT in JD
        {
            "outreach_message": "Hi! Open to a quick chat?",
            "specific_detail": "this detail is not in the JD at all",
        },
        # Step 4 attempt 3: valid
        {
            "outreach_message": "Saw you build inference routing system — would love a 15 min chat about what we're building.",
            "specific_detail": "inference routing system",
        },
    ])
    pipe = RecruitingPipeline(mock)
    result = pipe.generate_outreach_message(
        signals={"role_type": "Backend Engineer"},
        strategy={"keywords": ["inference"]},
        jd=JD,
    )

    assert result["attempts"] == 3, f"expected 3 attempts, got {result['attempts']}"
    assert result["character_count"] < 300
    assert "inference routing system" in result["outreach_message"]

    # Trace: 2 retries + 1 pass = 3 entries
    assert len(pipe.trace) == 3
    assert pipe.trace[0]["result"] == "retry"
    assert pipe.trace[1]["result"] == "retry"
    assert pipe.trace[2]["result"] == "pass"

    print("PASS: self-correction loop test")
    print(json.dumps(pipe.trace, indent=2))


def test_all_attempts_fail():
    from src.pipeline import PipelineError
    mock = MockLLM([
        {"outreach_message": "X" * 350, "specific_detail": "nope"},
        {"outreach_message": "Y" * 350, "specific_detail": "nope"},
        {"outreach_message": "Z" * 350, "specific_detail": "nope"},
    ])
    pipe = RecruitingPipeline(mock)
    try:
        pipe.generate_outreach_message({}, {}, JD)
        print("FAIL: should have raised PipelineError")
    except PipelineError as exc:
        # Trace should show 2 retries + 1 fail
        assert pipe.trace[-1]["result"] == "fail"
        print("PASS: all-attempts-fail exits gracefully")
        print(f"  exception: {exc}")


if __name__ == "__main__":
    test_self_correction_loop()
    print()
    test_all_attempts_fail()
