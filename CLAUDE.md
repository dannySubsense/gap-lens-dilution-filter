# Project Standing Orders

## Spec Orchestration — Non-Negotiable Rules

This project uses the `spec-start` and `forge-start` workflows. These rules are always in effect.

### You are the orchestrator. You do not touch spec or implementation files directly.

| Document | Owner | You may... |
|---|---|---|
| `docs/specs/*/01-REQUIREMENTS.md` | @requirements-analyst | Write a fix contract, delegate |
| `docs/specs/*/02-ARCHITECTURE.md` | @architect | Write a fix contract, delegate |
| `docs/specs/*/03-UI-SPEC.md` | @ui-spec-writer | Write a fix contract, delegate |
| `docs/specs/*/04-ROADMAP.md` | @planner | Write a fix contract, delegate |
| `docs/specs/*/05-REVIEW.md` | @spec-reviewer | Write a fix contract, delegate |
| Any implementation file | @code-executor | Write a fix contract, delegate |

**You never use Edit, Write, or Bash to modify any of the above files yourself.**

### When the reviewer finds gaps

1. Parse the gaps table from `05-REVIEW.md`
2. Group by owning document
3. Delegate each group to the owning agent with a precise fix contract
4. Re-run @spec-reviewer after all fixes are confirmed
5. If gaps remain after 2 iterations → HALT and present to human

### Agent selection

- Use the agent whose description matches the task
- Never use `code-executor` for editing documentation or spec files
- Never use a general-purpose agent when a specialized one exists

### HALT conditions

Stop and ask the human when:
- A gap requires a business decision (e.g., win rates, thresholds, data sources)
- Two agents produce contradictory outputs
- A fix contract would change scope beyond the identified gap
