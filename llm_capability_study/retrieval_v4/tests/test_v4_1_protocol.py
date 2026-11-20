"""Offline regression checks for revised Gold integrity and v4.1 runner."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gold_integrity import expected_gold_sha
from run_retrieval import parse_queries, parse_answer, answer_format
from search_legal_db import row_score


class ProtocolTests(unittest.TestCase):
    def test_query_id_prefix_only_for_same_case(self):
        raw = json.dumps({"searches":[{"component_id":"S-01-A-C1","queries":["CAS 65-30-5"]}]})
        self.assertEqual(parse_queries(raw, ["C1"], "S-01-A"), {"C1":["CAS 65-30-5"]})
        self.assertIsNone(parse_queries(raw, ["C1"], "S-02-A"))

    def test_duplicate_id_not_accepted(self):
        raw = json.dumps({"searches":[{"component_id":"C1","queries":["nicotine"]},
              {"component_id":"S-01-A-C1","queries":["nicotine sulfate"]}]})
        self.assertIsNone(parse_queries(raw, ["C1"], "S-01-A"))

    def test_single_vs_mixture_schema(self):
        single={"test_id":"S-01-A","scenario_kind":"PURE_SUBSTANCE","components":[{"component_id":"C1"}]}
        mix={"test_id":"M-06-B","scenario_kind":"FORMULATED_MIXTURE",
             "components":[{"component_id":f"C{i}"} for i in range(1,4)]}
        self.assertEqual(answer_format(single)["properties"]["all_components_designated"], {"type":"null"})
        self.assertEqual(answer_format(mix)["properties"]["all_components_designated"], {"type":"boolean"})
        self.assertEqual(answer_format(mix)["properties"]["components"]["minItems"], 3)

    def test_cas_prefixed_exact_match(self):
        row={"name_ko":"메탄올","name_en":"Methanol","cas_field":"67-56-1"}
        self.assertEqual(row_score("67-56-1", row), 1500)
        self.assertEqual(row_score("CAS 67-56-1", row), 1500)
        self.assertNotEqual(row_score("CAS 75-05-8", row), 1500)

    def test_registry_uses_private_hash_without_editing_public_manifest(self):
        manifest={"gold_sha256":"a"*64,"cases_sha256":"b"*64,"annex_sha256":"c"*64}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(expected_gold_sha(root, manifest), "a"*64)
            (root/"private").mkdir()
            (root/"private"/"gold_registry.json").write_text(json.dumps({
                "gold_sha256":"d"*64,"cases_sha256":"b"*64,"annex_sha256":"c"*64
            }), encoding="utf-8")
            self.assertEqual(expected_gold_sha(root, manifest), "d"*64)
            (root/"private"/"gold_registry.json").write_text(json.dumps({
                "gold_sha256":"d"*64,"cases_sha256":"NOT_THE_SAME","annex_sha256":"c"*64
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                expected_gold_sha(root, manifest)


if __name__ == "__main__":
    unittest.main()
