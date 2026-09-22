# changelog.d — per-PR changelog fragments

One file per PR, written by a human, **customer-facing**. At release-cut time
`otaman-deploy`'s assembler collects the accumulated fragments from every
bundled repo (this one included) and renders the release notes from them —
nothing else (not commit messages, not PR bodies, not source strings) reaches
the notes. See `release-notes-sibling-coverage`.

**Filename:** `<pr>.<category>.md` (e.g. `41.feature.md`)
**Categories:** `feature` · `fix` · `doc` · `removal` · `misc`

Write the line for someone running Otaman, not for the reviewer:

    Skill registration now reports the harness it targeted in every result.

To skip a PR that ships nothing customer-facing, put `changelog: exempt` in the
PR body. CI blocks a shipped-code PR that has neither a fragment nor the marker.

The convention (directory, filename, categories, exemption marker) lives in
otaman-core's git policy (`GIT_STANDARD_RULES["changelog_fragment"]`) and is
evaluated by `otaman_core.changelog_fragment` — the same module the CI gate
runs (`python -m otaman_core.changelog_fragment --check`). This file just
explains the convention, and is itself never a fragment.

**Clearing:** fragments are cleared by THIS repo's owner after the cut that
consumes them (on the `fragments-consumed` signal), by exact filename from the
release manifest (`otaman release clear-fragments <manifest>`) — this README
always survives.
