from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class ParserRule(BaseModel):
    rule_id: str
    detector_name: str
    locale: str = "zh-CN"
    enabled: bool = True
    priority: int = 100
    patterns: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    confidence: float = 0.75
    reason_template: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("rule_id", "detector_name", "reason_template")
    @classmethod
    def _required_strings_must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("ParserRule string fields must not be blank")
        return value


BUILTIN_RULES: list[ParserRule] = [
    ParserRule(
        rule_id="metadata.title.first_block.v1",
        detector_name="metadata",
        priority=10,
        confidence=0.95,
        reason_template="命中 {rule_id} 规则，使用首个非空块作为标题。",
        metadata={"result_type": "metadata.title"},
    ),
    ParserRule(
        rule_id="metadata.contract_type.purchase.v1",
        detector_name="metadata",
        priority=20,
        keywords=["采购"],
        confidence=0.78,
        reason_template="命中 {rule_id} 规则，关键词={keyword}。",
        metadata={
            "result_type": "metadata.contract_type_hint",
            "contract_type_hint": "采购合同",
        },
    ),
    ParserRule(
        rule_id="metadata.contract_type.confidentiality.v1",
        detector_name="metadata",
        priority=21,
        keywords=["保密"],
        confidence=0.78,
        reason_template="命中 {rule_id} 规则，关键词={keyword}。",
        metadata={
            "result_type": "metadata.contract_type_hint",
            "contract_type_hint": "保密协议",
        },
    ),
    ParserRule(
        rule_id="metadata.contract_type.service.v1",
        detector_name="metadata",
        priority=22,
        keywords=["服务"],
        confidence=0.75,
        reason_template="命中 {rule_id} 规则，关键词={keyword}。",
        metadata={
            "result_type": "metadata.contract_type_hint",
            "contract_type_hint": "服务合同",
        },
    ),
    ParserRule(
        rule_id="metadata.party.label.zh.v1",
        detector_name="metadata",
        priority=30,
        patterns=[r"(?P<role>甲方|乙方)[:：]\s*(?P<party>[^\n。；;]+)"],
        confidence=0.88,
        reason_template="命中 {rule_id} 规则，角色={role}。",
        metadata={"result_type": "metadata.party"},
    ),
    ParserRule(
        rule_id="metadata.signed_date.zh.v1",
        detector_name="metadata",
        priority=40,
        patterns=[r"(?P<signed_date>\d{4}年\d{1,2}月\d{1,2}日)"],
        confidence=0.82,
        reason_template="命中 {rule_id} 规则，日期={signed_date}。",
        metadata={"result_type": "metadata.signed_date"},
    ),
    ParserRule(
        rule_id="clause.header.zh.article.v1",
        detector_name="clause_header",
        priority=10,
        patterns=[r"^(?P<clause_no>第[一二三四五六七八九十百零〇\d]+条)\s*(?P<title>.*)$"],
        confidence=0.90,
        reason_template="命中 {rule_id} 规则，条款号={clause_no}。",
        metadata={"result_type": "clause_header", "level": "clause", "level_num": 1},
    ),
    ParserRule(
        rule_id="clause.header.numeric.hierarchy.v1",
        detector_name="clause_header",
        priority=20,
        patterns=[r"^(?P<clause_no>\d+\.\d+(?:\.\d+)*)\s+(?P<title>.*)$"],
        confidence=0.86,
        reason_template="命中 {rule_id} 规则，层级编号={clause_no}。",
        metadata={"result_type": "clause_header", "level": "sub_clause", "level_num": 2},
    ),
    ParserRule(
        rule_id="clause.header.zh.parenthesized.v1",
        detector_name="clause_header",
        priority=30,
        patterns=[r"^(?P<clause_no>（[一二三四五六七八九十百零〇\d]+）)\s*(?P<title>.*)$"],
        confidence=0.84,
        reason_template="命中 {rule_id} 规则，小项={clause_no}。",
        metadata={"result_type": "clause_header", "level": "sub_item", "level_num": 3},
    ),
    ParserRule(
        rule_id="clause.header.numeric.item.v1",
        detector_name="clause_header",
        priority=40,
        patterns=[r"^(?P<clause_no>\d+\.)\s*(?P<title>.*)$"],
        confidence=0.80,
        reason_template="命中 {rule_id} 规则，小项={clause_no}。",
        metadata={"result_type": "clause_header", "level": "sub_item", "level_num": 3},
    ),
    ParserRule(
        rule_id="definition.term.zh.v1",
        detector_name="definition",
        priority=10,
        patterns=[
            r"本合同所称(?P<term>[^，,。]+)[，,]?(?:是指|指)(?P<definition>[^。]+)",
            r"(?P<definition>[^，,。]+)[，,]?(?:以下简称|简称)[“\"]?(?P<term>[^”\"。]+)[”\"]?",
        ],
        confidence=0.76,
        reason_template="命中 {rule_id} 规则，术语={term}。",
        metadata={"result_type": "definition"},
    ),
    ParserRule(
        rule_id="reference.clause_or_attachment.zh.v1",
        detector_name="reference",
        priority=10,
        patterns=[
            r"(?P<target>第[一二三四五六七八九十百零〇\d]+条|附件[一二三四五六七八九十百零〇\d]+)"
        ],
        confidence=0.72,
        reason_template="命中 {rule_id} 规则，引用={target}。",
        metadata={"result_type": "reference"},
    ),
]
