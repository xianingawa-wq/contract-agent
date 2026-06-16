import unittest

from contract_agent import models as old_models
from contract_agent import report as old_report
from contract_agent import rules as old_rules
from contract_agent import service as old_service
from contract_agent.review import models as new_models
from contract_agent.review import reporting as new_reporting
from contract_agent.review import rules as new_rules
from contract_agent.review import service as new_service


class ReviewPackageCompatibilityTests(unittest.TestCase):
    def test_old_root_imports_reexport_review_package_objects(self):
        self.assertIs(old_models.ReviewRequest, new_models.ReviewRequest)
        self.assertIs(old_models.Finding, new_models.Finding)
        self.assertIs(old_models.ReviewReport, new_models.ReviewReport)
        self.assertIs(old_models.Severity, new_models.Severity)
        self.assertIs(old_rules.run_rules, new_rules.run_rules)
        self.assertIs(old_rules.normalize_side, new_rules.normalize_side)
        self.assertIs(old_report.render_json, new_reporting.render_json)
        self.assertIs(old_report.render_markdown, new_reporting.render_markdown)
        self.assertIs(old_service.review_text, new_service.review_text)


if __name__ == "__main__":
    unittest.main()
