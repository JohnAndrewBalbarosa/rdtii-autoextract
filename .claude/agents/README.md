# Zetarix Subagent Roster & Orchestration Playbook

Project-scoped subagents for **Zetarix / RDTII AutoExtract**. The main session acts as the
**mastermind orchestrator**: it plans, decomposes, dispatches, and integrates. Subagents are
**domain-scoped, minimal-tool, conclusion-returning** workers — tuned to spend tokens where
they matter and stay cheap where they don't.

## Roster

| Agent | Domain | Model | Typical effort |
|-------|--------|-------|----------------|
| `zx-scraper` | L4 transport, L6 dom_cleaner, L7 scaffolds (Playwright, BS4, selectors) | sonnet | medium · high for tricky DOM heuristics |
| `zx-pipeline` | `core/pipeline/` detector + **golden_dataset + scoring/F1**, extraction, clustering | sonnet | high (matching/F1 is subtle) |
| `zx-frontend` | `frontend/` Next.js reviewer console | sonnet | medium |

### Reused built-ins (no custom file)

- **Explore** — cheap read-only recon / fan-out search. Ask for conclusions, not dumps.
- **tdd-guide** — enforce tests-first for new behavior.
- **python-reviewer** — mandatory code review before commit.
- **security-reviewer** — when a change touches input handling, network, browser automation, or files.
- **build-error-resolver** — minimal-diff fixes when build/tests go red.

## Mastermind loop

1. **Recon** — dispatch `Explore` (cheap) to locate files/patterns. Conclusions only.
2. **Decompose** — orchestrator splits work into single-domain tasks.
3. **Implement (TDD)** — dispatch the matching `zx-*` worker with a scoped task and an explicit
   "reuse existing utilities" instruction.
4. **Review** — `python-reviewer` (+ `security-reviewer` for boundary/network/browser work).
5. **Green build** — `build-error-resolver` if pytest/build fails.

## Token discipline (why this roster is "minimal")

- **Right model per task**: Haiku-class for search/mechanical, Sonnet for implementation,
  Opus (orchestrator) only for hard cross-domain reasoning and planning.
- **Minimal tools** per agent — each only gets Read/Write/Edit/Bash/Grep/Glob, scoped to its layer.
- **One domain per dispatch** — no agent reaches across layers; cross-cutting concerns are flagged
  back up to the orchestrator.
- **Conclusions, not dumps** — every agent returns what changed + test results, never whole files.
- **Parallel only when independent** — dispatch multiple `zx-*` agents in one message only when their
  files don't overlap.
