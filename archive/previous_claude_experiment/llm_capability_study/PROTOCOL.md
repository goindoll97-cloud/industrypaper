# Study 3: LLM capability and decision consistency

## Research question

**Can stronger large language models identify chemical regulatory targets more accurately and consistently, given the same frozen regulatory reference? Where do errors persist?**

Important distinction: this tests *identification within a specified catalog*, NOT whether a law has no regulatory coverage or whether AI can close a legislative gap.

## Current verified starting point

- Benchmark: `data/retrieval_INPUT.csv`, `data/retrieval_GOLD.csv`
- Frozen search catalog: `data/regulatory_catalog.csv` with **29 target IDs**
- **112 unique queries**: **60 FOUND / 52 NOT_FOUND** *relative to these 29 target IDs*
- Source types: **72 parent/salt**, **30 chemical group**, **10 named mixture**
- Existing Claude baseline: 112 LLM-only queries, one successful scored response per query, retained in the original `intermediate/` files.
- Existing Ollama hybrid experiment is separate, in `ollama_followup/`. **Do not use its Hybrid data in Study 3**.

## Freeze decisions before collecting new compounds

1. **Target universe:** keep the original 29 regulatory target IDs frozen for the primary comparison, including their exact regulatory scope and isomer interpretation. If the catalog is expanded, treat it as a SEPARATE benchmark: a new catalog changes the question and the prompt.
2. **Chemical input:** retain the original CAS-only/candidate SMILES plus the whole fixed catalog design. Do not expose candidate name, synonyms, source group, GOLD answers or reviewer notes to the tested LLM.
3. **Outcome:** exact target ID, `NOT_FOUND` (only from the 29-target catalog), or `REVIEW` when a decision is not justified. RE​VIEW is an abstention, not automatically correct.
4. **Gold standard:** legal scope comes from a documented regulatory source, identity from verified CAS and/or molecular structure evidence. Every proposed Gold label must receive documented, source-based researcher adjudication BEFORE any model predictions are inspected. An independent second reviewer is optional, not a required dataset-freeze condition; the lack of independent agreement evidence must be disclosed as a study limitation.
5. **Dataset separation:** existing 112 cases are a frozen historical baseline. New cases are a separately labelled extension/holdout. Do not amend the old 112 labels or revise the test set after seeing model output.
6. **Model comparison:** freeze prompts, complete model identifiers and digests, quantization, decoding settings, maximum context, and evaluation date. Use the same accessible regulatory information for all models; ensure the prompt fits each model's context. Larger parameter count is not an established ranking of regulatory competence.
7. **Repeated answers:** target **5 independent samples per case per model** initially; report per-case prediction agreement and accuracy separately. Do not count repeats as independent chemical cases.
8. **Scoring:** exact target accuracy, sensitivity for in-catalog cases, specificity for out-of-catalog cases, wrong-target rate, false inclusion, false exclusion, abstention, per-category accuracy, and per-case stability. Consider uncertainty with case-level paired analyses/cluster bootstrap.
9. **No regulatory source fabrication:** blank or ambiguous legal evidence requires adjudication or exclusion from accuracy analysis. Never treat lack of a PubChem SMILES as proof of NOT_FOUND.

## Candidate sampling frames (revised)

Study 3 must NOT require all evaluation chemicals to be close to the 29 target entries.
The PubChem candidate collector now records three independent sampling frames:

1. CATALOG_LISTED: CAS values appearing in frozen catalog reference/member lists but not already tested.
2. NEAR_CATALOG: PubChem structure-similarity and salt searches anchored on frozen catalog entries.
3. INDEPENDENT_GENERAL: names drawn from multiple broad chemical categories and seeded numeric PubChem CID probes **without looking up starting seeds in the 29 target list**. These are not guaranteed to be structurally far from targets or legally NOT_FOUND.

Typical *recruitment* quotas are 20%/40%/40%, adjustable. Each observed mixture may still need independent evidence.
CID-range probing is reproducible but **not a representative random draw of PubChem chemical records**, since numeric CIDs reflect assignment history and gaps. Report the sampling frame, selection parameters, and errors by stratum.

The candidate generation output source_category GENERAL_CHEMICAL is a provenance label, NOT a fourth legal target type. A reviewer should assign the final analytic category (e.g., independently sourced out-of-catalog case, near miss, or a true in-catalog target) only after verifying the full 29-target legal scope. Every newly collected row starts REVIEW_PENDING and no negative label is inferred merely from its discovery frame.

Across collection batches, use --exclude-file to exclude prior CAS signatures as well as the frozen 112 cases. Use separate --run-id labels and different --random-seed values to expand the numeric CID probe frame without overwriting earlier outputs.

## Expand only after the protocol above is fixed

Target ~300-400 distinct chemical cases as a *planning goal*, NOT a fixed statistical sample size. Start with an audited pilot of **40-60 NEW cases** and grow only once identity and legal-source reviews work. Stratify by **target type** and **gold status**, especially the underrepresented 10 named mixtures and difficult negative near-neighbor cases. Use quotas as recruitment guidance, not a claim of population prevalence.

For each candidate use the fields in `new_cases_template.csv`:

- `case_id`: unique temporary identifier (e.g. NEW-0001)
- `cas_inputs`: CAS number or pipe-separated mixture-component CAS
- `source_category`: PARENT_SALT / CHEMICAL_GROUP / MIXTURE
- `difficulty_tag`: EXACT_LISTED / SALT / GROUP_MEMBERSHIP / MIXTURE_COMPONENTS / STRUCTURAL_NEAR_MISS / STEREO_OR_AMBIGUOUS
- `gold_status`: FOUND / NOT_FOUND / REVIEW_PENDING
- `gold_target_id`: one of the 29 target IDs when FOUND, or NOT_FOUND; leave blank for REVIEW_PENDING
- `regulatory_source_url` and `regulatory_source_date`: immutable evidence and version of the regulatory source
- `identity_evidence_url`, `smiles`, `smiles_qc_status`: identity and structure provenance
- `reviewer1_status`, `reviewer2_status`, `adjudication_status`: optional second-review fields; the required case-level legal/chemical basis is documented in `human_legal_basis` of the reviewer sheet.
- `notes_human_only`: research notes (NEVER exposed to tested models)

The template intentionally starts **without fabricated chemical rows**. The evaluator should reject pending/unverified rows rather than silently counting them.

## Immediate next steps

1. Run `python llm_capability_study/audit_baseline.py`; inspect `llm_capability_study/output/baseline_summary.json` and `baseline_inventory.csv`.
2. Adjudicate the first 40-60 rows in a separate working copy using verifiable legal and identity evidence. Independent expert review may be added but is not mandatory.
3. Freeze a versioned expansion dataset, then implement the LLM-only run/scoring protocol for the extended sample. Model fitting or prompt tuning should use a different development set, not the evaluation set.
4. Report Claude only on the 112 historical cases; Claude was not repeated and has NO results for the expansion.

## Protocol amendment log

- **2026-11-17 — Independent reviewer requirement changed:** the initial plan asked for two independent reviewers to verify new labels. The dataset-freeze gate now requires **documented official legal scope, chemical identity, adjudication evidence and a versioned audit trail**, not two distinct reviewer files. Optional second review remains beneficial but is not enforced. This change was recorded **before running the new Study 3 LLM comparison**; it does not retroactively verify the Gold labels and must be stated in the manuscript's limitations.
- The frozen historical 112-case baseline, target universe of 29 IDs, and the model-input anti-leakage rules are unchanged.
