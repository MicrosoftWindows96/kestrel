# Security

## Reporting

For vulnerabilities affecting kestrel itself (the library, mock site, or example adapter):

- Email: spam@zagrosi.com
- Optionally encrypt with a public key (link to be added)
- Expect acknowledgment within 7 days
- Disclosure window: 90 days from acknowledgment, sooner if a fix lands earlier

For vulnerabilities in third-party adapters:

- Report to the adapter maintainer first
- Cc the project if no response within 14 days

## Scope

In scope:

- Code execution from a malicious adapter
- Path traversal or arbitrary file write
- Profile decryption without correct passphrase
- Memory disclosure of profile or quotes
- TLS validation bypass
- Logger leaks of unredacted PII

Out of scope:

- Vulnerabilities in upstream dependencies (report to upstream)
- Vulnerabilities in aggregator sites (not our system)
- Vulnerabilities exploitable only with local code execution as the user

## Threat model

The user is trusted. The user's machine is trusted up to the bounds described in [PRIVACY.md](PRIVACY.md). Adapters are partially trusted; the runner enforces sandbox boundaries.

| Adversary | Capability |
|-----------|------------|
| Attacker with file access to the laptop | Can read disk; should fail to recover profile or quotes |
| Attacker on the network | Should fail to intercept submissions (TLS only) |
| Malicious adapter | Should fail to escape adapter sandbox to read other adapters' state, profile, or quote outputs from other runs |
| Compromised dependency | Detected via lockfile and signed-commit policy; not preventable |

## Supply chain

- Dependencies pinned in `uv.lock`; commits to `pyproject.toml` and `uv.lock` reviewed together
- All maintainer commits SSH-signed; unsigned commits on `main` rejected
- Pre-commit hooks: secret scanning (`gitleaks`), lint, type-check, test
- CI re-runs all hooks; no merge without green CI
- No fetched deps installed outside `uv sync --frozen`

## Adapter sandboxing

Adapters run in a separate process with restricted permissions. The adapter API receives:

- Profile data through a typed interface, not raw access
- Browser session through a controlled handle
- Quote return channel only

Adapters cannot:

- Read other adapters' state or quotes
- Write outside their own scratch directory
- Spawn subprocesses
- Access network outside the URLs declared in their manifest

Sandbox enforcement is best-effort, not airtight; review adapter source before running.

## Local file permissions

- Profile DB: `0600` (owner read/write only)
- Logs: `0600`
- Temp browser profiles: `0700` directories, `0600` files

Enforced by code at write time. CI test verifies on Linux and macOS.

## What kestrel does not do

- No auto-update from the network
- No remote configuration
- No telemetry, error reporting, or analytics
- No outbound connections to any host not declared by an adapter manifest
