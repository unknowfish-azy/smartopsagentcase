# Server demo and theme parity

**Goal:** Add six isolated fictional server examples and align light/dark text and effects across balanced/lightweight visual modes.

**Approved design:** User confirmed a real/demo list switch, searchable demo rows and local demo details without persistence or remote actions. Their additional requirement makes light surfaces use dark text and dark effects, and dark surfaces use light text/effects. Filled controls retain contrasting foregrounds rather than blindly inverting every pixel.

**Constraints:** No database, credentials, backend APIs, SSH execution or production data changes. Preserve current dirty workspace. Keep Three.js async/home-only and do not raise bundle thresholds. No new dependencies.

- [x] Add failing demo fixture/isolation tests; integrate view switch, independent statistics and local details, with mutation guards.
- [x] Add failing palette/contrast tests; map Element Plus tokens and shared effect tokens to both themes, fix conflicting button states.
- [x] Connect Three.js, Canvas, meteor and jellyfish effects to the shared palette without remounting or losing reduced-motion behavior.
- [x] Verify real/demo/error separation, live theme changes, balanced/lightweight/reduced-motion and 375/1440px layouts; run unit/build regression and document limits.
- [x] Follow-up: fix the Agent refresh button's white-on-white state and verify loading/error recovery.
- [x] Follow-up: correct the sidebar/topbar glass frame geometry and mobile menu width; verify 375/900/1440px layouts.

Acceptance evidence and boundaries: `docs/server-demo-theme-acceptance.md`.
