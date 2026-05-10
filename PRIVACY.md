# Privacy

kestrel handles personal data: date of birth, address, postcode, vehicle registration, email, phone, and sometimes National Insurance number. This document is the design contract for how that data is held, transmitted, and discarded.

## Threat model

Adversaries we design against, in priority order:

1. Lost or stolen laptop with disk recoverable
2. Backup leak (Time Machine, cloud sync, third-party backup tools)
3. Malware running as the user
4. Forensic recovery from swap or temp files
5. Network observers (ISP, public WiFi)
6. The aggregator itself, beyond what users explicitly submit

Out of scope:

- Nation-state adversaries with hardware access while running
- Malware running as root
- Compromised Python interpreter

## Data taxonomy

| Class | Examples | Storage policy |
|-------|----------|----------------|
| Profile (input) | DOB, address, postcode, registration, occupation | SQLCipher with ephemeral passphrase |
| Quote (output) | premium, insurer, policy details | In-memory only, discarded on exit |
| Browser state | cookies, cache, profile | Disposable per run, deleted after |
| Telemetry | usage stats, errors | None. Never collected. |
| Logs | activity, debug | PII-redacted, opt-in only |

## Profile storage

The profile encapsulates the data you fill into quote forms. It is encrypted at rest with SQLCipher.

- Key: derived from a passphrase you enter at the start of each run
- Key never written to disk, keychain, or any other persistence
- File: `~/.local/share/kestrel/profile.sqlite` with mode `0600`
- Schema version tracked; migrations supported

If you forget the passphrase, the profile is unrecoverable. By design.

## Quote handling

Quote results live only in memory:

- Returned by adapters as `Quote` dataclasses
- Displayed in the runner output
- Sorted, compared, presented
- Process exit clears them
- Not persisted by default

Optional `--save` flag exports a single run to a SQLCipher file the user names and places themselves. Off by default.

## Memory hardening

- `mlock()` on pages holding profile and quote data where the OS supports it (Linux and macOS)
- Sensitive dataclasses zero-fill in `__del__` and on exit handlers
- `__repr__` on profile and quote types returns `<redacted>` to prevent accidental log output

## Logging

- Default: errors only, no PII
- Logger redacts known PII fields by name (DOB, postcode, registration, address, email, phone) before write
- File logging opt-in via `--log-file PATH`
- Log files gitignored, rotated, capped at 10 MB total
- No remote log shipping ever

## Browser profile

- Disposable directory per run under `$TMPDIR/kestrel-<random>`
- Removed via `shutil.rmtree` after run regardless of success or failure
- Cookies, cache, local storage all live and die with the run
- No persistent profile, no shared profile

## Network

- Outbound only to URLs explicitly named by adapter manifests
- No telemetry endpoints
- No error reporting service
- No analytics
- No cloud sync
- No "anonymous usage stats"

## What we refuse to ship

- "Save quote history" feature (use opt-in `--save` instead)
- Cloud sync of any kind
- Sharing features ("send to friend", etc.)
- Crash reporters that phone home
- Anonymous usage telemetry
- "Cloud profile" storage

If you want history, run `--save` and manage the encrypted file yourself.

## Reporting privacy issues

See [SECURITY.md](SECURITY.md).
