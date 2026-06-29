# Zetarix — Department Handbook

This folder is the **delegation map** for Zetarix (RDTII AutoExtract). It splits the
codebase into **4 departments**, each owned end-to-end by a developer or small team.

The split follows the **ports & adapters (hexagonal)** core principle: the domain
(`backend/core/`) knows nothing about FastAPI, Next.js, Claude, Tesseract, or Postgres.
Every concrete tool is an adapter wired at the edge. A *swap = changing one factory or
config entry.* No department is allowed to break that seam.

## The 4 departments

| # | Department | Owns (file structure) | Modularity (functionality) | Agent |
|---|---|---|---|---|
| 01 | [Scraper / Botting](01-scraper/README.md) | `backend/adapters/botting/` | How a URL becomes cleaned, structured sections (transport → presentation → application + site scaffolds) | `zx-scraper` |
| 02 | [Pipeline & Evaluation](02-pipeline-eval/README.md) | `backend/core/pipeline/*` (minus output), `backend/core/domain/`, `backend/adapters/{extraction,clustering,llm}/` | Tagging, provision extraction, the **F1 scoring harness**, concept-graph clustering, LLM middleman | `zx-pipeline` |
| 03 | [Platform & Contracts](03-platform-contracts/README.md) | `backend/core/ports/`, `backend/app/`, `backend/run.py`, `output_emitter.py`, `golden_dataset.py` | The interface seam everyone depends on: ports, CLI, FastAPI, the 13-column output contract, golden-dataset ground truth | (shared / lead-owned) |
| 04 | [Frontend / Reviewer UI](04-frontend-reviewer/README.md) | `frontend/src/`, `frontend/app/` | The human-review console: findings table, filters, F1/stats, accept/reject, data-adapter swap point | `zx-frontend` |

## How to read each department README

Per the team convention, the docs are **separated two ways**:

- **In `docs/` → separated by FILE STRUCTURE.** Each department has its own folder
  (`docs/departments/0X-name/`) holding its `README.md` and `component.puml`.
- **Inside each README → separated by MODULARITY OF FUNCTIONALITY.** Each README is
  organized by *what the modules do*, not by file type — with the file structure listed
  as a reference table, then the functional modules, then the public surface and the
  port seams, then reverse-prompting hooks for delegating tasks.

## Reverse-prompting workflow

Each README ends with a **Reverse-Prompting Hooks** section: ready-made task seeds you
can hand to a developer (or an AI agent) without re-explaining the architecture. The
pattern is always:

> *"Within `<department scope>`, implement `<change>`. You may only touch files under
> `<owned paths>`. You must not change any port signature in `backend/core/ports/`.
> Verify with `<test command>`."*

This keeps the hexagonal boundary intact while letting work happen in parallel.

## Diagrams

Each department ships a **component diagram** (`component.puml`, PlantUML). Render with:

```powershell
# Requires the PlantUML jar or the VS Code PlantUML extension
java -jar plantuml.jar docs/departments/01-scraper/component.puml
```

The diagrams show the modules of a department, the **ports** they implement or depend
on, and how they connect to the agnostic core — the seam that must never be crossed
directly.

## The one rule that binds all departments

> Nothing in `backend/core/` imports a concrete adapter. Departments talk to each other
> **only through the ports in `backend/core/ports/`** (Department 03). If you find
> yourself importing `playwright`, `networkx`, `fastapi`, or a vendor SDK inside
> `core/`, stop — that belongs in an adapter.
