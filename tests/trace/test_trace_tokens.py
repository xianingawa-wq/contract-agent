import unittest


class TraceTokenTests(unittest.TestCase):
    def test_token_trace_summarizes_estimated_input_and_output_tokens(self):
        from contract_agent.trace.tokens import TokenTrace, estimate_tokens

        trace = TokenTrace()
        trace.add_input("contract", "a" * 120)
        trace.add_output("answer", "b" * 60)
        summary = trace.summary()

        self.assertEqual(estimate_tokens("a" * 120), 30)
        self.assertEqual(summary.estimated_input_tokens, 30)
        self.assertEqual(summary.estimated_output_tokens, 15)
        self.assertEqual(summary.estimated_total_tokens, 45)
        self.assertEqual(summary.records[0].label, "contract")

    def test_token_trace_summary_records_are_snapshots(self):
        from contract_agent.trace.tokens import TokenTrace

        trace = TokenTrace()
        trace.add_input("contract", "abcd")

        summary = trace.summary()
        summary.records[0].estimated_tokens = 999

        self.assertEqual(trace.summary().estimated_total_tokens, 1)


if __name__ == "__main__":
    unittest.main()
