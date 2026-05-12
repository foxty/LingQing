import pytest
import logging
from apps.shared.utils.logger import get_logger


class TestLogger:
    def test_basic_logger(self, caplog):
        caplog.set_level(logging.DEBUG)
        logger = get_logger(__name__)
        logger.debug("This is a DEBUG message")
        logger.info("This is an INFO message")
        logger.warning("This is a WARNING message")
        logger.error("This is an ERROR message")
        assert "DEBUG" in caplog.text
        assert "INFO" in caplog.text
        assert "WARNING" in caplog.text
        assert "ERROR" in caplog.text

    def test_different_modules(self, caplog):
        caplog.set_level(logging.DEBUG)
        agent_logger = get_logger("apps.agents.test_agent")
        agent_logger.info("Agent logger initialized")
        agent_logger.debug("Agent processing data")
        api_logger = get_logger("apps.api.test_endpoint")
        api_logger.info("API logger initialized")
        api_logger.debug("Handling request")
        ui_logger = get_logger("apps.agent_ui.test_component")
        ui_logger.info("Agent UI logger initialized")
        ui_logger.debug("Rendering component")
        assert "Agent logger initialized" in caplog.text
        assert "Agent processing data" in caplog.text
        assert "API logger initialized" in caplog.text
        assert "Handling request" in caplog.text
        assert "Agent UI logger initialized" in caplog.text
        assert "Rendering component" in caplog.text

    def test_error_logging(self, caplog):
        logger = get_logger(__name__)
        try:
            _ = 1 / 0
        except Exception as e:
            logger.error(f"Caught exception: {e}", exc_info=True)
        assert "Caught exception" in caplog.text
        assert "ZeroDivisionError" in caplog.text
