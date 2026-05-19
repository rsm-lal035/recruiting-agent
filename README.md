# OCBridge Recruiting Copilot

Take-home assignment for the OCBridge Engineering Intern role, 2026.

A five-step AI agent that takes a job description and runs it through: JD signal extraction → search strategy → Boolean query → outreach message (with self-correction) → candidate summary card.

---

## Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url> ocbridge-recruiting-copilot
cd ocbridge-recruiting-copilot

# 2. Create a venv (Python 3.10+)
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install deps
pip install -r requirements.txt

# 4. Set your API key
export ANTHROPIC_API_KEY=sk-ant-...   # Windows: set ANTHROPIC_API_KEY=sk-ant-...

# 5. Run
python main.py
```

Optional flags:
```bash
python main.py --jd path/to/jd.txt           # use your own JD
python main.py --jd jd.txt --notes notes.txt # add hiring manager notes
python main.py --verbose                      # detailed logging
```

Output goes to `output.json` in the repo root.

---

## File layout

```
.
├── main.py                  # entrypoint
├── requirements.txt
├── output.json              # latest real run
├── sample_data/sample_jd.txt
├── src/
│   ├── pipeline.py          # 5-step orchestration + retry loop
│   ├── llm_client.py        # Anthropic wrapper + JSON parsing
│   ├── prompts.py           # all prompts
│   └── tools.py             # boolean validator + bias check
└── test_pipeline.py         # mock-LLM tests for the retry loop
```

Each step is a separate function in `src/pipeline.py`, makes its own LLM call, and appends to `pipeline_trace` as it runs.

---

## Sample Run

```bash
python main.py
```

### Terminal output

```
[info] No --jd given. Using sample JD: /…/sample_data/sample_jd.txt

======================================================================
PIPELINE RESULT
======================================================================

[1] Candidate Search Strategy
    seniority         : Senior to Staff (5+ years)
    target_backgrounds: ['Senior/Staff backend engineer at an inference or model-serving company', ...]
    target_companies  : ['Anyscale', 'Modal', 'Together AI', 'Fireworks AI', ...]
    keywords          : ['inference', 'model serving', 'vLLM', 'Triton', ...]

[2] Boolean Query
    ("inference" OR "model serving" OR "vLLM" OR "Triton") AND (Python OR Go) AND (Kafka OR Redis OR gRPC) AND (startup OR "Series A" OR "Series B") NOT (intern OR junior)

[3] Outreach Message
    chars   : 162 (limit 300)
    attempts: 2
    detail  : 'inference routing system'
    message : Saw your work on low-latency model serving — we're building the inference routing system at a Series A and going from 10M to 1B requests/day. Worth a 15-min chat?

[4] Candidate Summary
    Priya Raghavan — Anyscale
    skills  : ['vLLM and Triton model serving', 'Python + Go backend at scale', ...]
    fit     : Built and operated the inference autoscaling layer at Anyscale.
    concerns: Only worked at one large-ish company; may need calibration on 14-person startup tempo.

[5] Pipeline Trace
    step=1 action=extract_jd_signals             attempt=1 result=pass
    step=2 action=generate_search_strategy       attempt=1 result=pass
    step=3 action=generate_boolean_query         attempt=1 result=pass  | balanced_parens=True
    step=4 action=generate_outreach_message      attempt=1 result=retry | message was 302 chars
    step=4 action=generate_outreach_message      attempt=2 result=pass  | chars=162
    step=5 action=generate_candidate_summary     attempt=1 result=pass
======================================================================

Wrote /…/output.json
```

Step 4 took two tries here. First attempt came back at 302 characters, so the loop fed that back as feedback and the second attempt landed at 162. Full `output.json` is in the repo.

---

## Seniority decision

The JD may not have a clear seniority signal. If the model returns something empty or vague (`"unspecified"`, `"unknown"`, etc.), the pipeline substitutes `"Mid to Senior (inferred; JD lacked explicit signal)"` and notes it in the trace. Better to give the recruiter a sensible default with a label than a blank field. Handled in `src/pipeline.py` → `generate_search_strategy`.

---

## Bonus items

- **Boolean query validator** (`src/tools.py`): after Step 3, runs deterministic checks on the query (balanced parens, AND/OR present, balanced quotes, length cap) and logs the result to the trace. I kept it as a local Python check rather than a native tool-use call because the round-trip isn't worth it for something this cheap.
- **Bias guardrail** (`src/tools.py`): scans the outreach for age-coded language ("young", "energetic"), gendered terms, "culture fit", and premature comp mentions. I put this on the outreach specifically because it's the one output that gets sent straight to a person — a biased Boolean query just returns bad search results, but a biased outreach message goes into someone's inbox with our name on it. Flag-only, doesn't block.
- **Error handling**: if any step fails, `output.json` still gets written with the partial trace. LLM client retries on connection / rate-limit errors with backoff. Fallback JSON parser handles malformed model output.
- **Tests** (`test_pipeline.py`): mock-LLM tests for both the retry-then-pass path and the all-attempts-fail path. Run with `python test_pipeline.py`.

---

## Write-up

**What would I improve with another week?**

Real candidate retrieval instead of mock data for Step 5 — currently the candidate is invented, which limits what the prompt is really doing. I'd also build a small eval harness (a handful of varied JDs scored on schema match) to iterate on the prompts more systematically, add token/cost tracking to the trace, and add an email-length outreach variant alongside the 300-char LinkedIn one.

**What did I notice that wasn't explicitly stated?**

- "Self-validates its outputs" suggests other steps could use validation too, even though only Step 4 needs to retry. I added a small validator for the Boolean query since unbalanced parens are an easy and common failure.
- The `specific_detail` field is described as "the exact phrase extracted from the JD." I read that strictly — my Step 4 check verifies `specific_detail` is actually a substring of the JD, not just something that sounds like it. That stops the model from hallucinating a fake "specific detail."
- The note about `pipeline_trace` being "immediately visible" if reconstructed implied the trace structure itself is graded. So each step writes to the trace as it runs, not at the end.

**Why five steps instead of one? What breaks if you collapse Steps 1 and 2?**

Three reasons to keep them split: debuggability (the trace tells you which step produced bad output), the retry loop only works per-step (you can't retry "everything"), and each output is independently useful.

Specifically collapsing Steps 1 and 2 would mean Step 2 reasons over raw JD text instead of structured signals. The signals would get re-extracted implicitly inside the strategy reasoning, which means they'd be invisible in the trace, inconsistent across runs, and tangled up with the strategy logic — making it hard to tell whether bad output came from misreading the JD or from bad strategy. One extra LLM call is a small price for that clarity.

**Which parts used AI vs. my own judgment?**

AI helped with the initial scaffolding of `pipeline.py`, brainstorming prompt wording, and drafting the sample JD. My own decisions: the seniority edge case (it's a product call, not a code one), where to put the bias guardrail and the flag-not-block choice, the design of the retry feedback loop (explicit per-failure feedback rather than blind retries), validating `specific_detail` as an actual substring, and writing the mock-LLM tests.

---

## Tests

```bash
python test_pipeline.py
```

Two scripted scenarios, no API needed: one where Step 4 retries twice then passes, one where all three attempts fail and `PipelineError` is raised.
