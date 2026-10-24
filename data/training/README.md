# Training data workspace

This additive directory contains validated training assets. The existing `date/` directory is retained unchanged for compatibility.

Only samples that pass schema, duplicate, empty-field, unsafe-sample and label validation may be promoted for training. Empty subdirectories contain `.gitkeep` placeholders and do not represent completed datasets or training runs.

The versioned source schemas live in `training/schemas/` and are loaded through `training.schema_registry`. Schema version `1.0.0` defines the common Task -> Environment -> Knowledge -> Evidence -> Decision -> Tool -> Risk -> Approval -> Execution -> Verification -> Inspector envelope.

No sample in this directory is considered trainable merely because it is valid JSON. Promotion requires the later quality-gate phases, a dataset manifest, leakage review and human sampling. `REAL`, `SYNTHETIC` and `DEMO` classifications must remain separate.
