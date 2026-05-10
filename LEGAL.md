# Legal

This is not legal advice. Consult a solicitor for anything serious.

## Purpose

kestrel is a research project for studying browser automation, anti-bot evasion, and adaptive parsing in the specific context of personal-use UK car insurance quote shopping. It is not a product. It is not a service. It is not a comparison engine.

## Scope of permitted use

- Run kestrel locally against your own machine and your own browser with your own data
- Use it to fetch quotes for vehicles you own or are insuring
- Study the codebase and contribute improvements
- Fork it under AGPL-3.0 terms

## Scope of refused use

- Commercial scraping operations
- Hosted comparison services using kestrel as backend
- Scraping at scale beyond personal renewal cadence
- Misrepresenting personal details to obtain cheaper quotes (see STRATEGY.md ethical limits)
- Use against any site whose Terms of Service you have not personally read and accepted

## United Kingdom

The Computer Misuse Act 1990 (as amended) governs unauthorized access to computer systems in England, Wales, Scotland, and Northern Ireland. Section 1 concerns unauthorized access; Section 3 concerns unauthorized acts impairing operation. Aggressive scraping that circumvents anti-bot protections may, in some interpretations, fall within scope.

The General Data Protection Regulation (UK GDPR) and Data Protection Act 2018 govern handling of personal data. kestrel processes only your own personal data on your own machine; this is generally outside scope of the regulatory regime, but exporting or sharing the data brings you in scope.

The Consumer Rights Act 2015 and unfair terms doctrine sometimes limit the enforceability of overly broad scraping prohibitions in consumer-facing Terms of Service, but this is jurisdiction-specific and case-specific. Do not rely on it.

## Terms of Service

Each aggregator and insurer has their own Terms of Service. Many forbid automated access. Some forbid it absolutely, some only at scale, some carve out personal-use exceptions. You are responsible for reading and complying with the Terms of any site you point kestrel at.

The maintainer of kestrel does not waive any aggregator's Terms on your behalf. Using kestrel does not exempt you from those Terms.

## Maintainer position on adapters

The maintainer publishes only:

- The library and primitives
- A mock insurer site
- An example adapter against the mock

The maintainer does not publish working selectors targeting any real aggregator or insurer. Community contributors who choose to do so accept responsibility for their own contributions, including alignment with the target site's Terms.

This split distributes legal exposure: the library is generic browser automation tooling, comparable to Selenium or Playwright; site-specific adapters are user-contributed and user-maintained.

## DMCA and takedown

If you believe kestrel or one of its adapters infringes your rights or violates the Terms of a service you operate, please:

1. Open a public issue describing the concern
2. Or email the maintainer (see SECURITY.md)
3. We respond within 7 days

We will remove infringing content. We will not remove the project as a whole on the basis of a hosted-service Terms violation, since the project is a library and tutorial, not a service operator.

## Why AGPL-3.0

- Strong copyleft via network-use clause prevents closed-source forks running as a service
- Forces transparency on any commercial derivative
- Reduces incentive to build a hosted scraping product on top of kestrel
- Signals research and educational orientation to industry watchers and regulators

A more permissive license (MIT, Apache 2.0) would invite commercial forks that would carry kestrel's name into use cases the maintainer does not endorse. AGPL-3.0 makes that path uncomfortable.

## Disclaimer

The maintainer assumes no responsibility for how you use this software. You are responsible for:

- Reading and complying with the Terms of any site you target
- Filing accurate quotes (no misrepresentation)
- Securing your local machine and your data
- Whatever consequences arise from your use

If unsure, do not run kestrel against a site. Use the mock instead.
