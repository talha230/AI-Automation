# Day 1 — AI Requirements Assistant

A small but production-shaped FastAPI service that turns a plain-language product
idea into a **structured** software requirements document, using Claude with
enforced JSON output.

Give it *"an app that lets neighbours lend and borrow tools"* and it returns
functional requirements (MoSCoW-prioritised), non-functional requirements, user
stories with acceptance criteria, assumptions, out-of-scope items, risks with
mitigations, and clarifying questions — as validated JSON, not prose you have to
parse.

## What this demonstrates

| Day-1 goal | Where it lives |
|---|---|
| **FastAPI** | `app/main.py` — `/health` and `/requirements`, lifespan startup, request-id middleware |
| **Structured JSON outputs** | `app/schemas.py` defines a Pydantic `RequirementsDocument`; `app/assistant.py` passes it to `client.messages.parse(output_format=...)`, so the model is *constrained* to the schema and we get a typed object back |
| **Logging** | `app/logging_config.py` — configurable text/JSON formatter with a per-request correlation id |
| **Secure API key management** | `app/config.py` — key held as a `SecretStr`, loaded from the environment or a git-ignored `.env`, never logged (only a redacted form is), and `.env` is in `.gitignore` |

## Architecture

```
HTTP request ──▶ FastAPI (main.py)
                   │  request-id middleware, validation
                   ▼
              RequirementsAssistant (assistant.py)
                   │  builds prompt, calls Claude with a Pydantic output schema
                   ▼
              Anthropic API  ──▶ schema-constrained JSON
                   │
                   ▼
              RequirementsDocument (validated) ──▶ JSON response
```

Config (`config.py`) and logging (`logging_config.py`) are cross-cutting and
injected at startup.

## Setup

```bash
cd day1-requirements-assistant
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then edit .env and add your key
# or:  export ANTHROPIC_API_KEY=sk-ant-...
```

## Run

```bash
uvicorn app.main:app --reload
```

Then open the interactive docs at <http://127.0.0.1:8000/docs>, or:

```bash
curl -s http://127.0.0.1:8000/requirements \
  -H 'content-type: application/json' \
  -d '{"idea": "A mobile app for neighbours to lend and borrow tools",
       "audience": "Suburban homeowners"}' | jq
```

`GET /health` reports status and whether a key is configured (useful for probes).

## Test

```bash
pytest
```

The suite (`tests/`) runs **without an API key or network** — the schemas are
tested directly and the API is tested against a stubbed assistant, so CI stays
fast and hermetic. Live generation naturally requires a real key.

## Design notes

- **Model** defaults to `claude-opus-5` and is configurable via the `MODEL` env
  var (any structured-output-capable Claude model works).
- **Refusals** (`stop_reason == "refusal"`) and API errors are caught in
  `assistant.py` and surfaced as a clean `502` rather than a stack trace.
- **Credentials** resolve the way the SDK expects: an explicit `ANTHROPIC_API_KEY`
  wins, otherwise a bare client falls back to an `ant auth login` profile — so the
  code doesn't hard-code auth.
