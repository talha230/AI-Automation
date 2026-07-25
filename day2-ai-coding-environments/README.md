# Day 2 — Comparing AI Coding Environments

> Framed around **architecture, security, and production readiness** — not feature
> checklists. Features change weekly; the *shape* of a tool (where the agent loop
> runs, where your code goes, who holds the keys, what you can audit) changes
> slowly and determines what the tool is actually safe and sensible to use for.

This is the start of the analysis, deliberately organised so it stays useful as
individual products evolve. Rather than rank named tools, it groups them into
**four architectural archetypes** and evaluates the archetypes. A product can
then be understood by which archetype it belongs to (and some straddle two).

*A note on scope:* this compares the environments as engineering systems. It is
model-agnostic — a good architecture with a weak model and vice-versa are both
possible, and model quality moves independently of the tool it's wrapped in.

---

## 1. The four archetypes

| Archetype | Where the loop runs | Where code lives | Canonical examples |
|---|---|---|---|
| **A. Editor-embedded assistant** | Vendor cloud, driven by your keystrokes | Your machine (editor buffer) | Inline completion + chat panels in IDEs; AI-native editors |
| **B. Local terminal agent** | Your machine (agent loop is a local process) | Your machine | Terminal-based coding agents / CLIs |
| **C. Autonomous cloud agent** | Vendor cloud (fully) | Vendor-provisioned sandbox | Hosted "give it a ticket" agents; agent-in-the-web offerings |
| **D. Harness / Agent SDK** | Wherever *you* deploy it | Wherever you deploy it | Agent SDKs and libraries you embed in your own infra |

The single most consequential design decision is **where the agent loop and the
code-execution sandbox live**, because it determines the data-egress boundary,
the blast radius of a mistake, and how you audit what happened. Everything below
follows from that.

```
                 loop on YOUR machine            loop in VENDOR cloud
              ┌──────────────────────────┬──────────────────────────┐
 code on      │  B. Local terminal agent │  A. Editor-embedded       │
 your machine │     (Aider, CLI agents)  │     (inline completion)   │
              ├──────────────────────────┼──────────────────────────┤
 code in      │  D. Harness / SDK        │  C. Autonomous cloud      │
 vendor cloud │  (you choose to deploy   │     agent (hosted "ship   │
 or your infra│   to cloud)              │     me a PR" services)    │
              └──────────────────────────┴──────────────────────────┘
```

---

## 2. Architecture

What to actually look at, beyond "does it have an agent mode":

- **Loop location.** Local loop (B, D-on-prem) means the orchestration, file reads,
  and tool calls happen on hardware you control; only model inference leaves. Cloud
  loop (A, C) means the vendor's orchestrator drives the work and sees more of your
  context by construction.
- **Execution sandbox.** Does generated code run on your box, in an isolated
  container you own, or in a vendor-hosted container? An isolated sandbox is the
  difference between "the agent ran a bad `rm`" being a container reset versus a
  workstation restore.
- **Context strategy.** Whole-repo embedding/RAG vs. on-demand file reads vs.
  long-context + compaction. This drives both cost and how much of your codebase is
  transmitted per request.
- **Model access.** Single-vendor lock-in vs. bring-your-own-key vs. multi-provider
  routing. Matters for cost control, for data-processing agreements, and for not
  being stranded when one model regresses.
- **Extensibility & interop.** A tool/plugin protocol (e.g. MCP), hooks, and a
  scriptable CLI determine whether the environment can reach *your* systems (issue
  tracker, CI, internal APIs) without bespoke glue — and whether you can insert
  policy at the seams.
- **Statefulness.** Stateless request/response (A) is simple and cheap to reason
  about; long-lived stateful sessions (C, some D) enable multi-hour autonomous
  work but add reconnection, replay, and orphaned-resource concerns.

| | A. Editor-embedded | B. Local terminal | C. Autonomous cloud | D. Harness / SDK |
|---|---|---|---|---|
| Loop location | Vendor cloud | **Local** | Vendor cloud | **Your choice** |
| Sandbox owner | You (editor host) | You (your shell) | Vendor container | You |
| Context transmitted | Selection + open files ± repo index | Files the agent reads | Full repo (cloned to vendor) | What you send |
| Model access | Usually single vendor | Often BYO-key | Usually single vendor | **BYO / any** |
| Extensibility | Editor plugin APIs | CLI + hooks + MCP | Web integrations, MCP | **Full — it's your code** |
| Best fit | Line-level velocity | Repo-level tasks with a human in the loop | Fan-out of well-scoped tickets | Building AI features / bespoke agents |

**Takeaway:** A optimises for latency and flow; B for control and transparency;
C for parallelism and hands-off throughput; D for embedding agentic behaviour
into a product you own. None is "most advanced" — they occupy different points on
the control-vs-autonomy curve.

---

## 3. Security

Security posture is mostly determined by the archetype, not by a settings page.
Evaluate along these axes:

### 3.1 Data egress boundary
- **A / C** send more of your code to the vendor by design (indexing, cloning).
  For proprietary or regulated codebases, the question is not "is it encrypted in
  transit" but "what is the data-retention and training policy, and can we get a
  zero-retention / no-train agreement in writing?"
- **B / D-on-prem** keep the repository local; only prompts and the files the agent
  chooses to read reach the model provider. Smaller, more auditable egress surface.

### 3.2 Credential & secret handling
The failure mode to fear: a secret ends up in the model's context (system prompt,
a file the agent `cat`s, an env dump) and is then persisted in history, logs, or a
provider's cache. Good environments:
- **Never place secrets in the prompt.** The mature pattern is egress-time
  substitution / proxied credentials — the sandbox sees an opaque placeholder and
  the real value is injected *after* the request leaves the sandbox, so agent-run
  code (even under prompt injection) can't read it.
- Route git/push auth through a proxy that injects the token outside the sandbox,
  rather than writing it into the container.
- Keep keys in a secret manager, not a committed `.env`. (See Day 1's config
  module for the small-scale version of this discipline.)

### 3.3 Execution isolation & permission model
- Does dangerous work run in an **isolated, disposable sandbox**? Container reset
  beats workstation recovery.
- Is there a **permission/approval gate** for hard-to-reverse actions (shell,
  network egress, file deletion, `git push`)? "Ask before X" with per-action
  granularity is the control that makes autonomy tolerable.
- Reversibility as a design input: read-only and idempotent tools can be
  auto-approved; destructive ones should be gated.

### 3.4 Prompt injection & supply chain
Any agent that reads untrusted content (a web page, a dependency's README, a PR
comment, tool output) can be steered by instructions hidden in that content. The
defensive posture that matters:
- Treat all external/tool-returned text as **data, not instructions**.
- Constrain the agent's capabilities (network allow-lists, tool allow-lists) so a
  successful injection has a small blast radius.
- Prefer environments where **egress is deny-by-default** and each outbound host is
  opted in.

| Security axis | A | B | C | D |
|---|---|---|---|---|
| Code stays on-prem | ✗ (indexed) | ✓ | ✗ (cloned) | ✓ if you self-host |
| Isolated execution sandbox | n/a (edits only) | ✗ (your shell) | ✓ (vendor container) | ✓ if you build it |
| Egress-time secret substitution | rare | via proxy/config | ✓ (mature offerings) | you implement |
| Per-action approval gates | limited | ✓ (common) | ✓ / policy-based | you implement |
| Injection blast-radius control | low risk (no exec) | medium | **depends on network policy** | you own it |

**Takeaway:** B minimises egress but runs code on your machine (isolate it
yourself). C can be *more* secure operationally — disposable sandbox, proxied
credentials, network allow-lists — *if* the vendor's data policy is acceptable.
That trade (data-boundary risk ↔ execution-isolation benefit) is the crux for
regulated teams.

---

## 4. Production readiness

"Can a serious team run this every day?" — measured by the boring properties, not
the demo.

- **Reproducibility & pinning.** Can you pin the model version and agent config so
  a run is repeatable, and roll back when a new model regresses? Versioned,
  declarative agent/environment definitions (config-as-code) beat clicking around a
  UI.
- **Auditability & observability.** Is there a durable trace of every tool call,
  file edit, and model request — with token/cost usage — that survives the session?
  You cannot govern what you cannot replay.
- **CI/CD & automation fit.** Can it run headless in a pipeline (triggered by an
  issue, a schedule, a webhook) and open a PR, not just live inside an IDE?
- **Team & governance.** SSO, role-based access, per-workspace policy, secret
  scoping, and org-wide guardrails — the difference between a solo tool and a fleet.
- **Cost predictability.** Token spend is the new cloud bill. Effort/budget controls,
  caching, and per-run accounting decide whether autonomy is affordable at scale.
- **Reliability & recovery.** Long autonomous runs need graceful handling of
  timeouts, disconnects, merge conflicts, and partial failure — plus a human
  off-ramp when the agent is stuck.
- **Maturity.** Stability of the API/CLI surface, breaking-change cadence, and the
  strength of docs and community support.

| Production axis | A | B | C | D |
|---|---|---|---|---|
| Reproducible / pinnable runs | weak | good (scriptable) | good (config-as-code) | **strong (you own it)** |
| Durable audit trail | weak | local logs | **strong (session traces)** | you build it |
| Headless CI/CD use | ✗ | ✓ | ✓ | ✓ |
| Team governance (SSO/RBAC) | via IDE licensing | limited | **strong** | you build it |
| Cost accounting | opaque per-seat | per-run visible | per-run visible | full control |
| Human off-ramp | native (you're in the editor) | native | needs design | you design it |

**Takeaway:** For *governed, auditable, repeatable* automation, C and D lead — C
because hosted platforms invest in traces, RBAC, and config-as-code; D because you
own every layer. B is production-grade for individual and small-team workflows
with a human in the loop. A is a productivity multiplier, not an automation
platform.

---

## 5. Choosing — a decision guide

| If your priority is… | Lean toward | Because |
|---|---|---|
| Fastest inner-loop coding, human always driving | **A. Editor-embedded** | Lowest latency, no orchestration overhead, edits stay local |
| Repo-scale tasks with review, minimal data egress | **B. Local terminal** | Local loop, transparent tool calls, code never cloned to a vendor |
| Parallelising many well-scoped tickets, hands-off | **C. Autonomous cloud** | Disposable sandboxes, proxied secrets, traces, runs from a webhook/schedule |
| Regulated code that can't leave your network | **B or D self-hosted** | Keep the loop and repo on infra you control |
| Shipping agentic features inside *your* product | **D. Harness / SDK** | You own the loop, the data path, and the deployment |
| Org-wide governance, audit, cost control | **C or D** | Config-as-code, RBAC, durable per-run accounting |

### Anti-patterns to avoid
- Judging tools by feature lists — features converge; **architecture and data
  boundaries don't.**
- Putting secrets anywhere the model's context can reach them.
- Granting an autonomous agent broad network + shell access with no allow-list or
  approval gate ("it worked in the demo" is not a threat model).
- Adopting an autonomous cloud agent without reading the **data-retention and
  training policy** first.
- Treating a stateless assistant (A) as if it were an automation platform (C/D).

---

## 6. Where this connects to Day 1

The Day 1 assistant is a **tiny archetype-D system**: a loop we own (FastAPI), a
data path we control, secrets kept out of the model's reach and out of git,
structured/validated I/O, and logging we can audit. The same three lenses —
**architecture, security, production readiness** — scale from that 200-line
service up to a full autonomous coding platform. Evaluate every AI coding
environment through them, and the marketing feature grid stops mattering.

---

*Living document — Day 2 of the series. Next: hands-on with one environment from
each archetype, applying this rubric to concrete workflows.*
