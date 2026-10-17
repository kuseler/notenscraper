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


if __name__ == "__main__":
    unittest.main()
