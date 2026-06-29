# AGENTS.md — Delegation, Kanban & Human-in-the-Loop Protocol

Instructions for any AI agent working in this repo. Read this before doing task work.
It governs how work is tracked on the GitHub Projects Kanban board and how the
**human-in-the-loop (HITL)** gate is enforced. (Claude Code also auto-loads `CLAUDE.md`,
which points here.)

---

## 0. Prerequisite check (do this first, every session)

Before any board operation, verify the GitHub CLI. Never assume it is installed or
authenticated; run both commands in the current session:

```bash
gh --version          # is gh installed?
gh auth status        # authenticated? what token scopes?
```

- **`gh` not installed** → STOP and guide the user: install from https://cli.github.com,
  then `gh auth login`. Do not fake board state.
- **Authenticated but token scopes lack `project`** → STOP and tell the user to run, in the
  session, the one interactive step (the agent cannot do OAuth):
  ```
  ! gh auth refresh -s project,read:project --hostname github.com
  ```
  Continue once they confirm.
- **No board exists yet** → bootstrap one (see §4).

Never invent issue/board state. If a command fails, surface it.

---

## 1. The board

- **Project:** "Zetarix Delegation" — https://github.com/users/JohnAndrewBalbarosa/projects/10
  (linked to this repo; `gh project list --owner JohnAndrewBalbarosa`).
- **Fields:** `Status` (Kanban), `Department` (01 Scraper / 02 Pipeline / 03 Platform /
  04 Frontend), `HITL Gate` (Yes/No), `Role` (AI / Human / AI + Human), `Start`, `Target`.
- **Issues** carry labels: `delegation`, `dept:*`, `hitl`, `model-training`. Each issue body
  has Context / Why / Scope / Acceptance criteria / HITL / Reverse-prompting seed.

The Kanban/Roadmap **view layout** is UI-only (the API cannot set it). If columns aren't
showing, tell the user: view ⌄ → Layout → Board, Group by `Status`.

## 2. Status lifecycle (move cards as work progresses)

```
Backlog → Todo → In Progress → In Review → Done
```

- **Pick up a task** → move it to **In Progress**; set yourself (`Role`) and dates if unset.
- **Finish implementing** (code written, tests green, change committed and pushed) → move to
  **In Review** and comment the result on the issue (what you did + how to verify).
- **AI work always stops at In Review. An AI agent must never move any item to Done**, close it
  as completed, or self-approve it. Only a human may perform the final review and move it to
  **Done** (see §3).

## 3. Human review gate (the hard rule)

Every AI-authored change is **proposed, not done**, until a human manually reviews the code.
The agent's job always ends at **In Review**, regardless of the `HITL Gate` value.

An item with **`HITL Gate = Yes`** (or `Role = AI + Human`) requires additional human
verification of logic and output, not only code review.

- The agent moves the card to **In Review** and clearly states **what the human must check**:
  - **Code** — read the diff / commit
  - **Logic** — is the approach/design correct
  - **Output** — does the produced result look right (e.g. the scrape JSON trace, the F1
    numbers, the extracted rows)
- The **human** verifies manually and, only if it passes, personally moves the card to
  **Done**. Telling the agent that a review passed does not authorize the agent to set Done;
  the human must perform the board transition.
- **Non-HITL** items (`HITL Gate = No`) still require human code review. Once tests pass and
  the change is committed/pushed, the agent moves the item to **In Review** and stops there.
- An AI agent must never set **Done** through the UI, `gh`, GraphQL, an API, automation, or a
  draft-card bootstrap operation.

### Output verification helpers (use these to make HITL fast)
- Scraping: `python -m tools.inspect_dom --url <u> --json out/trace.json --headless` →
  prints a reviewer reverse-prompt of kept vs skipped blocks + `potential_false_skips`
  (real text hiding in ignored divs). Present the borderline blocks; let the human decide
  KEEP/IGNORE.
- Always show the human a concrete **preview of the output** and your **skip/keep decisions
  with reasons** before asking them to sign off.

## 4. Bootstrap a board on a new repo (automation recipe)

If no board exists (or for another project), create it with gh:

1. `gh project create --owner <OWNER> --title "<REPO> Delegation"` (capture id + number);
   `gh project link <NUM> --owner <OWNER> --repo <OWNER>/<REPO>`.
2. Expand the built-in `Status` to **Backlog, Todo, In Progress, In Review, Done** via the
   GraphQL `updateProjectV2Field` mutation (this clears existing Status — re-set every item after).
3. Create single-selects `Department`, `HITL Gate` (Yes/No), `Role` (AI / Human / AI + Human);
   create DATE fields `Start`, `Target`.
4. Create labels (`delegation`, `dept:*`, `hitl`, `model-training`).
5. One issue per task with the rich body template; add each to the board; set
   Department / HITL / Role / Status / Start / Target.
6. Add historical shipped-work draft cards as **In Review**; a human may verify and move them
   to **Done**.

### gh gotchas (learned)
- `gh project item-list` defaults to 30 items → pass `--limit 100`.
- gh writes CRLF on Windows → strip `\r` (`tr -d '\r'`) before `item-edit --date`, else
  `parsing time "…\x0d"` errors.
- Setting a single-select needs the **option id** (from `field-list --format json`), not its name.
- Dedupe draft cards by title; **never delete real issues**.

## 5. Definition of Done and AI completion boundary

A task is ready for human review when: acceptance criteria met · tests green · change
committed and pushed · verification instructions and output preview posted. At that point,
the AI moves it to **In Review** and stops.

A task is **Done** only when a human has manually reviewed the code and personally moved the
card to Done. For `HITL Gate = Yes`, the human must also verify logic and output. An AI agent
must never perform the Done transition; otherwise the task stays in **In Review** or earlier.
