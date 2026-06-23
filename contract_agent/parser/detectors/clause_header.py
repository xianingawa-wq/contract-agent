from __future__ import annotations

from contract_agent.parser.detectors.base import DetectorContext
from contract_agent.parser.models import DetectorResult, DocumentSpan


class ClauseHeaderDetector:
    name = "clause_header"

    def detect(self, context: DetectorContext) -> list[DetectorResult]:
        registry = context.registry
        results: list[DetectorResult] = []
        for item in _iter_text_items(context.document):
            for rule in registry.rules_for(self.name, "clause_header"):
                match = registry.match_rule(rule, item["text"])
                if match is None:
                    continue
                clause_no = (match.groups.get("clause_no") or "").strip()
                title = (match.groups.get("title") or clause_no).strip()
                results.append(
                    DetectorResult(
                        result_id=f"{self.name}-{len(results) + 1}",
                        detector_name=self.name,
                        rule_id=rule.rule_id,
                        result_type="clause_header",
                        value={
                            "clause_no": clause_no,
                            "title": title,
                            "level": rule.metadata.get("level"),
                            "level_num": rule.metadata.get("level_num"),
                            "parent_hint": None,
                        },
                        block_ids=item["block_ids"],
                        span_ids=item["span_ids"],
                        confidence=rule.confidence,
                        reason=match.reason() if context.config.store_detector_reasons else None,
                    )
                )
                break
        return results


def _iter_text_items(document):
    if document.blocks:
        for block in document.blocks:
            yield {
                "text": block.text,
                "block_ids": [block.block_id],
                "span_ids": list(block.location.span_ids),
            }
        return
    for span in document.spans:
        assert isinstance(span, DocumentSpan)
        yield {"text": span.text, "block_ids": [], "span_ids": [span.span_id]}
