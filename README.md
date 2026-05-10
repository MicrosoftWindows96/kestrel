# kestrel

Educational research project. Browser-automation harness for fetching personal UK car insurance quotes across multiple aggregators with human-in-the-loop supervision.

Named for the small UK falcon. Patient watcher: hovers above a field, observes, picks the right moment.

## Status

**Alpha. Educational and personal-use only.** Not a product. Not for commercial use. Not for use against any site whose Terms of Service you have not personally reviewed and accepted. See [LEGAL.md](LEGAL.md) before doing anything.

## Intent

UK car insurance shopping is fragmented across aggregators and direct insurers. Same details produce different quotes across sites and across time. This project is a **lab**, not a comparison service: a place to study browser-automation, anti-bot evasion, adaptive parsing, and the ethical limits of personal-use scraping.

The maintainer ships only:

- Library primitives (fetcher wrapper, form DSL, checkpoint primitive, recorder mode, quote schema)
- A **mock insurer site** for testing
- One example adapter against the mock

Adapters targeting real aggregators are **not** shipped by the maintainer. Community contributors who run their own quotes against their own data may publish adapters as plugins. See [ADAPTERS.md](ADAPTERS.md).

## Architecture (planned)

```
src/kestrel/         core lib (fetcher wrapper, form DSL, checkpoint, recorder)
mock_site/           FastAPI fake insurer for tests and tutorials
adapters/example/    adapter against mock_site (only adapter shipped)
cli/                 Textual TUI runner
tests/               pytest, mock-only network
```

## Install (planned)

```bash
uv sync
uv run kestrel --help
```

Python 3.12+. `uv` required.

## Run mock site

```bash
uv run mock-site
uv run kestrel --adapter example
```

## Privacy default

- Quote results: in-memory only, discarded on exit
- Input profile: SQLCipher with ephemeral passphrase entered each run
- No telemetry, no error reporting, no analytics, no cloud sync
- Logs: PII-redacted, off by default
- Browser profile: disposable per run

See [PRIVACY.md](PRIVACY.md).

## Documentation

| File | Purpose |
|------|---------|
| [LEGAL.md](LEGAL.md) | CMA 1990, ToS, DMCA, scope of permitted use |
| [PRIVACY.md](PRIVACY.md) | PII model, storage policy, hardening |
| [STRATEGY.md](STRATEGY.md) | Quote variance, IP, timing, ethical limits |
| [SECURITY.md](SECURITY.md) | Threat model, vulnerability reporting |
| [CONVENTIONS.md](CONVENTIONS.md) | Commit, code, doc, review style |
| [CONTRIBUTING.md](CONTRIBUTING.md) | DCO, PR process, contributor rules |
| [ADAPTERS.md](ADAPTERS.md) | Plugin model and adapter API contract |

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE). Strong copyleft via network use. Forks running as service must release source.

## Contact

Security issues: see [SECURITY.md](SECURITY.md). Other matters: open an issue.
