import unittest

from contract_agent.runtime.config import Settings, temporary_settings
from contract_agent.services.chat_service import ChatService
from contract_agent.services.review_service import ReviewService


class ServiceConfigInjectionTests(unittest.TestCase):
    def test_chat_service_uses_constructor_settings_for_missing_key_guard(self):
        service = ChatService(
            runtime_settings=Settings(chat_api_key=None, react_max_steps=7),
            review_service=object(),
        )

        with temporary_settings(chat_api_key="global-key", react_max_steps=1):
            self.assertEqual(service.settings.react_max_steps, 7)
            with self.assertRaisesRegex(RuntimeError, "CHAT_API_KEY"):
                service._require_llm()

    def test_review_service_uses_constructor_settings_for_health(self):
        service = ReviewService(runtime_settings=Settings(chat_api_key="injected-key", vector_backend="faiss"))

        with temporary_settings(chat_api_key=None, vector_backend="milvus"):
            health = service.health()

        self.assertIsInstance(health.llm_configured, bool)
        self.assertEqual(service.settings.chat_api_key, "injected-key")


if __name__ == "__main__":
    unittest.main()
