"""Unit tests for the logger."""

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tmux_dashboard import logger as logger_module
from tmux_dashboard.logger import Logger


class TestLogger(unittest.TestCase):
    def setUp(self) -> None:
        logger_module._WARNED_WRITE_FAILURE = False

    def test_write_handles_oserror(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "log.jsonl"
            logger = Logger(log_path)

            stderr_capture = io.StringIO()
            with patch("pathlib.Path.open", side_effect=OSError("nope")), patch("sys.stderr", stderr_capture):
                logger.info("event", "message")

            output = stderr_capture.getvalue()
            self.assertIn("failed to write log", output)

    def test_write_warns_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "log.jsonl"
            logger = Logger(log_path)

            stderr_capture = io.StringIO()
            with patch("pathlib.Path.open", side_effect=OSError("nope")), patch("sys.stderr", stderr_capture):
                logger.info("event1", "message")
                logger.info("event2", "message")

            output = stderr_capture.getvalue().strip().splitlines()
            self.assertEqual(len(output), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
