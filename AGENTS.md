# TagTracker project instructions

Go collector/browser dashboard with Swift helpers; local history of observations displayed by Find My. Read `README.md`, `CONTRIBUTING.md`, and relevant docs.

- `make build` requires macOS/Swift for helpers. `make test` runs Go tests and Python lifecycle/unit checks; inspect the Makefile for current commands.
- An observation reflects what Find My displayed, not a fresh GPS fix or a measured route. Preserve stale/unknown-location semantics.
- Scans interact with the visible Find My app. Preserve idle gating, interruption cleanup, screen-sharing behavior, and user-window ownership.
- A running service is not proof of complete collection. Check freshness, gaps, errors, stored observations, and the rendered UI.
- Public demos must use fictional items and public landmarks. Actual locations, item identifiers, databases, and device diagnostics stay private.

## Working rules

- Preserve unrelated changes and use the repository's existing conventions.
- Test changes through the real user flow before saying they work. State what could not be tested and why. A passing build or a saved setting is not end-to-end verification.
- Run browser tests headlessly when no visible interaction is needed. Close only the windows/tabs you opened and stop only the temporary servers you started.
- Never send email on the user's behalf without showing the complete draft and receiving approval of that exact version. Changes to the draft require renewed approval.
- Do not add AI attribution, AI co-author trailers, or session links to commits, PRs, issues, releases, or comments. Use the repository owner's configured Git identity; never invent an identity.
- Before starting a new product or tool, research existing solutions, compare their fit/cost/limitations, and wait for the user's choice. Routine fixes, additions to existing projects, and throwaway scripts do not require that step.
- Give progress updates during long work. Do not stop or restart a slow job the user is waiting on without asking.
- Keep credentials, personal identifiers, account details, private hostnames, and private notebooks out of repository instructions and public artifacts. Use fictional test data and repo-relative paths.
- Keep durable public project knowledge in this file or focused project docs. Private notes belong in the agent's configured private context store, if available; a cloud task must work from this repo without access to private files.
