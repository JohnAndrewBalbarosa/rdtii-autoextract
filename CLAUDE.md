# CLAUDE.md

This repo's agent operating rules live in **[AGENTS.md](AGENTS.md)** — read it first.

Key points (full detail in AGENTS.md):

- **Before board work:** check `gh` is installed + authenticated + has the `project` scope;
  if not, guide the user (do not fake state).
- **Track work on the Kanban board** (Projects #10 "Zetarix Delegation"): move cards
  Backlog → Todo → In Progress → In Review → Done as work progresses.
- **Human-in-the-loop:** items with `HITL Gate = Yes` are *proposed, not done*. The agent
  stops at **In Review** and tells the human exactly what to check (code / logic / output).
  Only a human moves a HITL item to **Done**. Never self-approve.
- **Show your work:** before asking for sign-off, present a concrete output preview and your
  keep/skip decisions with reasons (e.g. `tools/inspect_dom.py --json`).

See also [docs/departments/](docs/departments/README.md) for the per-department delegation
handbook and [docs/departments/DELEGATION_BACKLOG.md](docs/departments/DELEGATION_BACKLOG.md).
