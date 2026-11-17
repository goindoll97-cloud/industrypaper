# -*- coding: utf-8 -*-
"""Run a frozen 112-query CAS retrieval benchmark locally with Ollama.

No Anthropic API, no PubChem lookup, no RDKit rerun. Requires Python >= 3.10.
The 49 archived Hybrid gate decisions are reused unchanged.
For the other 63 queries, the SAME Ollama sample is used in both arms.
GOLD is loaded only by score, never by check or run.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
FILES = {
    "input": ROOT / "data/retrieval_INPUT.csv",
    "catalog": ROOT / "data/regulatory_catalog.csv",
    "smiles": ROOT / "intermediate/shared_pubchem_smiles.csv",
    "gate": ROOT / "intermediate/hybrid_gate_preflight.csv",
    "manifest": ROOT / "intermediate/prompt_manifest.csv",
}
GOLD = ROOT / "data/retrieval_GOLD.csv"
SYSTEM_PROMPT = """You are performing regulatory identity retrieval for a controlled chemical benchmark.
You receive only candidate CAS identifier(s), PubChem-derived SMILES for those CAS identifiers,
and a fixed regulatory catalog that is the search space.
Find which single catalog target the candidate belongs to.
A catalog entry's isomer_scope states which stereoisomers of its reference substance are covered.
If the reference SMILES defines no stereochemistry, every stereoisomer is covered. Otherwise:
ALL_STEREOISOMERS covers every stereoisomer; EXACT_STEREO_ONLY covers only the stereochemistry
drawn in the reference SMILES; UNSPECIFIED_REVIEW means stereo-only differences cannot be decided.
Return NOT_FOUND when none of the catalog targets applies.
Return REVIEW only when the supplied CAS/SMILES/catalog information is insufficient to decide reliably.
Do not use or infer hidden benchmark labels. Do not browse or use external knowledge beyond the supplied fields.
The catalog itself is the allowed regulatory reference database.
Return only the requested JSON object."""
SCHEMA = {
    "type": "object",
    "properties": {
        "query_id": {"type": "string"},
        "status": {"type": "string", "enum": ["FOUND", "NOT_FOUND", "REVIEW"]},
        "target_id": {"type": "string"},
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
    },
    "required": ["query_id", "status", "target_id", "reason", "confidence"],
    "additionalProperties": False,
}


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def htext(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def csv_out(path, data):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)


def split(text):
    return [s.strip() for s in (text or "").split("|") if s.strip()]


def create_prompts(queries, catalog, smiles):
    def rec(cas):
        return {"cas": cas, "smiles": smiles.get(cas, "")}

    entries = []
    for r in catalog:
        item = {"target_id": r["target_id"],
                "regulatory_scope": r["regulatory_scope_text"]}
        if split(r["reference_cas_set"]):
            item["reference_substances"] = [rec(x) for x in split(r["reference_cas_set"])]
        if r["isomer_scope"]:
            if r["isomer_scope"] not in {
                "ALL_STEREOISOMERS", "EXACT_STEREO_ONLY", "UNSPECIFIED_REVIEW"
            }:
                raise ValueError("Unrecognized isomer scope in catalog.")
            item["isomer_scope"] = r["isomer_scope"]
        if split(r["official_member_cas_set"]):
            item["official_enumerated_members"] = [
                rec(x) for x in split(r["official_member_cas_set"])]
        mixture = {}
        if split(r["official_mixture_cas"]):
            mixture["mixture_cas"] = [rec(x) for x in split(r["official_mixture_cas"])]
        if split(r["mixture_component_cas_set"]):
            mixture["component_cas"] = [rec(x) for x in split(r["mixture_component_cas_set"])]
        if mixture:
            item["mixture_identity"] = mixture
        entries.append(item)
    prompts = {}
    for q in queries:
        payload = {
            "candidate_query": {
                "query_id": q["query_id"],
                "candidate": [rec(x) for x in split(q["cas_inputs"])],
            },
            "regulatory_catalog": entries,
            "task": (
                "Search the entire regulatory catalog. Return the one target_id that the candidate "
                "belongs to. If none applies, return NOT_FOUND. If the supplied CAS/SMILES information "
                "is insufficient to decide reliably, return REVIEW."
            ),
        }
        prompts[q["query_id"]] = "INPUT=" + json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"))
    return prompts


def load_frozen():
    for p in FILES.values():
        if not p.exists():
            raise FileNotFoundError(f"Missing required file: {p}")
    queries = rows(FILES["input"])
    catalog = rows(FILES["catalog"])
    smiles = {r["cas"]: r["smiles"] for r in rows(FILES["smiles"])}
    gates = {r["query_id"]: r for r in rows(FILES["gate"])}
    prompts = create_prompts(queries, catalog, smiles)
    manifest = rows(FILES["manifest"])
    qids = [r["query_id"] for r in queries]
    if len(set(qids)) != 112 or len(queries) != 112 or len(catalog) != 29:
        raise RuntimeError("Expected 112 unique queries and 29 catalog targets.")
    if set(gates) != set(qids) or len(manifest) != 224:
        raise RuntimeError("The frozen Hybrid gate or Claude prompt manifest is incomplete.")
    for r in manifest:
        qid = r["query_id"]
        if qid not in prompts or htext(prompts[qid]) != r["prompt_sha256"]:
            raise RuntimeError(f"Claude prompt SHA mismatch: {qid}. Stop experiment.")
        if len(prompts[qid]) != int(r["prompt_chars"]):
            raise RuntimeError(f"Claude prompt length mismatch: {qid}.")
    counts = Counter(g["gate_status"] for g in gates.values())
    if counts != {"FOUND": 49, "REVIEW": 63}:
        raise RuntimeError(f"Hybrid gate changed: {counts}")
    ids = {r["target_id"] for r in catalog}
    for g in gates.values():
        if g["gate_status"] == "FOUND" and g["gate_target_id"] not in ids:
            raise RuntimeError("Gate contains an unknown target.")
    return {
        "queries": queries, "catalog": catalog, "gates": gates,
        "prompts": prompts, "target_ids": ids,
        "input_sha256": {k: sha(p) for k, p in FILES.items()},
    }


def api(url, body=None, timeout=900):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    request = urllib.request.Request(
        url, data=data, method="POST" if body is not None else "GET",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def get_model(args):
    info = api(args.host.rstrip("/") + "/api/tags", timeout=args.timeout)
    matches = [r for r in info.get("models", []) if args.model in
               {r.get("name"), r.get("model")}]
    if not matches and ":" not in args.model:
        matches = [r for r in info.get("models", []) if args.model + ":latest" in
                   {r.get("name"), r.get("model")}]
    if len(matches) != 1:
        raise RuntimeError("Ollama model not installed. Run: ollama pull " + args.model)
    digest = matches[0].get("digest")
    if not digest:
        raise RuntimeError("Ollama model digest missing.")
    return matches[0]["name"], digest


def directory(args):
    model = re.sub("[^A-Za-z0-9._-]", "_", args.model)
    run_id = re.sub("[^A-Za-z0-9._-]", "_", args.run_id)
    if not run_id or run_id.startswith("."):
        raise ValueError("Invalid run-id.")
    return HERE / "results" / (model + "__" + run_id)


def settings(args, frozen, model, digest):
    return {
        "protocol": "OLLAMA_PAIRED_REPEATS_V1",
        "model": model, "model_digest": digest,
        "repeats": args.repeats, "temperature": args.temperature,
        "num_ctx": args.num_ctx, "num_predict": args.num_predict,
        "thinking": False, "output": "JSON_SCHEMA",
        "seed": None,
        "system_prompt_sha256": htext(SYSTEM_PROMPT),
        "input_sha256": frozen["input_sha256"],
        "gate_source": "ARCHIVED_49_DIRECT_63_REVIEW",
        "paired_shared_llm_response": True,
    }


def save_json(path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def normalize(text, qid, target_ids):
    r = json.loads(text)
    if not isinstance(r, dict) or r.get("query_id") != qid:
        raise ValueError(f"Invalid JSON object or query_id: {qid}")
    status = str(r.get("status", "")).upper()
    target = str(r.get("target_id") or "")
    if status not in {"FOUND", "NOT_FOUND", "REVIEW"}:
        raise ValueError(f"Invalid status for {qid}")
    if status == "FOUND" and target not in target_ids:
        status, target = "REVIEW", ""
    if status != "FOUND":
        target = ""
    return {
        "query_id": qid, "status": status, "target_id": target,
        "confidence": str(r.get("confidence") or ""),
        "reason": str(r.get("reason") or ""),
    }


def run(args, frozen):
    model, digest = get_model(args)
    out = directory(args)
    conf = settings(args, frozen, model, digest)
    out.mkdir(parents=True, exist_ok=True)
    cfile = out / "run_config.json"
    if cfile.exists() and json.loads(cfile.read_text(encoding="utf-8")) != conf:
        raise RuntimeError("Model/options/input changed; choose a NEW --run-id.")
    save_json(cfile, conf)
    (out / "calls").mkdir(exist_ok=True)
    queries = frozen["queries"]
    if args.query_id:
        queries = [r for r in queries if r["query_id"] == args.query_id]
        if not queries:
            raise ValueError("Unknown query-id.")
    if args.limit:
        queries = queries[:args.limit]
    completed = failed = cached = 0
    for rep in range(1, args.repeats + 1):
        for q in queries:
            qid = q["query_id"]
            path = out / "calls" / f"r{rep:02d}_{qid}.json"
            digest_prompt = htext(frozen["prompts"][qid])
            if path.exists():
                old = json.loads(path.read_text(encoding="utf-8"))
                if old.get("call_status") == "OK" and old.get("prompt_sha256") == digest_prompt:
                    cached += 1
                    continue
                raise RuntimeError(f"Invalid existing call, inspect: {path}")
            print(f"repeat {rep}/{args.repeats}, {qid}", flush=True)
            request = {
                "model": model, "stream": False, "think": False,
                "format": SCHEMA,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": frozen["prompts"][qid]},
                ],
                "options": {
                    "temperature": args.temperature,
                    "num_ctx": args.num_ctx,
                    "num_predict": args.num_predict,
                },
            }
            start = time.perf_counter()
            try:
                response = api(args.host.rstrip("/") + "/api/chat",
                               request, timeout=args.timeout)
                raw = (response.get("message") or {}).get("content", "")
                parsed = normalize(raw, qid, frozen["target_ids"])
                parsed.update({
                    "call_status": "OK", "repeat": rep,
                    "at_utc": datetime.now(timezone.utc).isoformat(),
                    "prompt_sha256": digest_prompt, "raw_response": raw,
                    "model_returned": response.get("model"),
                    "prompt_eval_count": response.get("prompt_eval_count"),
                    "eval_count": response.get("eval_count"),
                    "total_duration_ns": response.get("total_duration"),
                    "elapsed_sec": time.perf_counter() - start,
                })
                save_json(path, parsed)
                completed += 1
            except Exception as exc:
                failed += 1
                with (out / "failures.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "repeat": rep, "query_id": qid,
                        "error": type(exc).__name__ + ": " + str(exc),
                    }, ensure_ascii=False) + "\n")
                print(f"ERROR {qid}: {exc}", file=sys.stderr, flush=True)
    print(f"New OK: {completed}; cached: {cached}; failures: {failed}. "
          "Only complete 112 x repeats can be scored.")
    if failed:
        raise RuntimeError("Some calls failed. Rerun the SAME command to resume.")


def score(args, frozen):
    out = directory(args)
    cfile = out / "run_config.json"
    if not cfile.exists():
        raise FileNotFoundError("No Ollama run config: " + str(cfile))
    conf = json.loads(cfile.read_text(encoding="utf-8"))
    if conf["repeats"] != args.repeats or conf["input_sha256"] != frozen["input_sha256"]:
        raise RuntimeError("Repeat count/input mismatch; use original settings.")
    if not GOLD.is_file():
        raise FileNotFoundError("Frozen gold labels missing.")
    gold = {r["query_id"]: r for r in rows(GOLD)}
    if set(gold) != set(frozen["prompts"]):
        raise RuntimeError("GOLD query IDs do not match the benchmark.")
    preds, metrics, stable = [], [], []
    all_calls = {}
    missing = []
    for rep in range(1, args.repeats + 1):
        for q in frozen["queries"]:
            qid = q["query_id"]
            path = out / "calls" / f"r{rep:02d}_{qid}.json"
            if not path.exists():
                missing.append((rep, qid))
                continue
            r = json.loads(path.read_text(encoding="utf-8"))
            if r.get("call_status") != "OK" or r.get("prompt_sha256") != htext(frozen["prompts"][qid]):
                missing.append((rep, qid))
                continue
            all_calls[(rep, qid)] = r
    if missing:
        raise RuntimeError(f"{len(missing)} calls missing/invalid; first 10: {missing[:10]}. "
                           "Resume run before scoring.")
    for rep in range(1, args.repeats + 1):
        for q in frozen["queries"]:
            qid = q["query_id"]
            g = frozen["gates"][qid]
            truth = gold[qid]["gold_target_id"] if gold[qid]["gold_status"] == "FOUND" else "NOT_FOUND"
            r = all_calls[(rep, qid)]
            for system in ("LLM_ONLY", "HYBRID"):
                if system == "HYBRID" and g["gate_status"] == "FOUND":
                    status, target, source = "FOUND", g["gate_target_id"], "FROZEN_GATE"
                else:
                    status, target, source = r["status"], r["target_id"], "SHARED_OLLAMA"
                pred = target if status == "FOUND" else status
                preds.append({
                    "query_id": qid, "repeat": rep, "system": system,
                    "status": status, "target_id": target,
                    "predicted_outcome": pred, "gold_outcome": truth,
                    "correct": int(pred == truth),
                    "decision_source": source,
                    "source_categories": gold[qid]["source_categories"],
                })
    csv_out(out / "predictions_by_repeat.csv", preds)
    for system in ("LLM_ONLY", "HYBRID"):
        cases = [p for p in preds if p["system"] == system]
        for rep in range(1, args.repeats + 1):
            sub = [p for p in cases if p["repeat"] == rep]
            metrics.append({
                "system": system, "repeat": rep, "n": 112,
                "correct": sum(p["correct"] for p in sub),
                "accuracy": sum(p["correct"] for p in sub) / 112,
                "false_inclusion": sum(p["gold_outcome"] == "NOT_FOUND"
                                      and p["status"] == "FOUND" for p in sub),
                "false_exclusion": sum(p["gold_outcome"] != "NOT_FOUND"
                                      and p["status"] == "NOT_FOUND" for p in sub),
                "wrong_target": sum(p["gold_outcome"] != "NOT_FOUND"
                                    and p["status"] == "FOUND"
                                    and not p["correct"] for p in sub),
                "review": sum(p["status"] == "REVIEW" for p in sub),
            })
        for q in frozen["queries"]:
            qid = q["query_id"]
            sub = [p for p in cases if p["query_id"] == qid]
            counts = Counter(p["predicted_outcome"] for p in sub)
            label, count = counts.most_common(1)[0]
            majority = label if count > args.repeats / 2 else "REVIEW"
            stable.append({
                "system": system, "query_id": qid,
                "gold_outcome": sub[0]["gold_outcome"],
                "distinct_predictions": len(counts),
                "all_identical": int(len(counts) == 1),
                "majority_prediction": majority,
                "majority_correct": int(majority == sub[0]["gold_outcome"]),
                "correct_repeats": sum(p["correct"] for p in sub),
                "outcome_counts": json.dumps(counts, ensure_ascii=False),
            })
    csv_out(out / "accuracy_by_repeat.csv", metrics)
    csv_out(out / "consistency_by_query.csv", stable)
    summary = {
        "model": conf["model"], "model_digest": conf["model_digest"],
        "n_queries": 112, "repeats": args.repeats,
        "actual_ollama_calls": len(all_calls), "hybrid_frozen_gate": 49,
        "paired_response_reuse": True, "systems": {},
    }
    for system in ("LLM_ONLY", "HYBRID"):
        a = [r for r in metrics if r["system"] == system]
        b = [r for r in stable if r["system"] == system]
        summary["systems"][system] = {
            "mean_accuracy": sum(x["accuracy"] for x in a) / len(a),
            "min_accuracy": min(x["accuracy"] for x in a),
            "max_accuracy": max(x["accuracy"] for x in a),
            "stable_queries": sum(x["all_identical"] for x in b),
            "stable_fraction": sum(x["all_identical"] for x in b) / 112,
            "majority_accuracy": sum(x["majority_correct"] for x in b) / 112,
        }
    summary["ollama_telemetry"] = {
        "sum_elapsed_sec": sum(float(x["elapsed_sec"]) for x in all_calls.values()),
        "sum_prompt_eval_count": sum(int(x.get("prompt_eval_count") or 0) for x in all_calls.values()),
        "sum_eval_count": sum(int(x.get("eval_count") or 0) for x in all_calls.values()),
    }
    summary["limitations"] = (
        "Local Ollama latency and token accounting are not directly comparable "
        "to Claude API. Frozen Hybrid gate is replayed, not rerun with RDKit. "
        "Claude was evaluated once; Qwen repeats do not establish Claude repeat stability.")
    save_json(out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Saved reports to:", out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["check", "run", "score"])
    p.add_argument("--model", default="qwen3:8b")
    p.add_argument("--run-id", default="main")
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument("--num-ctx", type=int, default=32768)
    p.add_argument("--num-predict", type=int, default=700)
    p.add_argument("--host", default="http://127.0.0.1:11434")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--limit", type=int, help="Pilot: limit the number of queries.")
    p.add_argument("--query-id", help="Run or resume one query only.")
    a = p.parse_args()
    if a.repeats < 2 or a.num_ctx < 16384 or not (0 <= a.temperature <= 2):
        p.error("Requires repeats >=2, num_ctx >=16384, temperature in [0,2].")
    if a.limit is not None and not 1 <= a.limit <= 112:
        p.error("limit must be 1..112.")
    frozen = load_frozen()
    print("Claude prompt hashes verified: 112 queries, 29 targets, 49 gate FOUND, 63 REVIEW.")
    if a.command == "check":
        print("Offline check succeeded. Ollama/GOLD/RDKit not required.")
    elif a.command == "run":
        run(a, frozen)
    else:
        score(a, frozen)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, FileNotFoundError, OSError) as exc:
        print("ERROR:", str(exc), file=sys.stderr)
        sys.exit(1)
