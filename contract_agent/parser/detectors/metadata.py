from __future__ import annotations

from contract_agent.parser.detectors.base import DetectorContext
from contract_agent.parser.models import DetectorResult


class MetadataDetector:
    name = "metadata"

    def detect(self, context: DetectorContext) -> list[DetectorResult]:
        registry = context.registry
        document = context.document
        results: list[DetectorResult] = []
        blocks = document.blocks

        title_rule = registry.rules_for(self.name, "metadata.title")[0]
        first_block = next((block for block in blocks if block.text.strip()), None)
        if first_block is not None:
            results.append(
                DetectorResult(
                    result_id=self._result_id(results),
                    detector_name=self.name,
                    rule_id=title_rule.rule_id,
                    result_type="metadata.title",
                    value={"title": first_block.text.strip()[:100]},
                    block_ids=[first_block.block_id],
                    span_ids=list(first_block.location.span_ids),
                    confidence=title_rule.confidence,
                    reason=self._reason(
                        context, title_rule.reason_template.format(rule_id=title_rule.rule_id)
                    ),
                )
            )

        for rule in registry.rules_for(self.name, "metadata.contract_type_hint"):
            match = registry.match_rule(rule, document.raw_text)
            if match is None:
                continue
            results.append(
                DetectorResult(
                    result_id=self._result_id(results),
                    detector_name=self.name,
                    rule_id=rule.rule_id,
                    result_type="metadata.contract_type_hint",
                    value={"contract_type_hint": rule.metadata.get("contract_type_hint")},
                    confidence=rule.confidence,
                    reason=self._reason(context, match.reason()),
                )
            )
            break

        for block in blocks:
            for rule in registry.rules_for(self.name, "metadata.party"):
                match = registry.match_rule(rule, block.text)
                if match is None:
                    continue
                results.append(
                    DetectorResult(
                        result_id=self._result_id(results),
                        detector_name=self.name,
                        rule_id=rule.rule_id,
                        result_type="metadata.party",
                        value={
                            "role": match.groups.get("role"),
                            "party": (match.groups.get("party") or "").strip(),
                        },
                        block_ids=[block.block_id],
                        span_ids=list(block.location.span_ids),
                        confidence=rule.confidence,
                        reason=self._reason(context, match.reason()),
                    )
                )

            for rule in registry.rules_for(self.name, "metadata.signed_date"):
                match = registry.match_rule(rule, block.text)
                if match is None:
                    continue
                results.append(
                    DetectorResult(
                        result_id=self._result_id(results),
                        detector_name=self.name,
                        rule_id=rule.rule_id,
                        result_type="metadata.signed_date",
                        value={"signed_date": match.groups.get("signed_date")},
                        block_ids=[block.block_id],
                        span_ids=list(block.location.span_ids),
                        confidence=rule.confidence,
                        reason=self._reason(context, match.reason()),
                    )
                )

        return results

    def _result_id(self, results: list[DetectorResult]) -> str:
        return f"{self.name}-{len(results) + 1}"

    def _reason(self, context: DetectorContext, reason: str) -> str | None:
        return reason if context.config.store_detector_reasons else None
