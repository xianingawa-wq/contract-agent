import unittest

from contract_agent.orchestration.gateway import GatewayRouter
from contract_agent.orchestration.protocol import AgentMode, PipelineStatus


class GatewayRouterTests(unittest.TestCase):
    def test_routes_explicit_review_keywords_to_review_team(self):
        router = GatewayRouter()

        response = router.route("请全面审查这份合同", contract_clause_count=10)

        self.assertEqual(response.team, "review")
        self.assertEqual(response.mode, AgentMode.MULTI_MANUAL)
        self.assertTrue(response.request_id)

    def test_explicit_mode_overrides_detected_complexity(self):
        router = GatewayRouter()

        response = router.route(
            "简单看看这份合同",
            explicit_mode=AgentMode.MULTI_MANUAL,
            contract_clause_count=1,
        )

        self.assertEqual(response.mode, AgentMode.MULTI_MANUAL)

    def test_create_pipeline_state_and_started_event_are_consistent(self):
        router = GatewayRouter()
        response = router.route("帮我查一下合同问题", contract_id="contract-1")

        state = router.create_pipeline_state(response, contract_id="contract-1")
        event = router.create_pipeline_started_event(state)

        self.assertEqual(state.contract_id, "contract-1")
        self.assertEqual(state.status, PipelineStatus.PENDING)
        self.assertEqual(event.pipeline_id, state.pipeline_id)
        self.assertEqual(event.data["mode"], state.mode.value)
        self.assertEqual(event.data["team"], state.team)


if __name__ == "__main__":
    unittest.main()
