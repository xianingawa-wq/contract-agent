import unittest

from contract_agent.config import Settings
from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser import ContractParser
from contract_agent.services.review_service import ReviewService
from contract_agent.services.rule_engine import RuleEngine


def _builtin_parser() -> ContractParser:
    return ContractParser(
        parser_config=ParserConfig(
            default_converter="builtin",
            enabled_converters=["builtin"],
            fallback_order=["builtin"],
        )
    )


class ReviewContractTypeTests(unittest.TestCase):
    def test_rule_engine_accepts_purchase_alias_for_procurement_rules(self):
        document = _builtin_parser().parse_text(
            "第一条 付款\n甲方应于合同签订后5日内支付100%合同价款。\n"
            "甲方：A\n乙方：B\n合同总价100元\n违约责任：按损失赔偿。"
        )

        rule_ids = [risk.rule_id for risk in RuleEngine().check("purchase", document)]

        self.assertIn("PAY_001", rule_ids)
        self.assertIn("ACC_001", rule_ids)

    def test_review_service_reports_normalized_contract_type_for_alias(self):
        class FakeRetriever:
            queries = []

            def retrieve_documents_with_rerank(self, **kwargs):
                self.queries.append(kwargs["query"])
                return []

        class FakeLlmReviewer:
            contract_types = []

            def enrich_risk(self, risk, contract_type, clause_text, retrieved_contexts):
                self.contract_types.append(contract_type)
                return None

        service = ReviewService(
            runtime_settings=Settings(chat_api_key="chat-key"),
            parser_config=ParserConfig(
                default_converter="builtin",
                enabled_converters=["builtin"],
                fallback_order=["builtin"],
            ),
        )
        service._knowledge_retriever = FakeRetriever()
        service._llm_reviewer = FakeLlmReviewer()
        document = service.parser.parse_text(
            "第一条 付款\n甲方应于合同签订后5日内支付100%合同价款。\n"
            "甲方：A\n乙方：B\n合同总价100元\n违约责任：按损失赔偿。"
        )

        response = service.review_document(document, "purchase", "甲方")

        self.assertEqual(response.summary.contract_type, "采购合同")
        self.assertIn("ACC_001", [risk.rule_id for risk in response.risks])
        self.assertTrue(FakeRetriever.queries)
        self.assertTrue(all("采购合同" in query for query in FakeRetriever.queries))
        self.assertEqual(set(FakeLlmReviewer.contract_types), {"采购合同"})
