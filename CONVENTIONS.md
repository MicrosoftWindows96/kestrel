# Conventions

Project-wide rules for commits, code, docs, and review. Enforced by pre-commit hooks and CI where possible.

## Commits

Format: [Conventional Commits](https://www.conventionalcommits.org/).

```
<type>(<scope>): <imperative subject ≤50 chars>

<optional body wrapped at 72 cols>

Signed-off-by: Name <email>
```

Allowed types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`, `ci`, `build`, `revert`.

### Hard rules

- Imperative mood: `add`, not `added` or `adds`
- Subject ≤50 chars, body wraps at 72
- One logical change per commit
- Linear history: rebase, no merge commits on `main`
- All commits SSH-signed by maintainer (`git config gpg.format ssh`)
- All commits carry `Signed-off-by:` (DCO) — `git commit -s`
- No tool-attribution or generator metadata in commit messages
- No `Co-Authored-By:` lines
- ASCII hyphen `-` only; no em-dash, no en-dash
- No section references in commit bodies (`see section 3.2`, `per spec.md#foo`); commits stand alone

### Vocabulary blocklist

Reject commits containing these words (case-insensitive) in subject or body:

```
implemented      implementation       comprehensive
robust           seamless             leverage
leverages        leveraging           delve
delves           delving              furthermore
moreover         holistic             streamline
streamlines      elevate              elevates
in this commit   it is worth noting   it's worth noting
key takeaway     as an AI             let me know if
i hope this      feel free to
```

Pre-commit hook enforces. Hook file: `.githooks/commit-msg`.

### Examples

Good:

```
feat(fetcher): add Scrapling stealth session wrapper

Wrap StealthyFetcher with project-default args (block_webrtc,
hide_canvas, dns_over_https). Expose async session pool.

Signed-off-by: MicrosoftWindows96 <spam@zagrosi.com>
```

Bad:

```
feat: implemented comprehensive fetcher solution — leverages Scrapling

Robust implementation that elevates the scraping experience.
```

## Code style

- Python 3.12+, `from __future__ import annotations` everywhere
- Type hints on all public APIs; `mypy --strict` in CI
- Format: `ruff format`
- Lint: `ruff check` (rules: E, F, I, N, UP, B, S, A, C4, RET, SIM, ARG, PT, RUF)
- No `utils.py`, `helpers.py`, `common.py` — name modules by purpose
- `from __future__ import annotations` first import, after module docstring
- Prefer dataclasses (`@dataclass(frozen=True, slots=True)`) over `dict` for structured data
- No `**kwargs` passthrough on public APIs
- Functions ≤50 lines target; if longer, split
- One class per file when class has more than ~30 lines
- Imports grouped: stdlib, third-party, local — `ruff` enforces

## Docs style

- User-facing docs (README, LEGAL, PRIVACY, etc.): readable English, concise
- No em-dash or en-dash anywhere; ASCII hyphen only
- Tables OK; bullet lists OK; avoid prose paragraphs over 4 lines
- Code blocks language-tagged
- File references format: `path/to/file.py:line` for navigation

## Planning

All planning artifacts live under `.planning/` which is gitignored. Never commit planning files.

```
.planning/
  deep-project/    decomposition output from /deep-project
  deep-plan/       per-unit TDD plans from /deep-plan
  reviews/         triple-review artifacts (one per commit)
  scratch/         notes, drafts, exploration
```

`.planning/` survives across sessions on local disk; treat as personal scratchpad.

## Review pipeline

Every commit to `main` requires three independent automated review passes before merge:

```
Pass 1   bugs and logic errors
Pass 2   convention adherence and vocabulary blocklist
Pass 3   security, privacy, and PII handling
```

Each pass runs as an independent process so a single failure mode in one pass cannot mask issues for the next. Tooling choice for each pass lives in maintainer-private notes and may rotate over time; the public contract is that three independent passes run.

Review outputs cached in `.planning/reviews/<sha>.md` (gitignored).

A commit may merge only if all three passes report no blocking issues. Non-blocking suggestions tracked in next-iteration backlog.

## Branches

- `main`: protected, signed commits only, linear history, all reviews passed
- `feat/<short-slug>`: feature branches
- `fix/<short-slug>`: bug fixes
- `chore/<short-slug>`: tooling, deps, refactors
- Branch lifetime ≤7 days target

## Files explicitly never tracked

See `.gitignore`. Notably:

- `.planning/`
- `.env`, secrets, keys
- `*.sqlite`, quote DBs (PII)
- Logs, screenshots, HAR files

## Pre-commit hooks (planned)

```
ruff format --check
ruff check
mypy --strict
pytest -q (mock-site only)
gitleaks (secret scan)
commitlint (subject/body rules + AI-tell blocklist)
```

Configured via `.pre-commit-config.yaml`. Mandatory; CI re-runs identical checks.
