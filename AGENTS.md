# AGENTS.md — fac

## What is this repo?

`fac` is a Phoenix/Elixir web application AND its control-plane infrastructure. It implements a deterministic PR agent loop where AI agents (Codex, Claude) autonomously pick up issues, write code, and open PRs that pass through machine-verifiable review before merge.

## Build Commands

```bash
# Install dependencies
mix deps.get

# Compile (strict — warnings are errors)
mix compile --warnings-as-errors

# Run tests
mix test

# Run linter
mix credo --strict

# Run type checker
mix dialyzer

# Check formatting
mix format --check-formatted

# Start dev server
mix phx.server
```

## Architecture

```
lib/fac/          — Core business logic (Elixir contexts)
lib/fac/harness/  — Harness engineering modules (risk classifier, evidence)
lib/fac_web/      — Phoenix web layer (controllers, views, router)
config/           — Application configuration (Sentry, DB, etc.)
harness/          — Machine-readable contracts and evidence
scripts/harness/  — Python CI scripts (risk gate, policy resolver, rerun dedupe)
.github/workflows/ — GitHub Actions (risk-policy-gate, CI pipeline, agent workflows)
test/             — ExUnit tests
```

## Key Contracts

- `harness/contract.json` — Central policy contract consumed by all workflows
- `.coderabbit.yaml` — CodeRabbit review configuration

## PR Loop

1. Issue created (Linear or GitHub) → label applied (`agent:codex` or `agent:claude`)
2. Agent creates branch, writes code, opens PR
3. `risk-policy-gate` classifies risk tier, checks policy
4. CodeRabbit reviews on current-head SHA
5. CI fanout (ExUnit, Credo, Dialyzer, format, secrets scan)
6. All pass → ready for human merge

## Gotchas

- Always run `mix format` before committing
- `harness/contract.json` is the source of truth for risk tiers and merge policy
- Python scripts in `scripts/harness/` must pass `python3 -m pytest tests/ -v`
- Sentry DSN is configured via `SENTRY_DSN` environment variable
- Database config is in `config/dev.exs` — requires PostgreSQL
