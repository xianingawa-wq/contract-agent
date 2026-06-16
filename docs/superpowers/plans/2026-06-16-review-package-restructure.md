# Review Package Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the local contract review facade into `contract_agent.review` while preserving old root import paths.

**Architecture:** Create a focused `contract_agent/review` package for local review models, rule adaptation, reporting, and orchestration. Keep `contract_agent/models.py`, `rules.py`, `report.py`, and `service.py` as compatibility shims that re-export the new implementation.

**Tech Stack:** Python 3.11+, dataclasses, unittest, existing `ContractParser` and `RuleEngine`.

---

### Task 1: Add Compatibility Regression Tests

**Files:**
- Modify: `tests/test_service.py`
- Modify: `tests/test_rules.py`
- Modify: `tests/test_report.py`
- Create: `tests/test_review_package_compatibility.py`

- [x] **Step 1: Update tests to import new review package paths**

Change local review tests to use:

```python
from contract_agent.review.service import review_text
from contract_agent.review.models import ReviewRequest, Severity
from contract_agent.review.rules import run_rules
from contract_agent.review.models import Finding, ReviewReport, Severity
from contract_agent.review.reporting import render_json, render_markdown
```

- [x] **Step 2: Add old-path compatibility test**

Create `tests/test_review_package_compatibility.py`:

```python
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
```

- [x] **Step 3: Run the focused compatibility test and verify it fails**

Run: `python -m unittest tests.test_review_package_compatibility -v`

Expected: FAIL or ERROR because `contract_agent.review` does not exist yet.

### Task 2: Create Review Package Implementation

**Files:**
- Create: `contract_agent/review/__init__.py`
- Create: `contract_agent/review/models.py`
- Create: `contract_agent/review/rules.py`
- Create: `contract_agent/review/reporting.py`
- Create: `contract_agent/review/service.py`
- Modify: `contract_agent/cli.py`

- [x] **Step 1: Move current root implementations into review package**

Copy current implementation content exactly into the matching new modules:

```text
contract_agent/models.py  -> contract_agent/review/models.py
contract_agent/rules.py   -> contract_agent/review/rules.py
contract_agent/report.py  -> contract_agent/review/reporting.py
contract_agent/service.py -> contract_agent/review/service.py
```

Then update imports inside new modules to point at `contract_agent.review.*` where they reference local review facade objects.

- [x] **Step 2: Add review package exports**

Create `contract_agent/review/__init__.py`:

```python
from contract_agent.review.models import Finding, ReviewReport, ReviewRequest, Severity
from contract_agent.review.reporting import render_json, render_markdown
from contract_agent.review.rules import normalize_contract_type, normalize_side, run_rules
from contract_agent.review.service import LLMEnricher, review_text

__all__ = [
    "Finding",
    "LLMEnricher",
    "ReviewReport",
    "ReviewRequest",
    "Severity",
    "normalize_contract_type",
    "normalize_side",
    "render_json",
    "render_markdown",
    "review_text",
    "run_rules",
]
```

- [x] **Step 3: Update CLI to use new package paths**

In `contract_agent/cli.py`, change imports to:

```python
from contract_agent.review.reporting import render_json, render_markdown
from contract_agent.review.service import review_text
```

- [x] **Step 4: Run focused tests and verify they pass**

Run: `python -m unittest tests.test_service tests.test_rules tests.test_report tests.test_review_package_compatibility tests.test_cli -v`

Expected: PASS.

### Task 3: Convert Root Modules to Compatibility Shims

**Files:**
- Modify: `contract_agent/models.py`
- Modify: `contract_agent/rules.py`
- Modify: `contract_agent/report.py`
- Modify: `contract_agent/service.py`

- [x] **Step 1: Replace root module bodies with re-exports**

Use these shim bodies:

```python
from contract_agent.review.models import Finding, ReviewReport, ReviewRequest, Severity

__all__ = ["Finding", "ReviewReport", "ReviewRequest", "Severity"]
```

```python
from contract_agent.review.rules import normalize_contract_type, normalize_side, run_rules

__all__ = ["normalize_contract_type", "normalize_side", "run_rules"]
```

```python
from contract_agent.review.reporting import render_json, render_markdown

__all__ = ["render_json", "render_markdown"]
```

```python
from contract_agent.review.service import LLMEnricher, review_text

__all__ = ["LLMEnricher", "review_text"]
```

- [x] **Step 2: Run all tests**

Run: `python -m unittest discover -s tests -v`

Expected: PASS.

### Task 4: Update Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`

- [x] **Step 1: Update layout documentation**

Add `contract_agent/review/` to the README layout and architecture runtime boundary sections as the local CLI rule-review facade.

- [x] **Step 2: Run final verification**

Run:

```powershell
python -m compileall -q contract_agent tests
python -m unittest discover -s tests -v
```

Expected: both commands exit with code 0.
