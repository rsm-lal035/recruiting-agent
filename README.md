# OCBridge Recruiting Copilot

A five-step AI agent that turns a raw Job Description into a complete recruiting workflow: extracted JD signals → candidate search strategy → Boolean sourcing query → personalized outreach (with self-correcting validation) → mock candidate summary card.

Built for the OCBridge Engineering Intern take-home, 2026.

---

## Setup (clean machine, ~2 minutes)

```bash
# 1. Clone
git clone <repo-url> ocbridge-recruiting-copilot
cd ocbridge-recruiting-copilot

# 2. Create venv (Python 3.10+)
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install
pip install -r requirements.txt

# 4. Set your Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...   # Windows: set ANTHROPIC_API_KEY=sk-ant-...

# 5. Run on the bundled sample JD
python main.py
```

You can also run on your own JD:

```bash
python main.py --jd path/to/jd.txt
python main.py --jd jd.txt --notes hiring_manager_notes.txt
cat jd.txt | python main.py --stdin
python main.py --verbose   # full per-step logging
```

Output is written to `output.json` in the repo root.

---

## How the pipeline works

```
JD ──► [1] extract_jd_signals
        │
        ▼
       [2] generate_search_strategy
        │
        ▼
       [3] generate_boolean_query  ──► validate_boolean_query()  (tool call)
        │
        ▼
       [4] generate_outreach_message
        │   ├─ generate
        │   ├─ validate (length < 300 AND specific_detail in JD)
        │   ├─ retry up to 3x with explicit feedback
        │   └─ check_outreach_for_bias()  (guardrail)
        │
        ▼
       [5] generate_candidate_summary  ──► output.json
```

Each step is a separate function in `src/pipeline.py`, makes its own LLM call, and appends to `pipeline_trace`. No collapsing.

### File layout

```
.
├── main.py                  # CLI entrypoint
├── requirements.txt
├── output.json              # Result of the last run (committed)
├── sample_data/
│   └── sample_jd.txt        # Realistic sample JD used by default
├── src/
│   ├── pipeline.py          # 5-step orchestration + self-correction loop
│   ├── llm_client.py        # Anthropic API wrapper + robust JSON parsing
│   ├── prompts.py           # All prompts in one place
│   └── tools.py             # Boolean validator + bias guardrail
└── test_pipeline.py         # Mocked tests for the self-correction loop
```

---

## Sample Run

Run command:

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
    target_backgrounds: ['Senior/Staff backend engineer at an inference or model-serving company', 'Backend engineer at a high-throughput data infra startup (Kafka/Confluent, Materialize, Estuary)', 'ML platform engineer who has owned latency SLOs in production', 'Distributed systems engineer from a payments or ad-tech company comfortable with <100ms latency']
    target_companies  : ['Anyscale', 'Modal', 'Together AI', 'Fireworks AI', 'Replicate', 'Baseten', 'OctoAI', 'Cohere infra team', 'early-stage AI infra startups (seed to Series B)', 'Stripe / Cloudflare / Cash App backend (latency-critical experience)']
    keywords          : ['inference', 'model serving', 'vLLM', 'Triton', 'TGI', 'GPU scheduling', 'gRPC', 'Kafka', 'Redis', 'low-latency', 'distributed systems', 'Python', 'Go', 'CUDA']

[2] Boolean Query
    ("inference" OR "model serving" OR "vLLM" OR "Triton") AND (Python OR Go) AND (Kafka OR Redis OR gRPC) AND (startup OR "Series A" OR "Series B") NOT (intern OR junior)

[3] Outreach Message
    chars   : 162 (limit 300)
    attempts: 2
    detail  : 'inference routing system'
    message : Saw your work on low-latency model serving — we're building the inference routing system at a Series A and going from 10M to 1B requests/day. Worth a 15-min chat?

[4] Candidate Summary
    Priya Raghavan — Anyscale
    skills  : ['vLLM and Triton model serving', 'Python + Go backend at scale', 'GPU scheduling and inference routing', 'gRPC and Kafka in production']
    fit     : Built and operated the inference autoscaling layer at Anyscale, directly relevant to the 10M→1B requests/day scaling challenge and the latency-critical routing path.
    concerns: Has only worked at one large-ish company — may need a calibration conversation about operating at 14-person startup tempo and ambiguity.

[5] Pipeline Trace
    step=1 action=extract_jd_signals             attempt=1 result=pass  | role_type=Senior Backend Engineer — AI Infrastructure
    step=2 action=generate_search_strategy       attempt=1 result=pass  | seniority=Senior to Staff (5+ years)
    step=3 action=generate_boolean_query         attempt=1 result=pass  | chars=167 balanced_parens=True has_and=True has_or=True
    step=4 action=generate_outreach_message      attempt=1 result=retry | message was 302 chars (limit: 300)
    step=4 action=generate_outreach_message      attempt=2 result=pass  | chars=162, detail='inference routing system'
    step=5 action=generate_candidate_summary     attempt=1 result=pass  | candidate=Priya Raghavan @ Anyscale
======================================================================

Wrote /…/output.json
```

### Resulting `output.json`

```json
{
  "candidate_search_strategy": {
    "target_backgrounds": [
      "Senior/Staff backend engineer at an inference or model-serving company",
      "Backend engineer at a high-throughput data infra startup (Kafka/Confluent, Materialize, Estuary)",
      "ML platform engineer who has owned latency SLOs in production",
      "Distributed systems engineer from a payments or ad-tech company comfortable with <100ms latency"
    ],
    "target_companies": [
      "Anyscale", "Modal", "Together AI", "Fireworks AI", "Replicate",
      "Baseten", "OctoAI", "Cohere infra team",
      "early-stage AI infra startups (seed to Series B)",
      "Stripe / Cloudflare / Cash App backend (latency-critical experience)"
    ],
    "keywords": [
      "inference", "model serving", "vLLM", "Triton", "TGI",
      "GPU scheduling", "gRPC", "Kafka", "Redis",
      "low-latency", "distributed systems", "Python", "Go", "CUDA"
    ],
    "seniority": "Senior to Staff (5+ years)"
  },
  "boolean_query": "(\"inference\" OR \"model serving\" OR \"vLLM\" OR \"Triton\") AND (Python OR Go) AND (Kafka OR Redis OR gRPC) AND (startup OR \"Series A\" OR \"Series B\") NOT (intern OR junior)",
  "outreach_message": {
    "outreach_message": "Saw your work on low-latency model serving — we're building the inference routing system at a Series A and going from 10M to 1B requests/day. Worth a 15-min chat?",
    "specific_detail": "inference routing system",
    "character_count": 162,
    "attempts": 2
  },
  "candidate_summary": {
    "name": "Priya Raghavan",
    "current_company": "Anyscale",
    "key_skills": [
      "vLLM and Triton model serving",
      "Python + Go backend at scale",
      "GPU scheduling and inference routing",
      "gRPC and Kafka in production"
    ],
    "fit_reason": "Built and operated the inference autoscaling layer at Anyscale, directly relevant to the 10M→1B requests/day scaling challenge and the latency-critical routing path.",
    "concerns": "Has only worked at one large-ish company — may need a calibration conversation about operating at 14-person startup tempo and ambiguity."
  },
  "pipeline_trace": [
    { "step": 1, "action": "extract_jd_signals",          "attempt": 1, "result": "pass",  "note": "role_type=Senior Backend Engineer — AI Infrastructure" },
    { "step": 2, "action": "generate_search_strategy",    "attempt": 1, "result": "pass",  "note": "seniority=Senior to Staff (5+ years)" },
    { "step": 3, "action": "generate_boolean_query",      "attempt": 1, "result": "pass",  "note": "chars=167 balanced_parens=True has_and=True has_or=True" },
    { "step": 4, "action": "generate_outreach_message",   "attempt": 1, "result": "retry", "note": "message was 302 chars (limit: 300)" },
    { "step": 4, "action": "generate_outreach_message",   "attempt": 2, "result": "pass",  "note": "chars=162, detail='inference routing system'" },
    { "step": 5, "action": "generate_candidate_summary",  "attempt": 1, "result": "pass",  "note": "candidate=Priya Raghavan @ Anyscale" }
  ]
}
```

> The trace shows Step 4 retrying once because the first attempt came back at 302 characters. The second attempt passed both checks (under 300 chars **and** the specific phrase "inference routing system" actually appears in both the JD and the outreach).

---

## Decisions worth calling out

### Seniority edge case

The schema requires a `seniority` field but the JD may not contain a clear signal. **Decision:** if the model returns an empty / "unspecified" / "unknown" / "n/a" value for seniority, the pipeline replaces it with `"Mid to Senior (inferred; JD lacked explicit signal)"` and writes a note in the pipeline_trace. Reasoning:

- A blank field forces the recruiter to make the call without context — that's worse than a labeled-as-inferred default.
- "Mid to Senior" is the modal hire for a startup that bothers to write a JD; it's a sensible default that's easy for a human to override.
- The pipeline_trace note makes it obvious that this was an inferred decision, not extracted from the JD, so downstream consumers know to question it.

This is handled in `src/pipeline.py` → `generate_search_strategy`.

### Why I chose Anthropic Claude as the LLM

Any LLM API was allowed. I used Claude (Anthropic) for three reasons:

1. The assignment is for OCBridge, an Anthropic-affiliated entity — defaulting to Claude is the least surprising choice.
2. Claude is reliable at returning clean JSON from a "return JSON only" instruction, which keeps `src/llm_client.py` simple.
3. Free credits are available on signup, satisfying the "use free-tier where possible" constraint.

Swapping providers is a one-file change in `src/llm_client.py`.

### Bonus items implemented

- **Tool / function-style call** (`src/tools.py` → `validate_boolean_query`): runs deterministic checks (balanced parens, presence of AND/OR, balanced quotes, length cap) on the Step 3 output and logs results into the trace. It's not a native function-calling API call — I deliberately kept it as a Python tool the agent invokes after the LLM call, because for a check this cheap and deterministic the round-trip through function calling adds latency without adding value. The pattern slot-fits for whenever we want to add real tool-calling later.
- **Guardrail** (`src/tools.py` → `check_outreach_for_bias`): scans the generated outreach for age-coded language ("young", "energetic", "digital native"), gendered terms ("guys", "salesman"), "culture fit", and premature comp mentions. **Why this output specifically:** the outreach message is the only one that gets sent directly to a human without further review. A bad Boolean query just returns bad candidates; a biased outreach message goes into someone's inbox under our brand. Flag-only, doesn't block — a human recruiter decides.
- **Error handling**: graceful pipeline exit on failure; `output.json` still gets written with whatever trace exists, so failures are debuggable. The LLM client retries on transient `APIConnectionError` / `RateLimitError` with exponential backoff. Malformed JSON from the model is rescued by a fallback brace-matching parser.
- **Tests** (`test_pipeline.py`): mock-LLM tests for both the happy path of the self-correction loop and the all-attempts-fail path. Confirms the trace structure is exactly what the assignment requires.

---

## Brief write-up

### What would I improve with another week?

- **Real candidate retrieval** instead of mock data. Step 5 could call a real source (a CSV of historical hires, a synthetic LinkedIn-style dataset, or actual LinkedIn Recruiter API if anyone has access) and rank candidates against the strategy, then summarize the top hit. Mock data is a reasonable stopgap but it limits the reviewer's signal on the prompt for Step 5.
- **Prompt evals**. Right now I tuned each prompt by hand on the sample JD. With another week I'd write a small eval harness (~10 diverse JDs, scored on schema-match + qualitative criteria) and iterate on each step's prompt independently.
- **Streaming output** so the recruiter sees results land as they're produced rather than waiting for all five steps to complete.
- **Multi-channel outreach**. The 300-char limit feels LinkedIn-shaped. I'd add a parallel email-length variant (~1500 chars) so the recruiter can pick the channel.
- **Token / cost tracking** in the trace.

### What did I notice that wasn't explicitly stated?

- The phrase "self-validates its outputs" in the overview suggests **other** steps could also benefit from validation, even though only Step 4 is required to retry. I added a lightweight validator for the Boolean query (Step 3) because empty or unbalanced queries are common LLM failures and easy to detect. I did not add a retry loop there — the assignment is explicit that Step 4 is the retry step.
- The schema says `specific_detail` is "the exact phrase extracted from the JD that was used to personalize the message." The natural reading is **verbatim from the JD**, not paraphrased. My validation in Step 4 checks that `specific_detail` is a substring of either the JD text or the outreach message — both must be true for the message to be considered personalized. This is stricter than the prompt alone and prevents the model from hallucinating a "specific detail" that sounds like it came from the JD but didn't.
- The `pipeline_trace` warning ("a single-call implementation that reconstructs the trace after the fact will be immediately visible") implied the trace structure itself is a signal. I made sure the trace is built **incrementally** inside each step, not assembled at the end.
- Mock candidate data is allowed, but `fit_reason` and `concerns` are tested for whether they reflect real reasoning. I prompted Step 5 to surface an *actual plausible gap* rather than a generic "no major concerns."

### Why five steps instead of one? What breaks if you collapse Steps 1 and 2?

The structural reasons:

1. **Debuggability**. When a downstream step produces nonsense, a multi-step trace tells you which step caused it. A monolithic prompt can only fail wholesale.
2. **Self-correction is only viable per-step**. You can't retry "the whole thing" cheaply or coherently; you need to know which output failed which check.
3. **Each step's output is reusable**. A user might want the Boolean query alone, or might want to feed the JD signals into a different downstream tool. Forcing everything through one prompt couples them.

**If you collapse Steps 1 and 2 specifically:** you lose the explicit structured representation of the JD. Step 2 currently gets a clean JSON object describing the role; if it instead worked from raw JD text, the model would re-extract signals on the fly inside its strategy reasoning, and those signals would be:

- **Invisible** (not in the trace, can't be audited)
- **Inconsistent** across runs (the model picks different signals each time)
- **Mixed with strategy reasoning**, making it hard to tell whether bad strategy came from misreading the JD or from bad strategic thinking

You'd lose the ability to diagnose Step 2 failures, and you'd lose a clean handoff that downstream steps (3 and 4) also depend on. The cost of one extra LLM call is much smaller than the cost of opaque failures.

### Which parts used AI vs. my own judgment?

**Used AI for:**
- Drafting the initial scaffolding of `pipeline.py` (refined heavily by hand).
- Idea generation for prompt phrasing.
- Drafting the sample JD content.

**My own judgment:**
- The seniority edge-case decision (inferred default + trace note) — this is a product call, not a code call.
- Which output to guard with the bias scanner, and the choice to flag-not-block (the assignment asked for the *reasoning* on this).
- The structure of the self-correction feedback loop (explicit, per-failure feedback passed into the next attempt's prompt, instead of just re-running the same prompt).
- The decision to validate `specific_detail` against both the JD and the message text — interpreting "exact phrase from the JD" as an actual substring check rather than trusting the model.
- The "tests with a mock LLM" approach. The assignment doesn't ask for tests, but they're how I proved the retry loop works without burning API calls.
- Trace design — keeping notes short and structured so they're useful when scanning a failed run.

---

## Tests

```bash
python test_pipeline.py
```

Verifies the self-correction loop on three scripted scenarios (no API needed):
1. Attempt 1 too long → retry → attempt 2 missing detail → retry → attempt 3 passes
2. All 3 attempts fail → `PipelineError` raised, trace shows the failure

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ANTHROPIC_API_KEY is not set` | `export ANTHROPIC_API_KEY=sk-ant-...` |
| `No JSON found in LLM response` | The model returned prose. Re-run; if persistent, lower the temperature or shorten the prompt context. |
| Step 4 always exhausts retries | The JD is unusually short or has no concrete phrases. Add hiring manager notes via `--notes`. |
| Rate limit errors | The client backs off and retries automatically; persistent 429s mean you're over your tier limit. |
