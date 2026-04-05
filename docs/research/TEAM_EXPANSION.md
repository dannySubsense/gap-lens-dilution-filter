# Research Team Expansion Log

**Project:** gap-lens-dilution-filter  
**Last updated:** 2026-04-05  

This document tracks additions to the Claude agent team and command set made to support the research phase of this project. Each entry records what was added, where it lives, why it was created, and what it is responsible for.

---

## Existing Team (Pre-Research Phase)

These agents and commands were already in place before the research pivot. Listed here for completeness.

### Agents (`~/.claude/agents/`)

| Agent | Role | Used in |
|-------|------|---------|
| `requirements-analyst` | Extracts requirements from vague input | `/spec-start` |
| `architect` | Designs technical architecture | `/spec-start` |
| `ui-spec-writer` | Defines screens and interaction flows | `/spec-start` |
| `planner` | Breaks architecture into roadmap slices | `/spec-start` |
| `spec-reviewer` | Reviews spec docs for completeness | `/spec-start` |
| `code-executor` | Implements code per spec | `/forge-start` |
| `test-writer` | Writes tests per spec | `/forge-start` |
| `test-runner` | Runs test suites | `/forge-start` |
| `qc-agent` | Verifies implementation against spec | `/forge-start` |
| `research` | Investigates external questions, APIs, docs | Ad-hoc |
| `data-auditor` | Audits dataset quality | Data pipeline work |
| `data-executor` | Executes data operations | Data pipeline work |
| `architect` | Architecture design | `/spec-start` |
| `doc-writer` | Writes documentation | Ad-hoc |
| `github-ops` | Git and GitHub operations | Ad-hoc |

### Commands (`~/.claude/commands/`)

| Command | Purpose |
|---------|---------|
| `/spec-start` | Orchestrates 5-document spec cycle for software features |
| `/forge-start` | Orchestrates implementation from approved spec |
| `/data-spec-start` | Variant of spec-start for data pipeline features |

---

## Research Phase Additions — 2026-04-05

### New Agents

#### `research-contract-writer`
**File:** `~/.claude/agents/research-contract-writer.md`  
**Model:** Opus  
**Why created:** The standard spec-reviewer checks functional completeness but not research validity. A backtest pipeline can be functionally correct and still produce findings that cannot be cited — due to look-ahead bias, survivorship bias, or insufficient reproducibility documentation. A dedicated agent is needed to define these constraints before implementation begins, not after.

**Responsible for:**
- Writing `RESEARCH-CONTRACT.md` for any research pipeline spec
- Defining output schema contracts (exact columns, types, valid ranges)
- Making look-ahead bias constraints explicit (what data was available at time T)
- Defining survivorship bias handling rules
- Setting sample size thresholds before conclusions can be drawn
- Establishing reproducibility requirements (versioning, determinism)
- Defining white paper citation standards for each output

**Inputs:** research log, hypothesis doc, methodology doc, 01-REQUIREMENTS.md, 02-ARCHITECTURE.md  
**Output:** `RESEARCH-CONTRACT.md`  
**Invoked by:** `/research-spec-start` (step 4)

---

#### `research-spec-reviewer`
**File:** `~/.claude/agents/research-spec-reviewer.md`  
**Model:** Opus  
**Why created:** The standard `spec-reviewer` checks whether requirements, architecture, and roadmap are consistent with each other. For research pipelines, that is necessary but not sufficient. The reviewer must also check that the architecture satisfies the Research Contract — specifically that point-in-time joins are correct, survivorship bias is handled, and outputs are traceable to hypothesis sub-claims.

**Responsible for:**
- All standard spec review checks (functional completeness, document consistency)
- Verifying Research Contract is present and complete
- Checking every data join for look-ahead bias
- Checking survivorship bias handling
- Verifying hypothesis traceability (every output column maps to a sub-claim)
- Verifying methodology alignment

**Inputs:** all spec documents + Research Contract + research methodology + hypothesis  
**Output:** `05-REVIEW.md` (with both functional gaps table and research validity gaps table)  
**Invoked by:** `/research-spec-start` (step 6)

---

### New Command

#### `/research-spec-start`
**File:** `~/.claude/commands/research-spec-start.md`  
**Why created:** `/spec-start` assumes the output is a software feature. Research pipelines have different constraints: no UI, outputs must satisfy research validity criteria, requirements must trace to hypothesis sub-claims, and review must cover look-ahead bias and survivorship bias. A separate command was needed rather than modifying the existing `/spec-start`.

**Sequence:**
1. Read research anchor docs (RESEARCH_LOG.md, HYPOTHESIS.md, METHODOLOGY.md)
2. `@requirements-analyst` → `01-REQUIREMENTS.md`
3. `@architect` → `02-ARCHITECTURE.md`
4. `@research-contract-writer` → `RESEARCH-CONTRACT.md` *(new step)*
5. `@planner` → `04-ROADMAP.md`
6. `@research-spec-reviewer` → `05-REVIEW.md` *(uses new agent)*
7. Human review

**Key differences from `/spec-start`:**
- No `03-UI-SPEC.md` step
- Research Contract step added between architecture and roadmap
- Uses `@research-spec-reviewer` instead of `@spec-reviewer`
- Output directory is `docs/research/{feature}/` not `docs/specs/{feature}/`
- Requirements must be anchored to hypothesis sub-claims

---

## Intended Usage

For the current research project (dilution filter backtest pipeline):

```
/research-spec-start
```

This will kick off the spec cycle for `docs/research/backtest-pipeline/` anchored to the experiment design logged in `docs/research/RESEARCH_LOG.md` on 2026-04-05 (Research Question RQ1).

---

## Future Additions (Anticipated)

As the research progresses, additional agents may be needed:

| Anticipated Agent | Purpose | Trigger |
|------------------|---------|---------|
| `teacher-labeler` | Manages GPT-4/Claude teacher labeling campaign | Phase R2 (classifier validation) |
| `backtest-validator` | Validates backtest output against Research Contract | After Phase R1 |
| `findings-writer` | Writes structured findings documents to white paper standard | After each experiment |

These will be documented here when created.
