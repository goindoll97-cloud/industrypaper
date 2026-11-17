# Ollama follow-up experiment

## Research design

This is an **additional experiment**, not a replacement for the original Claude study.

- Same 112 CAS query cases and 29 regulatory targets.
- Same original Claude system prompt and exact user prompt (verified against 175 saved prompt manifest rows).
- Same frozen Hybrid preflight: 49 direct decisions and 63 review cases.
- Default Ollama model: qwen3:8b, five repetitions for every query.
- **Paired response design:** for each repetition the SAME Ollama response is reused for the LLM-only arm and the Hybrid review arm. Thus 112 x 5 = **560 calls**, not two separately sampled arms.
- The original Claude experiment used separately sampled LLM calls; note this methodological difference in the paper.
- GOLD labels are only loaded in scoring, never included in the LLM inputs.
- The script does NOT rerun RDKit. It reuses the archived 49 decisions because the original parent/salt RDKit engine file is missing from this GitHub repository.

## Windows quick start (PowerShell)

Install Ollama from https://ollama.com/download and install Python 3.10+.

Clone the repository or use GitHub Code > Download ZIP. From its folder:

    git clone https://github.com/goindoll97-cloud/industrypaper.git
    cd industrypaper

Download and check one Ollama model:

    ollama pull qwen3:8b
    ollama list

If the Ollama application is not running, start it or run ollama serve in another terminal.

Offline protocol check (no Ollama, Anthropic API, PubChem or RDKit required):

    python ollama_followup/run_ollama_followup.py check

Pilot experiment (2 queries x 5 repeats = 10 local calls):

    python ollama_followup/run_ollama_followup.py run --model qwen3:8b --repeats 5 --limit 2

Full experiment (resumes, does not duplicate completed calls):

    python ollama_followup/run_ollama_followup.py run --model qwen3:8b --repeats 5

Score after all 560 successful calls exist:

    python ollama_followup/run_ollama_followup.py score --model qwen3:8b --repeats 5

If testing another locally installed model, change the model in BOTH run and score:

    ollama pull qwen3:14b
    python ollama_followup/run_ollama_followup.py run --model qwen3:14b --repeats 5
    python ollama_followup/run_ollama_followup.py score --model qwen3:14b --repeats 5

For a separate independent run of the same model, add --run-id replication2 to both commands.

## Options and safeguards

Default settings:

- repeats = 5; temperature = 0.3, no fixed random seed;
- num_ctx = 32768; num_predict = 700;
- host = http://127.0.0.1:11434; timeout = 900 seconds;
- thinking = false; JSON schema constrained response.

Optional --query-id RQ-0001 selects a one-query pilot. Optional --limit 2 runs only the first two cases. Scoring ALWAYS requires all 112 cases to have every repeat.

The first run stores model name, exact model digest, prompt hash, input file hashes and decoding configuration. Changing model, digest, input or generation settings under an existing run directory stops instead of mixing unlike data. For a new setup, change --run-id.

The results folder is excluded from automatic Git tracking; archive it separately if you want to preserve actual outputs.

Generated report paths under ollama_followup/results/MODEL__main:

- run_config.json: experiment settings, model revision digest, input file hashes
- calls/: each individual raw and normalized Ollama answer, local token and timing telemetry
- failures.jsonl: failures/invalid JSON attempts
- predictions_by_repeat.csv: paired outcome by repeat and method
- accuracy_by_repeat.csv: repeat-level accuracy and types of error
- consistency_by_query.csv: stability and strict majority outcome per query
- summary.json: aggregate statistics; local Ollama timings only

## Manuscript interpretation and limitations

Treat Claude as a single-run study and Ollama as the repeated external-model study. Do not combine them into one pooled repeat sample. The 49 deterministic Hybrid results are replayed from the frozen Claude experiment, not newly validated by RDKit.

Claude API token accounting and latency cannot be directly compared to local Ollama runtimes. Model capacity, quantization, context support and settings may differ despite identical candidate/user prompts.

The 49 deterministic cases in the archived experiment are positive examples; 49/49 success does not establish specificity on negative cases. Additional held-out negative cases would further strengthen the research.

WARNING: Some original repository files have unresolved Git merge-conflict markers, and the RDKit parent/salt engine source is not uploaded. The new script is intentionally standalone and does not import those original modules. Before full end-to-end reconstruction of the original pipeline, recover the missing engine and resolve those conflicts.
