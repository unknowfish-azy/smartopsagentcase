# Data Quality Gate

```text
Generator
→ Schema Validation
→ Rule Validation
→ Safety Validation
→ Knowledge / Version Validation
→ Deduplication
→ Grouped Split
→ Leakage Check
→ Human Sampling
→ READY Dataset
```

Implemented checks include:

- required common envelope and task-specific output fields;
- evidence relevance/trust range and unique evidence IDs;
- HIGH/CRITICAL risk requiring approval;
- REAL/SYNTHETIC/DEMO and source-type consistency;
- duplicate samples, unsafe markers and invalid evidence labels;
- pending human review status.

Current result: validation executed on all seven directories, zero samples found, all manifests `DRAFT`, aggregate quality report `NOT RUN`.
## Phase 4 Gate Status

Knowledge and training tests now execute, but no sample has been promoted. Current approved count is `0`; tests passing does not promote data or imply a quality score.

Phase 5 adds an explicit candidate lifecycle and Human Review gate. No candidate records were created in this run; approved count remains `0`.

Phase 7 recheck created no candidates and performed no promotion; quality remains `NOT RUN`.
