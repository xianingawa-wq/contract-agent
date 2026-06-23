from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.detectors.base import DetectorContext, DocumentDetector
from contract_agent.parser.detectors.clause_header import ClauseHeaderDetector
from contract_agent.parser.detectors.definition import DefinitionDetector
from contract_agent.parser.detectors.metadata import MetadataDetector
from contract_agent.parser.detectors.reference import ReferenceDetector
from contract_agent.parser.detectors.rules import BUILTIN_RULES, ParserRule
from contract_agent.parser.models import DetectorResult, ParsedDocument


ALLOWED_DETECTORS = {"metadata", "clause_header", "definition", "reference"}


class RuleMatch:
    def __init__(
        self, rule: ParserRule, groups: dict[str, str], keyword: str | None = None
    ) -> None:
        self.rule = rule
        self.groups = groups
        self.keyword = keyword

    def reason(self) -> str:
        values = {"rule_id": self.rule.rule_id, "keyword": self.keyword or "", **self.groups}
        try:
            return self.rule.reason_template.format(**values)
        except Exception:
            return f"命中 {self.rule.rule_id} 规则。"


class RuleRegistry:
    def __init__(self, rules: list[ParserRule]) -> None:
        self.warnings: list[str] = []
        self._rules = sorted(
            [rule for rule in rules if rule.enabled], key=lambda rule: rule.priority
        )

    @classmethod
    def builtin(cls) -> "RuleRegistry":
        return cls([rule.model_copy(deep=True) for rule in BUILTIN_RULES])

    @classmethod
    def from_config(cls, config: ParserConfig) -> "RuleRegistry":
        rules = [rule.model_copy(deep=True) for rule in BUILTIN_RULES]
        registry = cls(rules)
        if config.detector_rules_path:
            registry._merge_external_rules(Path(config.detector_rules_path))
        return registry

    def rules_for(self, detector_name: str, result_type: str | None = None) -> list[ParserRule]:
        rules = [rule for rule in self._rules if rule.detector_name == detector_name]
        if result_type is not None:
            rules = [rule for rule in rules if rule.metadata.get("result_type") == result_type]
        return rules

    def first_match(
        self, detector_name: str, text: str, result_type: str | None = None
    ) -> RuleMatch | None:
        for rule in self.rules_for(detector_name, result_type):
            match = self.match_rule(rule, text)
            if match is not None:
                return match
        return None

    def match_rule(self, rule: ParserRule, text: str) -> RuleMatch | None:
        for keyword in rule.keywords:
            if keyword and keyword in text:
                return RuleMatch(rule, {}, keyword=keyword)
        for pattern in rule.patterns:
            match = re.search(pattern, text)
            if match:
                return RuleMatch(
                    rule,
                    {key: value for key, value in match.groupdict().items() if value is not None},
                )
        if not rule.patterns and not rule.keywords:
            return RuleMatch(rule, {})
        return None

    def _merge_external_rules(self, path: Path) -> None:
        raw = _load_rule_file(path)
        raw_rules = raw.get("rules") if isinstance(raw, dict) else raw
        if not isinstance(raw_rules, list):
            raise ValueError("parser detector rules file must contain a rules list")
        external_rules = [ParserRule.model_validate(item) for item in raw_rules]
        seen_external: set[str] = set()
        by_id = {rule.rule_id: rule for rule in self._rules}
        for rule in external_rules:
            if rule.detector_name not in ALLOWED_DETECTORS:
                raise ValueError(f"unknown parser detector_name: {rule.detector_name}")
            if rule.rule_id in seen_external:
                raise ValueError(f"duplicate parser rule_id in external rules: {rule.rule_id}")
            seen_external.add(rule.rule_id)
            if rule.rule_id in by_id:
                self.warnings.append(f"external parser rule overrides {rule.rule_id}")
            by_id[rule.rule_id] = rule
        self._rules = sorted(
            [rule for rule in by_id.values() if rule.enabled], key=lambda rule: rule.priority
        )


class DetectorRegistry:
    def __init__(self, detectors: list[DocumentDetector], rule_registry: RuleRegistry) -> None:
        self._detectors = {detector.name: detector for detector in detectors}
        self.rule_registry = rule_registry

    @classmethod
    def default(cls, config: ParserConfig | None = None) -> "DetectorRegistry":
        parser_config = config or ParserConfig()
        return cls(
            [
                MetadataDetector(),
                ClauseHeaderDetector(),
                DefinitionDetector(),
                ReferenceDetector(),
            ],
            RuleRegistry.from_config(parser_config),
        )

    def detect(self, document: ParsedDocument, config: ParserConfig) -> list[DetectorResult]:
        context = DetectorContext(document=document, config=config, registry=self.rule_registry)
        results: list[DetectorResult] = []
        for detector_name in config.enabled_detectors:
            detector = self._detectors.get(detector_name)
            if detector is None:
                continue
            for result in detector.detect(context):
                if result.confidence >= config.min_detector_confidence:
                    results.append(result)
        return results


def _load_rule_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text) or {}
