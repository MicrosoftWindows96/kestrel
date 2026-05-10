# Strategy

How kestrel handles the fact that UK insurance quotes vary by IP, cookies, time of day, device, and shopping signals.

## Variance sources

- IP geography and reputation
- Cookies and returning-shopper signals
- Time of day and day of week
- Device class (desktop vs mobile)
- Browser engine
- Cross-site cookie pollination via shared adtech
- Quote frequency and recency

## Defaults

| Setting | Default | Reason |
|---------|---------|--------|
| Browser profile | Disposable per site | Kills "returning shopper" cookie tag |
| Inter-site delay | 30 minutes | Breaks adtech correlation across sites |
| Re-quote cooldown | 72 hours | Refuses re-running same details too fast |
| Headless mode | Off, always | Forces human supervision |
| Device matrix | Desktop only v1 | Mobile variant behind flag in v2 |
| Browser matrix | Firefox-derived only v1 | Chrome variant behind flag in v2 |
| Timing window | None enforced | User picks; recommendation: midweek 01:00-04:00 GMT |

## IP strategy

Recommended order:

1. Home IP. Matches your declared address geography. Looks natural. Free.
2. UK residential proxy from clean pool, matched to your county. Useful if you want IP rotation across runs.
3. Mobile network proxy. Even more natural-looking, but expensive.

Refused:

- Tor. See "Tor refused" below.
- Datacenter VPN. Often flagged.
- Shared free proxy lists. Burned IPs, fraud signals.

## Tor refused

kestrel does not support Tor as a transport for quote submission. Reasons:

- Tor exit IPs are publicly listed; insurance and financial sites flag them aggressively as fraud risk
- Geographic mismatch (e.g., exit in Romania while quoting UK address) compounds the signal
- UK insurers share fraud data via CIFAS and CUE; a "suspicious activity" tag from Tor use can persist on your record across the industry, affecting future quotes, mortgages, and credit decisions
- Tor protects identity from network observers; aggregators identify you by submitted PII, not IP, so Tor adds no privacy benefit while adding substantial risk

Pre-quote research browsing through Tor is your business. Form submission through Tor is refused at the fetcher layer.

## Timing

Empirical observation, not policy:

- Midweek pricing tends to be lower than weekends
- Late-night (01:00 to 04:00 GMT) tends to show fewer "shopping bot" filters
- Mid-month and mid-quarter tend to be quieter than month-end and quarter-end

kestrel does not auto-schedule. You pick when to run.

## Cooldown enforcement

Re-running a sweep against the same site within 72 hours is refused at the runner level. Override flag exists but requires explicit confirmation prompt and writes to a local log of override events.

Reason: fast re-quotes flag as price-shopping behavior on aggregator side, which can inflate prices on subsequent runs.

## Device and browser matrix

v2 feature. Off by default. Optional flag runs each adapter twice (desktop and mobile UA, Firefox and Chrome) and surfaces the cheapest result. Costs roughly 2x runtime.

## Ethical limits

The following are refused at the adapter level and PRs adding them will be rejected:

- Vehicle registration not yours
- Postcode not your actual address ("garaged at neighbour's" tax dodging)
- DOB shifting
- Occupation misrepresentation
- Claims history omission
- No-claims discount inflation
- Driving license details for someone else

These constitute material misrepresentation under UK insurance law and can void any policy purchased plus carry criminal exposure under fraud statutes.

kestrel exists to find the cheapest accurate quote for your real circumstances, not to manufacture cheaper ones.

## Realistic outcome

Variance handling at the strategy level typically reduces the cheapest-available premium by roughly 5 to 15 percent relative to a single sweep with default browser settings. Not magic. Not guaranteed. Sometimes zero.
