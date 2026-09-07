# Architecture

## The organising principle

The system is deliberately **not** "an LLM decides everything". Work is split by
whether a question has one correct answer:

| Deterministic code | LLM |
| --- | --- |
| Salary and equity normalisation | Reading prose that regexes cannot |
| Clearance and polygraph classification | Company, seniority, customer type |
| Skill normalisation against an ontology | Ownership / research / customer-facing intensity |
| Every score and weight | Requirement phrases written as narrative |
| Hard-gate detection | Polishing a drafted reply |
| Recommended action | — |
| Missing-information detection | — |

The LLM is an **optional enrichment layer**. `LLM_PROVIDER=mock` (the default)
disables it entirely, and the application — including the documented acceptance
example — works identically, just with fewer of the fuzzy fields populated.
That property is what makes the test suite fast, free and deterministic.

## System diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Browser                                                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  Next.js (App Router, TypeScript)                                    │  │
│  │  /  dashboard   /analyze   /examples   /opportunities/[id]           │  │
│  │  /profile       /resumes   /equity                                   │  │
│  │  Server components fetch on the server; interactive panels are        │  │
│  │  client components that call the API directly.                        │  │
│  └───────────────────────────────┬──────────────────────────────────────┘  │
└──────────────────────────────────┼─────────────────────────────────────────┘
                                   │  REST / JSON
┌──────────────────────────────────▼─────────────────────────────────────────┐
│  FastAPI                                                                   │
│                                                                            │
│   api/routes ──▶ services/analysis.py  (the only module that knows the     │
│                   │                      whole flow)                        │
│                   │                                                        │
│    ┌──────────────┼───────────────────────────────────────────┐            │
│    ▼              ▼                    ▼                      ▼            │
│  extraction   scoring/            missing_info          response_draft     │
│    │            ├ fit                  │                     │             │
│    │            ├ career_capital       │                     │             │
│    │            ├ proofability         │                     │             │
│    │            ├ compensation         │                     │             │
│    │            ├ lifestyle            │                     │             │
│    │            ├ upside               │                     │             │
│    │            ├ risk                 │                     │             │
│    │            └ engine (weights,     │                     │             │
│    │               action ladder)      │                     │             │
│    │                                   │                     │             │
│    ├── normalize.py   (money, hours, travel, YOE — regex only)             │
│    ├── clearance.py   (TS/SCI, CI vs FSP — regex only)                     │
│    ├── skills.py      (ontology, aliases, proofability, implications)      │
│    └── job_families.py(title → family)                                     │
│                                                                            │
│   llm/  base ─ anthropic ─ openai ─ mock      resume_match.py  equity.py   │
│         (one interface; provider chosen by env)                            │
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   │  SQLAlchemy 2.0
┌──────────────────────────────────▼─────────────────────────────────────────┐
│  PostgreSQL (pgvector image; vectors stored as JSON today)                  │
│  candidate_profiles · resume_documents · job_opportunities                  │
│  recruiter_messages · opportunity_scores · user_decisions                   │
└────────────────────────────────────────────────────────────────────────────┘
```

## The analysis pipeline

```
raw text
   │
   ├─▶ rule_extract()                    always runs, never fails
   │      salary · equity · clearance · polygraph · remote · travel · hours
   │      · YOE · skills (ontology) · job family · characteristics
   │      + a per-field confidence map
   │
   ├─▶ llm_extract()                     only when a provider is configured
   │      company · seniority · customer type · ownership · research intensity
   │      · requirement phrases
   │
   ├─▶ merge_extractions()
   │      DETERMINISTIC_FIELDS (money, clearance, polygraph, hours, travel,
   │      YOE, remote status) are NEVER overwritten by the model.
   │      Everything else: the model fills gaps and adds to list fields.
   │
   ├─▶ score_opportunity()               seven dimensions, each with reasons
   │      fit ─┬─ produces the gap list
   │           └─ gaps are classified: already demonstrated / proofable / hard gate
   │      proofability consumes the gaps
   │      overall = Σ(weightᵢ × scoreᵢ), capped when a hard gate exists
   │
   ├─▶ detect_missing_information()      priority-ordered, §5
   │
   └─▶ generate_response_draft()         template first; LLM polish is optional
          and is rejected if it drops a required question
```

## Why the scores are separate

A single number cannot express "this job pays extremely well, would compound
your career, and you are missing two skills you could demonstrate in a
fortnight". Collapsing those into one figure destroys the only information the
user actually needs to act on. So each dimension is computed, weighted and
displayed independently, and every one carries its reasons.

Risk is the clearest case: it is reported beside the overall score rather than
subtracted from it, because a high-risk, high-upside role is a legitimate
choice — but only if you can see that you are making it. `risk_penalty_weight`
lets a user opt into subtraction.

## Route structure

The dashboard lives in a `(dashboard)` route group rather than at `app/page.tsx`.
Route groups do not affect the URL — it still serves `/` — and the reason is
narrow but real: a `loading.tsx` at the app root creates a Suspense boundary
above *every* nested route, which commits a `200` before `notFound()` on
`/opportunities/[id]` can set a `404`. Scoping the skeleton to the group keeps
both the loading state and the correct status code.

## Correcting an extraction

Extraction is best-effort, and the honest response to that is an edit form
rather than a disclaimer. `PATCH /api/jobs/{id}` accepts any extracted field;
the route marks each corrected field `high` confidence (a human typed it) and
appends `+manual` to `extraction_method` — once, not per edit. The UI re-scores
immediately on save, so correcting a polygraph from *unspecified* to *full
scope* visibly moves the verdict.

`notes` is excluded from the confidence map: it was never extracted, so calling
it a high-confidence extraction would be meaningless.

## Data model notes

* **IDs are string UUIDs.** The same DDL runs on Postgres and on the SQLite
  database the test suite uses, so tests exercise the real schema.
* **List and dict fields use a portable JSON column** (JSONB on Postgres).
* **Scores are append-only.** Re-scoring writes a new `opportunity_scores` row,
  so changing your weights and re-running keeps the history of what the system
  thought before.
* **Drafts and approvals are stored separately.** `response_draft` holds what
  the system generated; `approved_response` holds what the human signed off.
  Editing never overwrites the generated text, so the record stays auditable.
* **Embeddings are JSON float arrays** and cosine similarity is computed in
  Python. For one person's résumé variants this is instant. Moving to a
  pgvector column is a migration, not an application change: only
  `services/embeddings.py` and `resume_match.cosine_similarity` touch the
  representation.

## Human-in-the-loop

There is no code path in this repository that sends an email, a LinkedIn
message, or anything else outbound. The system:

1. drafts a reply,
2. stores it with status `draft_generated`,
3. waits for a human to approve, edit, reject or ignore it.

"Approved" means *the user is happy to send this themselves*. Sending remains a
manual act in their own mail client. Automating it is deliberately left out of
v1 rather than left as a disabled feature.

## Failure behaviour

| Failure | Behaviour |
| --- | --- |
| No LLM API key | Deterministic extraction only; everything still works |
| LLM provider errors | Retried with backoff, then the rules-only result is used |
| LLM returns malformed JSON | Parsed leniently, then discarded if unusable |
| LLM polish drops a question | The template draft is kept instead |
| Embeddings unavailable | Résumé matching falls back to keyword/ontology overlap |
| Malformed `scoring_config` | Rejected at the API boundary; defaults used with a warning |
| A sample fails to seed | Logged; the remaining samples still load |
| API unreachable from the UI | `error.tsx` names the likely cause and offers a retry; the nav badge reads "API offline" |
