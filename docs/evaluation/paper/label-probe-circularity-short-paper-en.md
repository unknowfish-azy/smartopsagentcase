# Label–Probe Circularity in Synthetic Benchmarks: A Validity Trap for False-Success Detection in AIOps Agents, and a Repair Protocol

> **Status**: short paper draft v1 (2026-11-21), ~7.5 pages, 4 figures.
> **Reproducibility**: all numbers derive from `SmartOps-Dataset/Controlled/v1/samples.jsonl`
> (sha256[:16] `2c87fb6e5164b2d6`) via three scripts listed in §7; regression protection in
> `tests/scripts/test_validity_audits.py` (11 passed).
> **Scope discipline**: no real-world accuracy is claimed anywhere; the contribution is a
> *diagnostic of this construction pattern*, not a claim about all synthetic benchmarks.

---

## Abstract

Synthetic controlled sets are standard infrastructure for agent evaluation, yet their validity is
rarely audited. We report a structural failure mode — **label–probe circularity**: when labels are
built from the verifier probe's expected assertions while the evaluated component reads the same
probe, every classification metric degenerates into a single-bit readout of probe health. We
formalize the condition and demonstrate it on a 144-sample controlled set: on the primary binary
denominator (n=72), the trivial rule "unhealthy ⇒ FALSE_SUCCESS" reproduces the pipeline at
**72/72**, the flipped-probe intervention scores **0/72**, and the contingency table is perfectly
diagonal (Fisher one-sided p ≈ 9.1e-13). A variant-based wording holdout proves infeasible (13
overlapping claims, 644 shared fragments), and independent information units number **24**, not
144 — accuracy is invariant across 200 re-splits. We give a repair protocol and a precision–cost
model (±0.05 at DEFF=2 needs 769 units ≈ 44.22 person-hours), turning an informal risk into an
automatic pre-submission gate.

**Keywords**: evaluation validity; synthetic datasets; false-success detection; AIOps agents;
benchmark auditing

---

## 1 Introduction

### 1.1 Motivation

*False success* is a characteristic failure of operations agents: the system has not recovered, but
the agent asserts that it has. Detecting it requires labeled samples, and real production incidents
rarely come with usable labels — so much of the field moves to **synthetic controlled sets**, where
a generator emits `(claim, state probes, ground-truth label)` triples.

Such datasets have a hidden convenience: labels can be made very "clean", because the label is a
transcription of the probe expectation. This paper argues that precisely this convenience makes the
metrics meaningless.

### 1.2 Core claim

> If the ground-truth label is a function of the probe expectation, and the prediction is a
> function of probe health, then the metric measures *whether two functions read the same input* —
> not whether the model understands the semantics of the claim.

We call this **label–probe circularity**. It requires neither data fabrication nor a weak model:
even a verifier that ignores the claim text entirely, reading only probe health, scores perfectly.

### 1.3 Contributions

| # | Contribution | Evidence |
|---|---|---|
| C1 | Formal criterion and executable detector for circularity: single-bit separability, reversed-polarity control, Fisher association strength; exits non-zero when circularity holds, usable as a CI gate | `EXP-CIRC-001`, `tests/scripts/test_validity_audits.py` (11 passed) |
| C2 | Wording-independence audit: template-reuse structure metrics + wording isolation check (exact overlap strings, shared-fragment counts), plus proof of vocabulary co-origin | `EXP-WORDING-001` |
| C3 | Information-unit accounting and repair cost model: independent units = number of label families; precision-to-person-hour conversion with design-effect sensitivity | `EXP-CEIL-001` |

### 1.4 Relation to existing notions of leakage

Label leakage usually means train/test information sharing; here both label and prediction come from
**the same samples**, sharing a **construction variable**. Consequently neither deduplication nor
grouped splitting detects it — grouped splitting actually intensifies it, since each group carries a
single unique label, making within-group outcomes perfectly homogeneous (ICC point estimate 1.0000).
This is a **construction-level** problem.

---

## 2 Formalizing the failure mode

### 2.1 Notation

- Sample $s_i$ contains a claim string $c_i$, a probe set $P_i$, and a ground-truth label
  $y_i \in \mathcal{Y}$.
- The normalization layer outputs **probe health** $h_i = H(P_i) \in \{0,1\}$.
- The evaluated verifier outputs $\hat y_i = V(c_i, P_i)$.

### 2.2 Conditions

**Definition (single-bit separability).** If the map $h \mapsto \{y : \exists i, h_i = h\}$ has a
singleton preimage at every value, the label is *single-bit determined* by probe health; write
$\mathrm{SBS}(\mathcal{D}) = \text{True}$.

**Proposition (trivial-rule optimality).** If $\mathrm{SBS}$ holds on the subset used for scoring,
then the trivial rule $r(h) =$ the unique label at $h$ attains accuracy 1.0 on that subset,
**independently of the verifier implementation**.

**Definition (trivial-rule reproduction).**
$\mathrm{TR}(r) = \frac{1}{n}\sum_i \mathbb{1}[\hat y_i = r(h_i)]$.
If $\mathrm{TR} = 1$ while $\mathrm{TR}(r^\text{rev}) = 0$ for the reversed-polarity rule
$r^\text{rev}(h) = r(1-h)$, the verifier is equivalent to a probe readout.

### 2.3 Two statistics, not one: predictability vs. dependence

Benchmark auditing has converged on the observation that *predictability* and *dependence* are
different questions (arXiv:2605.23701). A metadata-only shortcut check asks whether outputs are
predictable from priors; an evidence-intervention check asks whether the protocol actually depends on
the supplied evidence. Their counterexample is instructive: a constructed dataset with moderate
metadata predictability yet **zero** evidence sensitivity. Auditing only the first axis would clear
it.

We therefore report two statistics, and require both to fire:

| Axis | Statistic here | Question it answers |
|---|---|---|
| Predictability | $\mathrm{SBS}(\mathcal{D})$, single-bit separability (§2.2) | Can the label be recovered from probe health alone? |
| Dependence (intervention) | $\mathrm{TR}(r)$ vs. $\mathrm{TR}(r^\text{rev})$ under the flipped-polarity intervention $h \mapsto 1-h$ | Does the verifier's output actually track the probe bit, rather than coinciding with it? |

The second statistic is deliberately an *intervention*, not a correlation: flipping the probe bit
while holding everything else fixed should collapse accuracy if the probe is genuinely load-bearing,
and leave it untouched if the score is carried by some other cue. Our intervention is deliberately
minimal — a single-bit flip, not a general cross-item evidence shuffle — and we flag that limitation
in §6.4.

### 2.4 Why routine checks miss it

- **Leakage checkers** test key duplication and near-duplication, not construction dependencies;
  this dataset passes all six key classes (0 hits).
- **Grouped splitting** keeps a group inside one split — which, because each group has a unique
  label, makes the circularity hold *simultaneously inside every split*.
- **Power analysis** computes intervals from nominal sample size and cannot see that one bit was
  read six times.

---

## 3 Empirical study: auditing one controlled set

### 3.1 Dataset and evaluated object

`SmartOps-Dataset/Controlled/v1`: 144 controlled verification samples = 6 fault families × 4
root-cause groups × 6 variants. Four-way labels: `FALSE_SUCCESS` 48 / `SUCCESS` 36 /
`FAILED` 30 / `UNKNOWN` 30. Every sample carries `ground_truth.label` and non-empty
`state_assertions`. All samples are `review_status=unreviewed`, `human_review=PENDING` — this is
**not** a reviewed golden set.

The evaluated object is the deterministic `InspectorPipeline` (Rule + Evidence + AI-degraded +
StateVerifier), with **no LLM** (`is_llm=false`). This matters: circularity also holds for a
deterministic verifier, so the issue is orthogonal to the model component.

The generator states the label provenance itself (`LABEL_CONTRACT`):

> "synthetic fixture: labels are derived directly from probe assertions, not real operational observations"

Hence our characterization: **not data fabrication, but the misuse of a metric as capability
evidence**.

### 3.2 EXP-CIRC-001: detecting circularity

**Contingency table (all 144 samples):**

| Label | probe unhealthy | probe healthy | total |
|---|---|---|---|
| SUCCESS | 0 | 36 | 36 |
| FALSE_SUCCESS | 48 | 0 | 48 |
| FAILED | 30 | 0 | 30 |
| UNKNOWN | 30 | 0 | 30 |

Perfectly diagonal. One-sided Fisher exact test on
`probe_healthy × (SUCCESS / not-SUCCESS)`: $p = 9.075\times10^{-13}$.

**Two readings must be reported separately:**

- full-set reading: `SBS_all = False` (unhealthy maps to three labels);
- **primary-binary-subset reading** (keeping only `SUCCESS`/`FALSE_SUCCESS`): `SBS_bin = True`.

Only the latter is the actual denominator of P/R/F1 (n=72). Reporting only the full-set reading
yields the misleading conclusion "not single-bit separable".

**Per-split replication:**

| split | binary n | trivial rule correct | reversed correct | coverage | out-of-taxonomy | denies_success |
|---|---|---|---|---|---|---|
| train | 28 | 28 | 0 | 58.33% | 0 | 20 |
| validation | 22 | 22 | 0 | 45.83% | 4 | 22 |
| test | 22 | 22 | 0 | 45.83% | 0 | 26 |

Reversed polarity is 0 everywhere, ruling out directional coincidence. On all n=72 the trivial
rule reaches **72/72**, reversed **0/72**.

**Coverage gap in the primary metric:** only 72 of 144 samples (50.00%) enter the denominator;
68 samples with `claim=denies_success` never enter it, and 4 out-of-taxonomy samples are disclosed
separately. That is, **the primary metric is computed only on the subset the verifier is guaranteed
to answer correctly**.

### 3.3 EXP-WORDING-001: wording independence is infeasible

- Each of the 24 groups contains only **2 scenarios × 3 templates**; unique claim strings per group
  range over 3–6 (distribution {3:1, 4:2, 5:6, 6:15}); mean cross-scenario template reuse rate
  13.33% (`ssh-bastion` reaches 100%).
- After a variant-based split (first 3 samples of each group to held): 72 unique claims per side,
  **13 exact overlaps**, **644 shared fragments of length ≥ 8** →
  `wording_holdout_feasible = false`.
- **Vocabulary co-origin:** the assertion vocabulary in `state_verifier.py` documents its own origin
  as "line-by-line analysis of the 144 controlled claims" and lists the corresponding `CV-*`
  identifiers. Vocabulary and evaluation set share a source.
- Group-paired consistency (unit = `root_cause_group`, n=24): both sides fully correct in 12 groups,
  agreement 0.50; single-side-only correctness in 0 groups.

**Interpretation:** the overlap is not a badly designed split but a consequence of the construction
(3 templates × 2 scenarios fill 6 variants, so short templates must repeat across scenarios). Metrics
on this set therefore establish only *within-template stability under paraphrase*, not wording
generalization.

### 3.4 EXP-CEIL-001: information ceiling and cost

**Independent information units.** Because the label is constant within a group, adding variants does
not add information.

| Label | independent groups | samples |
|---|---|---|
| SUCCESS | 6 | 36 |
| FALSE_SUCCESS | 8 | 48 |
| FAILED | 5 | 30 |
| UNKNOWN | 5 | 30 |
| **Total** | **24** | **144** |

Any "n=144" or "n=48" account overstates information by 6× and 2× respectively.

**Split stability.** Across 200 random half-group re-splits, primary-metric accuracy stays at 1.0000
(min/p50/max all 1.0) and the trivial-rule reproduction rate likewise stays at 1.0, while the number
of effective units varies with the split (scorable n p50 = 36). **An accuracy insensitive to sample
size is the signature of an invalid metric**; the absence of variance is not robustness but a direct
consequence of reading a single bit.

**Precision–cost conversion** ($n = z^2 p(1-p)/E^2 \cdot \mathrm{DEFF}$; assumptions in the note
below the table):

| Target margin | DEFF | nominal independent units needed | gap | person-hours |
|---|---|---|---|---|
| ±0.10 | 1.0 | 97 | 73 | 5.58 |
| ±0.10 | 2.0 | 193 | 169 | 11.10 |
| ±0.05 | 1.0 | 385 | 361 | 22.14 |
| ±0.05 | 2.0 | 769 | 745 | 44.22 |

> Assumptions: 90 s per label, 2 independent annotators, 15% arbitration rate, 180 s per arbitration.
> **Engineering estimates, not literature values**; unit time must be recalibrated by a pilot run.
> For reference, even with all-correct outcomes the Wilson 95% lower bound is only 0.862 at n=24,
> 0.9493 at n=72, 0.974 at n=144 — interval width is governed by effective units, not row count.

### 3.5 The causal chain

```text
Construction:  label derived directly from probe expectations (LABEL_CONTRACT)
        ↓
Evaluation:    primary metric computed only on SUCCESS/FALSE_SUCCESS → label = f(probe_health)
        ↓
Result:        a trivial rule reading one bit yields 1.0000; more samples / other seeds / other
               splits do not change it
        ↓
Side effects:  vocabulary drawn from the same 144 claims; the 6 variants are 6 restatements of the
               same information
```

---

## 4 Repair protocol

### 4.1 Three necessary conditions

1. **Adversarial units.** There must exist samples with "probe healthy but label ≠ `SUCCESS`" and
   "probe unhealthy but label = `SUCCESS`", so the trivial rule no longer succeeds. Otherwise no
   metric can distinguish semantic judgment from probe reading.
2. **Independent label provenance.** Labels must arise from independent observation or human
   adjudication, never by inverting `state_assertions[*].expected`.
3. **Wording isolation.** Introduce human-authored phrasings (≥ 2 annotators writing assertions
   against the same probes), or regenerate from an independent template pool; and run a wording
   isolation check (exact overlap + shared fragments) before submission.

### 4.2 Gate-ification

Wire the C1 detector into CI: non-zero exit on circularity aborts the build. We have done so, with
regression tests asserting that circularity *is* detected (preventing the detector itself from
degrading).

### 4.3 Required reporting after repair

A repaired dataset must report: the adversarial-unit fraction, the independent label provenance, the
wording-isolation result, and **two control baselines** — (a) the trivial probe-only rule and (b) a
claims-wording-only rule that ignores probes — demonstrating that the real verifier beats both.
Our current project lacks (b).

---

## 5 Figures

| Fig. | Content | Source |
|---|---|---|
| 1 | Label × probe-health heatmap (perfectly diagonal) | `reports/label-probe-circularity.json` |
| 2 | Per-split trivial rule vs reversed-polarity bars | idem |
| 3 | Two-panel: metric accuracy (flat line) vs effective-unit count (distribution) over 200 re-splits | `reports/dataset-ceiling.json` |
| 4 | Precision–cost curves (DEFF=1/2) with Wilson all-correct lower bounds | idem |

> Figure 3 is the most persuasive in the paper: it converts "metric insensitive to sample size"
> from an assertion into a visible fact.

---

## 6 Limitations and prohibited claims

1. **No over-generalization.** The scope is a diagnostic of *this construction pattern* (labels
   derived from verifier inputs); it must not be written as "all synthetic benchmarks are invalid".
2. **No performance claims.** Everything here is synthetic fixtures, `approved=False`, and a
   deterministic (non-LLM) verifier; no real-world accuracy may appear.
3. **Cost conversion is an order-of-magnitude judgment**, not a schedule commitment.
4. **The circularity audit has limits.** It detects a *sufficient* condition (single-bit separability),
   not subtler partial leakage (e.g., a label depending on a nonlinear combination of probes). It is
   therefore a *necessary check*, not a sufficient certification. The dependence statistic is likewise
   narrow: our intervention flips one bit ($h \mapsto 1-h$), whereas a general evidence-dependence
   audit permutes evidence across items while holding queries and labels fixed (arXiv:2605.23701).
   A verifier could in principle pass our two-bit test while remaining insensitive to richer evidence
   structure; generalising the intervention is left to future work.
5. This report does **not** modify any existing metric; it adds validity evidence only.

---

## 7 Reproducibility

```bash
# C1 circularity audit (exits non-zero when circularity holds; usable as a gate)
python scripts/audit_label_probe_circularity.py --write
# C2 wording independence audit
python scripts/build_wording_holdout.py --write
# C3 information ceiling and cost
python scripts/audit_dataset_ceiling.py --write
# Regression gate (11 tests, including protection against detector degradation)
python -m pytest tests/scripts/test_validity_audits.py -q
```

Machine artifacts: `reports/{label-probe-circularity,wording-holdout,dataset-ceiling}.{json,md}`.
Source fingerprint: `sha256[:16] = 2c87fb6e5164b2d6`.

---

## 8 Related work

Full bibliographic records and verification status are in `references.md`; entries marked there
with ✅ were checked against the original page/identifier during this search.

### 8.1 AIOps/SRE agent benchmarks

AIOpsLab (Shetty et al., SoCC'24; Chen et al., arXiv) supplies a live Kubernetes "gym" with fault
and workload generators, an agent–cloud interface, and predefined task metrics. ITBench (Jha et
al., ICML 2025, oral) provides Kubernetes-based SRE/CISO/FinOps scenarios with a managed
leaderboard; ITBench-AA later reported 59 SRE tasks on which every evaluated frontier model scored
below 50%. Cloud-OpsBench (Wang et al., arXiv:2603.00468) replays 754 runtime-verified fault
snapshots and reports a striking **outcome–process gap**: Joint RCA Accuracy up to 0.78 while
Evidence Closure Rate is only 0.38.

These benchmarks derive labels from **environment end-states** (did the injected fault clear?),
not from the verifier's expected assertions, so they are not subject to the circularity of §2. We
cite them for two reasons. First, they delimit our scope: circularity is a property of a
*construction pattern*, not of "synthetic data" as such (§6.1). Second, their findings are the same
symptom seen from another angle — outcome metrics flattering agents whose investigation is
incomplete — which supports our claim that **result-only metrics need validity auditing before
they can support capability claims**.

### 8.2 Detecting false success and over-claiming

Recent work treats false success as an *agent behavior* to be detected from trajectories.
*From Confident Closing to Silent Failure* (arXiv:2606.09863) characterises false success on
9,876 tau2-bench trajectories and shows that **LLM-as-judge is systematically misled by confident
assertion language regardless of the actual outcome**. Cao et al. (arXiv:2603.03116) introduce
Procedure-Aware Evaluation and report that **27–78% of benchmark-reported successes on τ-bench are
"corrupt successes"** concealing procedural violations, and independently document structural flaws
in the benchmark itself.

Our problem sits one stage earlier. When the label is derived from the verifier's probe
expectations, *no judge* — human or model — can recover independent evidence, because the label
carries no information beyond that input. Note also that corrupt success (reward = 1 with a
procedural violation) and false success (reward = 0 with a success claim) are **disjoint
populations**, as Cao et al. also observe; they threaten different deployment risks and require
different instrumentation.

### 8.3 Benchmark validity auditing and construction dependence

This is the family our work belongs to.

**HindAudit** (arXiv:2611.22241) is the closest structural precedent. Auditing clinical agent
benchmarks, its authors locate the main threat to validity in **case construction** rather than in
simulators, and separate three hindsight channels with real-data judges. Its two pitfalls for
leakage audits — placeholder masking can create a new cue for text judges, and comparing raw
probabilities across classifiers can hide large effects — are exactly the kind of caveat our §6.4
needs. We differ in target: HindAudit asks whether the *input* leaks the answer; we ask whether
the *label definition* already contains the answer.

**Metadata Predictability Is Not Evidence Dependence** (arXiv:2605.23701) supplies the framing our
detector should adopt. It separates *metadata predictability* (MPDS, an accuracy ratio against a
metadata-majority predictor) from *evidence dependence* (ΔEvi, the change in accuracy under a
cross-item evidence permutation that keeps queries and labels fixed), and constructs a counterexample
where MPDS is only moderate while ΔEvi is exactly zero. Our `single_bit_separable` is a
predictability statistic; our reversed-polarity control is a low-cost analogue of an intervention.
Explicitly aligning the two would strengthen §2, and we flag in §6.4 that our intervention is only
a single-bit flip, not a general evidence shuffle.

**When the Label Ignores the Request** (ACM, DOI 10.1145/3842413.3842427) audits a synthetic
conversational recommender benchmark and finds labels that contradict the visible request. Its
key methodological point matches our §3.3: generation-time guards run *inside* the generator on
signals the generator trusts, so auditing must be post hoc and use only participant-visible
evidence. Our finding that the assertion vocabulary is drawn from the same 144 claims is the
same species of self-trusted signal.

Finally, the classic lineage of "benchmarks solved by cues" — annotation artifacts (Gururangan et
al., TACL 2018), hypothesis-only baselines (Poliak et al., EMNLP 2018), right-for-the-wrong-reason
diagnostics (McCoy et al., ACL 2019), shortcut learning (Geirhos et al., 2020), and data
contamination (Sainz et al., 2023; Golchin & Surdeanu, ICLR 2024) — motivates treating benchmark
validity as a first-class object of study. Circularity is the limiting case of this lineage: the
cue need not leak from training data or surface wording. It is already in the definition of the
label.

### 8.4 Circularity in synthetic data

A mechanism-guided synthetic tax-risk framework (PLOS ONE, DOI 10.1371/journal.pone.0353137)
states the issue in terms we adopt: *"The mechanisms generate both predictors and labels, so high
discrimination is an internal property of the simulation"*, and lists "synthetic-only evidence and
circularity" among its limitations. Its audit protocol — parameter tracing, constraint verification,
entity-level leakage control, calibration stress testing — is a useful generalisation of our §4
repair protocol.

One reversal is worth flagging. Common audit heuristics treat **invariance** (stable performance
under semantically equivalent perturbations) as a *positive* signal. Our §3.4 reports invariance
under 200 random half-group re-splits and reads it as evidence *against* validity. The difference
is what should vary: perturbation-based invariance probes robustness to phrasing, whereas
re-split invariance probes sensitivity to sample size. A metric that does not respond to sample
size is not robust; it is uninformative.
