# SmartOps Companion Phase 1

## Delivered flow

External `smartops:fault-detected` event → MainLayout-owned bridge → validated Companion ingestion → existing InvestigationContext → ambient Spider cue → explicit user click → inquiry → answer events → local knowledge references → source-linked recommendations.

The investigation store remains the single owner of inquiry data. Companion snapshots clone plain JSON through Vue proxies, freeze the result, and always expose `executionAllowed: false`. Each Pinia instance owns its event bus; the shell removes its browser listeners when unmounted. Events are bounded to 200; previous investigations are retained in memory, up to 50. These are session records, not durable incident memory.

## Attention and capability status

Open COMPANION in the top bar to select NORMAL, FOCUS or QUIET. NORMAL allows an ambient cue; FOCUS limits cues to high/critical severity; QUIET limits them to critical severity. No mode automatically opens the investigation drawer. An explicit user request can always open it.

Model, capture/OCR and telemetry capabilities initially display offline/unconnected. Local knowledge is available without a network or model. Whale environment health remains UNKNOWN. Route changes no longer pretend that reasoning or telemetry has run.

The browser event is a compatibility input, not a real screen detector. Native desktop hosting, capture, OCR, AI reasoning, infrastructure probes, remote commands and durable incident memory remain future phases.

## Verification

- `npm test`: 80 tests passed.
- `node test/companion-browser.mjs`: desktop 1440px and mobile 375px passed; checks ambient notification, explicit inquiry opening, answer advancement, knowledge attachment, close/reopen retention, viewport bounds and page errors.
- `npm run build`: passed; existing large-chunk warning remains.
- `npm run lint` and `npm run typecheck`: exit 0, but the repository currently maps both to syntax checking `whaleQuality.js`; these are not full-project lint or TypeScript checks.
- `git diff --check`: passed.

Run the browser check against `npm run dev -- --host 127.0.0.1 --port 5189 --strictPort`. Override the full page URL with `COMPANION_BASE_URL` if needed. The test uses installed Microsoft Edge and injects a clearly synthetic fault fixture.

## Implementation decisions

Domain helpers stay independent of Vue; Pinia derives its context from the existing investigation store. This avoids two conflicting investigation owners, at the cost of retaining an adapter layer.

The subagent workflow did not produce a usable final independent review. Implementation was completed and reviewed locally, then validated with domain and browser tests. Do not treat earlier ledger claims of independent approval as final acceptance evidence.
