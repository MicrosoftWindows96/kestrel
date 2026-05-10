# Contributing

kestrel welcomes contributions to the core library, mock site, documentation, and example adapter. Contributions targeting real aggregators are also welcome but governed by additional rules below.

## Before you start

1. Read [LEGAL.md](LEGAL.md) and [PRIVACY.md](PRIVACY.md). Both shape what does and does not get accepted.
2. Read [CONVENTIONS.md](CONVENTIONS.md) for commit, code, and doc style.
3. Read [ADAPTERS.md](ADAPTERS.md) if you plan to contribute an adapter.

## License acceptance

By submitting a pull request you agree your contribution is licensed under AGPL-3.0-or-later, the same as the project. If your contribution incorporates code from another source, that source must be license-compatible with AGPL-3.0-or-later. Document the origin in the PR description.

## Developer Certificate of Origin

Every commit must carry a `Signed-off-by:` trailer (DCO). Use:

```bash
git commit -s
```

Which appends:

```
Signed-off-by: Your Name <your@email>
```

By signing off, you certify that you wrote the code or have the right to submit it under AGPL-3.0-or-later. Full text: https://developercertificate.org/

Pull requests with unsigned commits will not be merged.

## Pull request process

1. Fork the repo
2. Branch from `main` using one of: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`
3. Make commits following [CONVENTIONS.md](CONVENTIONS.md)
4. Open the PR with the template (auto-populated)
5. Maintainer runs the three-pass review pipeline (see CONVENTIONS.md)
6. Address review comments; force-push the same branch (we rebase, not squash-merge)
7. Maintainer merges via rebase

## Adapter contributions

Adapters targeting real third-party sites carry additional rules:

- The maintainer does not write or maintain such adapters; you do
- You attest in your PR that you have read and accepted the target site's Terms of Service
- You attest the data flow (which fields the adapter submits, where they go) is documented in the adapter README
- The adapter must not include your personal data; submit only adapter logic and selectors, not test profiles
- Tests for the adapter run against the mock site, not the real one

PRs that fail to attest these will be closed.

## Pre-commit hooks

Mandatory. Install with:

```bash
pre-commit install
```

Hooks run on every commit. CI re-runs the same hooks; bypassing locally does not help.

## Testing

```bash
uv run pytest
```

Tests must pass on Python 3.12 and 3.13. The mock site spins up automatically for integration tests. No test should hit any real third-party host.

## Style enforcement

```bash
uv run ruff format
uv run ruff check
uv run mypy
```

CI runs the same. PRs failing any of these will be marked needs-work.

## Communication

Discussions: GitHub Issues for feature ideas, bug reports, and design questions.

Chat: none. Email the maintainer for sensitive matters.

## What gets rejected

- Adapters performing personal-detail misrepresentation
- Code introducing telemetry, analytics, error reporting, or any phone-home behavior
- Code targeting real aggregators that ships in the maintainer's tree (versus a community plugin)
- Commit messages with vocabulary blocklist hits (see CONVENTIONS.md)
- Unsigned commits

## First-time contributors

Look for issues tagged `good-first-issue`. Documentation improvements, mock site enhancements, and example adapter polish are all reasonable starting points.
