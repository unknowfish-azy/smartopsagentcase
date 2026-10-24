# Model Registry

`training/model_registry.py` currently supports planned records and prevents `TRAINED` unless an artifact exists and evaluation status is `COMPLETED`.

Allowed lifecycle states include `PLANNED`, `TRAINING`, `TRAINED`, `FAILED`, `NOT_RUN` and `CANCELLED`. The repository currently has no trained artifact or registered trained model.
## Phase 5 Registry Boundary

No model may enter `TRAINED` or `DEPLOYED` in this phase. There is no artifact, completed evaluation or safety benchmark; any future model must remain `PLANNED`, `NOT_RUN` or an evidence-backed intermediate state until all gates pass.
