from __future__ import annotations

from contract_agent.parser.detectors.base import DetectorContext
from contract_agent.parser.models import DetectorResult


class DefinitionDetector:
    name = "definition"

    def detect(self, context: DetectorContext) -> list[DetectorResult]:
        registry = context.registry
        results: list[DetectorResult] = []
        for block in context.document.blocks:
            for rule in registry.rules_for(self.name, "definition"):
                match = registry.match_rule(rule, block.text)
                if match is None:
                    continue
                results.append(
                    DetectorResult(
                        result_id=f"{self.name}-{len(results) + 1}",
                        detector_name=self.name,
                        rule_id=rule.rule_id,
                        result_type="definition",
                        value={
                            "term": (match.groups.get("term") or "").strip(),
                            "definition": (match.groups.get("definition") or block.text).strip(),
                        },
                        block_ids=[block.block_id],
                        span_ids=list(block.location.span_ids),
                        confidence=rule.confidence,
                        reason=match.reason() if context.config.store_detector_reasons else None,
                    )
                )
        return results
