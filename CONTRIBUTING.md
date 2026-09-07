# Contributing

## Setup

```bash
make venv                 # backend virtualenv + dev dependencies
cd frontend && npm ci     # frontend dependencies
```

## Before opening a pull request

```bash
make lint    # ruff check + ruff format --check + tsc --noEmit + eslint
make test    # the full backend suite
```

Both run in CI, along with a frontend build and a Docker image build.

## Conventions

**Deterministic by default.** Before reaching for the LLM, ask whether the
question has one correct answer. If it does — money, clearance, a score, a
threshold — write rules. The LLM layer is for language understanding, and every
feature must still work with `LLM_PROVIDER=mock`.

**Every score carries its reasons.** A new scoring signal must append a
`Reason` explaining itself, with a signed impact. A number a user cannot argue
with is a number they cannot trust.

**Never conflate CI and full-scope polygraphs.** This is load-bearing. If you
touch `services/clearance.py`, the tests in `tests/test_clearance.py` are the
specification.

**No outbound sending.** Adding a code path that transmits a message to a third
party is out of scope for this project.

**No real correspondence in the repository.** Sample data must be fictional,
with `*.example` email domains. A test enforces this.

## Adding a skill to the ontology

`services/skills.py`, in the `SKILLS` tuple. Set `proofability` honestly:

* `≥ 0.85` — demonstrable in a week or two of focused work
* `0.55–0.85` — weeks to a few months
* `≤ 0.15`, or `learning_difficulty="gated"` — a hard gate, meaning an external
  body controls access (a licensing board, a cleared program). "This takes a
  long time" is not a gate.

Add aliases for how the skill actually appears in postings. Very short aliases
need an entry in `MINING_DENYLIST` or `CASE_SENSITIVE_MINING`, or they will
match inside unrelated words — see the tests for what that looks like in
practice.

## Changing scoring behaviour

Weights, bands and thresholds belong in `services/scoring/config.py` so users
can override them, not inline in a scoring function. If you find yourself
typing a number into a dimension module, it probably belongs in the config.
