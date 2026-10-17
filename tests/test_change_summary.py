import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from index import build_readable_change_summary


class ChangeSummaryTests(unittest.TestCase):
    def test_ignores_missing_vs_empty_string(self):
        previous_json = json.dumps({"status": ""}, ensure_ascii=False)
        current_json = json.dumps({}, ensure_ascii=False)
        summary = build_readable_change_summary(previous_json, current_json)
        self.assertEqual(summary, "")

    def test_reports_real_value_change(self):
        previous_json = json.dumps({"modules": [{"id": "T1000", "grade": "1,7"}]}, ensure_ascii=False)
        current_json = json.dumps({"modules": [{"id": "T1000", "grade": "1,3"}]}, ensure_ascii=False)
        summary = build_readable_change_summary(previous_json, current_json)
        self.assertIn("modules[0].grade", summary)
        self.assertIn('"1,7" → "1,3"', summary)

    def test_reports_grade_deletion_scenario(self):
        previous_json = json.dumps({
            "modules": [{
                "category": "2024 T-INF Kernmodule",
                "credits": "5,0",
                "date": "",
                "grade": "1,7",
                "id": "T4INF1002",
                "name": "Theoretische Informatik I",
                "partial_results": [{
                    "attempt": "Versuch 1",
                    "date": "16.06.2025",
                    "exam": "Klausur (100%)",
                    "grade": "1,7",
                    "semester": "SoSe 2025",
                    "unit": "Modulabschlussleistungen"
                }],
                "status": "Bestanden"
            }]
        }, ensure_ascii=False)
        current_json = json.dumps({
            "modules": [{
                "category": "2024 T-INF Kernmodule",
                "credits": "",
                "date": "",
                "grade": "",
                "id": "T4INF1002",
                "name": "Theoretische Informatik I",
                "partial_results": [],
                "status": "Offen"
            }]
        }, ensure_ascii=False)

        summary = build_readable_change_summary(previous_json, current_json)
        self.assertIn('modules[0].grade: "1,7" → ""', summary)
        self.assertIn('modules[0].status: "Bestanden" → "Offen"', summary)


if __name__ == "__main__":
    unittest.main()
