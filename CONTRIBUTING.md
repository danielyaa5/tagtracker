# Contributing

Open an issue describing the macOS version, expected behavior, and observed behavior. Remove item names, locations, account details, screenshots, and credentials from reports and fixtures.

Run `make build` and `make test` on macOS. Use synthetic records for UI and parsing tests. Changes to collection or cleanup should also be verified against the real Find My interface on your own Mac, including user activity, Screen Sharing, missing permissions, and failed text recognition. State clearly which checks were not performed.

Keep data under Application Support and bind the dashboard to loopback. Preserve upstream and third-party license notices. Do not commit generated binaries, signing identities, user configuration, histories, logs, or diagnostic captures.
