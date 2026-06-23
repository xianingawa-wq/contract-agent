import unittest

from contract_agent.logger.base import Error, Info, get_component_logger


class ComponentLoggerTests(unittest.TestCase):
    def test_component_logger_wraps_component_and_level(self):
        logger = get_component_logger("tests.logger.component", "Config")

        with self.assertLogs("tests.logger.component", level="INFO") as captured:
            logger.handle(Info("Loaded %s", "config.yaml"))

        self.assertIn("[Config][Info] Loaded config.yaml", captured.output[0])

    def test_component_logger_handles_error_event(self):
        logger = get_component_logger("tests.logger.component_error", "Config")

        with self.assertLogs("tests.logger.component_error", level="ERROR") as captured:
            logger.handle(Error("Failed %s", "config.yaml"))

        self.assertIn("[Config][Error] Failed config.yaml", captured.output[0])


if __name__ == "__main__":
    unittest.main()
