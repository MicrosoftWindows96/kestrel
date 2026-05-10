# Adapters

Adapters are plugins that teach kestrel how to interact with a specific quote source. Each adapter encodes the form fields, multi-step navigation, and result extraction for one site.

## Distribution model

The kestrel repo ships:

- The adapter API and base class
- One example adapter targeting the mock insurer site

The kestrel repo does **not** ship adapters targeting real aggregators or insurers. Those live as community-maintained plugins. Reasons in [LEGAL.md](LEGAL.md).

A community adapter can be:

- A separate repository on GitHub or elsewhere
- A Python package on PyPI named `kestrel-adapter-<site>`
- A local package the user develops privately

kestrel loads adapters via Python entry points in the `kestrel.adapters` group.

## Adapter API contract (planned)

```python
from kestrel.adapter import Adapter, AdapterManifest, Profile, Quote, AdapterContext

class ExampleAdapter(Adapter):
    manifest = AdapterManifest(
        name="example",
        version="0.1.0",
        target_hosts=["localhost"],
        legal_notice="Adapter targets the kestrel mock_site for testing.",
        author="kestrel-maintainers",
    )

    async def fetch_quote(self, profile: Profile, ctx: AdapterContext) -> Quote:
        page = await ctx.fetcher.open(self.manifest.target_hosts[0])
        await ctx.form.fill_step("driver-details", profile.as_form_dict())
        await ctx.checkpoint("captcha", reason="captcha solve required")
        await ctx.form.submit()
        return ctx.parser.extract_quote(page)
```

Methods:

- `fetch_quote(profile, ctx) -> Quote`: required, async, returns one `Quote`
- `validate_profile(profile) -> list[str]`: optional, returns missing or invalid fields
- `cleanup(ctx) -> None`: optional, called after fetch regardless of outcome

`AdapterContext` provides:

- `fetcher`: stealth browser session
- `form`: form-filling DSL
- `checkpoint(label, reason)`: pause for human input
- `parser`: result extractor primitives
- `tmp_dir`: scratch directory, auto-cleaned

## Manifest fields

| Field | Required | Purpose |
|-------|----------|---------|
| `name` | yes | Unique identifier; lowercase letters, digits, hyphens |
| `version` | yes | SemVer |
| `target_hosts` | yes | Allowlist of hostnames the adapter is permitted to contact |
| `legal_notice` | yes | Adapter author's statement on legal posture |
| `author` | yes | Maintainer of the adapter |
| `data_flow` | recommended | Markdown describing fields submitted and where they go |
| `tos_url` | recommended | Link to target site's Terms of Service the adapter author has reviewed |

Hosts not in `target_hosts` are blocked at the fetcher layer. The user sees a refusal error if an adapter attempts to escape its host allowlist.

## Adapter responsibilities

Adapter authors must:

- Read and accept the target site's Terms of Service before publishing
- Document the data flow honestly: every field submitted, every cookie set, every outbound URL
- Refuse to encode misrepresentation features (see [STRATEGY.md](STRATEGY.md))
- Maintain the adapter as the target site changes; abandoned adapters get deprecated and removed from registries
- Ship tests against `mock_site` patterns, not against the live target

Adapter authors must not:

- Embed personal data in the adapter source
- Embed the maintainer's credentials in the adapter source
- Add code that phones home to any address other than `target_hosts`
- Use telemetry, analytics, or error-reporting services

## Discovering adapters

```bash
uv run kestrel adapters list
```

Shows installed adapters, their manifests, and version status.

## Trust and review

Adapters are partially trusted code that runs in your browser session. Before installing or running an adapter:

1. Read its source
2. Verify the `target_hosts` matches your expectation
3. Verify the data flow documentation against the actual code
4. Verify it passes its own tests against `mock_site`
5. Verify the project signs its commits (where applicable)

The kestrel maintainer does not vet community adapters. There is no "official" adapter registry. Trust is on you.

## Lifecycle

A community adapter typically follows:

1. Proposal: open issue or RFC describing the target and intent
2. First version: tests pass against mock site patterns; manifest complete
3. Active: maintained against target site changes
4. Deprecated: maintainer announces sunset; users warned at runtime
5. Removed: deleted from any opt-in registry

## Reference: example adapter

`adapters/example/` in this repo is the canonical reference. It targets the mock site only and exercises every part of the adapter API. Use it as a starting template.
