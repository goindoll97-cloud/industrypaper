"""No-LLM unit tests: model JSON contradictions and evidence grounding are diagnostic."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from diagnose_raw_failures import audit_consistency


def row(test_id, rel, scope, entry, retrieved):
    return {
        "model": "qwen3.5:4b", "test_id": test_id, "case_id": "M-01",
        "condition": "A", "group": "MIXTURE", "difficulty": "HARD",
        "component_id": "C1", "gold_relation": "DIRECT_SPECIFIC",
        "predicted_relation": rel, "predicted_scope": scope,
        "predicted_designation_id": entry, "retrieved_gold_row": 1,
        "retrieved_designation_ids": json.dumps(retrieved),
    }


class ConsistencyTests(unittest.TestCase):
    def test_scope_contradictions_and_insufficient_not_forced(self):
        cases = [
            row("M-01-A", "DIRECT_SPECIFIC", False, "97-1-80", ["97-1-80"]),
            row("M-02-A", "EXPLICIT_EXCEPTION", True, "97-1-377", ["97-1-377"]),
            row("M-03-A", "NOT_COVERED", False, "", []),
            row("M-04-A", "INSUFFICIENT_EVIDENCE", True, "", []),
            row("M-05-A", "", "", "", []),
        ]
        output, summary = audit_consistency(cases)
        self.assertEqual([r["relation_scope_contradiction"] for r in output], [1,1,0,0,0])
        self.assertEqual([r["relation_scope_checkable"] for r in output], [1,1,1,0,0])
        full = next(x for x in summary if x["group"] == "ALL")
        self.assertEqual(full["component_n"], 5)
        self.assertEqual(full["relation_scope_checkable_n"], 3)
        self.assertEqual(full["relation_scope_contradiction_n"], 2)
        self.assertEqual(full["cited_returned_evidence_n"], 2)

    def test_reference_ids_not_retrieved_vs_malformed(self):
        cases = [
            row("M-01-A", "DIRECT_SPECIFIC", True, "97-1-80", ["97-1-80"]),
            row("M-02-A", "DIRECT_SPECIFIC", True, "97-1-999", ["97-1-80"]),
            row("M-03-A", "DIRECT_SPECIFIC", True, "67-56-1", ["97-1-80"]),
            row("M-04-A", "DIRECT_SPECIFIC", True, "", []),
        ]
        output, summary = audit_consistency(cases)
        self.assertEqual([r["designation_grounding"] for r in output],
            ["cited_returned_evidence", "legal_id_not_in_returned_evidence",
             "invalid_designation_id_format", "not_reported"])
        full = next(x for x in summary if x["group"] == "ALL")
        self.assertEqual(full["relation_scope_contradiction_n"], 0)
        self.assertEqual(full["legal_id_not_in_returned_evidence_n"], 1)
        self.assertEqual(full["invalid_designation_id_format_n"], 1)
        self.assertEqual(full["designation_id_not_reported_n"], 1)


if __name__ == "__main__":
    unittest.main()
