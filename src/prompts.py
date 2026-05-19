"""
All prompts live in one place so reviewers can read the prompt strategy quickly.

Each prompt:
  - Specifies the exact JSON schema we want back.
  - Reminds the model to return JSON only (no prose, no fences).
  - Hands the relevant prior-step context as JSON so the model can reason
    on a stable structure instead of free text.
"""

# Step 1: extract_jd_signals
EXTRACT_JD_SIGNALS = """You are a senior technical recruiter parsing a Job Description (JD).

Extract structured signals from the JD below. Be concrete. If a signal is not present
in the JD, set its value to null (do not invent).

Return ONLY a JSON object with this exact shape (no markdown, no prose, no fences):

{{
  "role_type": "string — e.g. 'Backend Engineer', 'ML Research Engineer', 'GTM Lead'",
  "required_skills": ["string", ...],
  "nice_to_have_skills": ["string", ...],
  "seniority_indicators": ["string", ...],
  "company_stage": "string or null — e.g. 'seed', 'Series A', 'public', null if unclear",
  "domain": "string or null — e.g. 'fintech', 'devtools', 'biotech'",
  "missing_information": ["string", ...]
}}

JOB DESCRIPTION:
\"\"\"
{jd}
\"\"\"

HIRING MANAGER NOTES (optional context):
\"\"\"
{hm_notes}
\"\"\"
"""


# Step 2: generate_search_strategy
GENERATE_SEARCH_STRATEGY = """You are a recruiter building a sourcing plan.

Given the extracted JD signals below, produce a candidate search strategy.

Return ONLY a JSON object with this exact shape (no markdown, no prose, no fences):

{{
  "target_backgrounds": ["string — concrete past roles or backgrounds to look for", ...],
  "target_companies": ["string — specific companies OR a company archetype like 'early-stage AI infra startups'", ...],
  "keywords": ["string — role-relevant skills and domain keywords", ...],
  "seniority": "string — recommended seniority level(s); if signals are ambiguous, say so and propose a range"
}}

Guidance:
  - target_backgrounds should be specific (e.g. 'IC4-IC5 backend at a payments company'),
    not generic ('experienced engineer').
  - target_companies should mix named comparables with archetypes so the recruiter has
    breadth to source from.
  - keywords should be the terms you'd plug into a Boolean search.

JD SIGNALS:
{signals}
"""

# Step 3: generate_boolean_query
GENERATE_BOOLEAN_QUERY = """You are building a LinkedIn Recruiter / sourcing-tool Boolean query
based on the search strategy below.

Return ONLY a JSON object with this exact shape (no markdown, no prose, no fences):

{{
  "boolean_query": "string — a single, valid Boolean query"
}}

Rules for the boolean_query string:
  - Use AND, OR, NOT in uppercase.
  - Quote multi-word terms with straight double quotes: \"Generative AI\".
  - Group OR-clauses in parentheses.
  - Keep it focused (8-15 terms is a good target). A query nobody will paste in is a bad query.
  - Do NOT include line breaks.

Example shape:
  (\"LLM\" OR \"Generative AI\") AND (Python OR Go) AND (startup OR \"Series A\")

SEARCH STRATEGY:
{strategy}
"""


# Step 4: generate_outreach_message (with self-correction feedback)
GENERATE_OUTREACH = """You are writing a recruiting outreach message for a top-of-funnel candidate.

Hard constraints:
  - Total length of `outreach_message` MUST be under {char_limit} characters.
  - `specific_detail` MUST be an exact phrase copied verbatim from the JD below,
    AND that exact phrase must appear inside `outreach_message`.
  - Tone: warm, peer-to-peer, startup-native. NO generic AI phrases like
    \"I came across your profile and was impressed by your background\",
    \"reach out regarding an exciting opportunity\", or \"perfect fit\".
  - Lead with WHY this person specifically.
  - End with a low-friction CTA (e.g. \"open to a quick chat?\").

Return ONLY a JSON object with this exact shape (no markdown, no prose, no fences):

{{
  "outreach_message": "string — the message itself",
  "specific_detail": "string — the exact phrase from the JD you used to personalize"
}}

FEEDBACK FROM PRIOR ATTEMPT (if any):
{feedback}

JOB DESCRIPTION (your source for `specific_detail` — copy a phrase verbatim from here):
\"\"\"
{jd}
\"\"\"

JD SIGNALS:
{signals}

SEARCH STRATEGY:
{strategy}
"""


# Step 5: generate_candidate_summary
GENERATE_CANDIDATE_SUMMARY = """You are generating a candidate summary card for a recruiter's pipeline view.

The candidate is hypothetical (mock data) but the reasoning must be real:
  - Invent a plausible name and current_company that matches the search strategy.
  - key_skills must be drawn from the JD signals and search strategy.
  - fit_reason must reference the role's actual requirements.
  - concerns must surface a real, plausible gap (don't hand-wave with 'no concerns').

Return ONLY a JSON object with this exact shape (no markdown, no prose, no fences):

{{
  "name": "string",
  "current_company": "string",
  "key_skills": ["string", "string", "string"],
  "fit_reason": "string — 1-2 sentences, concrete",
  "concerns": "string — 1-2 sentences, an honest gap"
}}

CONTEXT:
JD signals:
{signals}

Search strategy:
{strategy}

Boolean query the recruiter will run:
{boolean_query}

Outreach message that will be sent:
{outreach_message}
"""
