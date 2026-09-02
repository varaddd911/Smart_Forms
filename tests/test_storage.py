import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from audit import log_error, log_llm_usage
from conversation import ConversationState
from flow import process_turn
from models import IntakeRecord, PartialIntakeRecord
from storage import save_intake_record


class TestStorage(unittest.TestCase):
    def record(self):
        return IntakeRecord(
            query_type="inspection",
            regulation_ref="FDA_21CFR",
            product_area="oncology",
            urgency="urgent",
            submitting_team="CMC",
        )

    def test_storage_contains_only_safe_fields(self):
        with TemporaryDirectory() as tmp:
            path = save_intake_record(self.record(), turns_taken=3, output_dir=Path(tmp))
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(
            set(payload.keys()),
            {
                "query_type",
                "regulation_ref",
                "product_area",
                "urgency",
                "submitting_team",
                "timestamp",
                "turns_taken",
                "log_safe",
            },
        )
        self.assertTrue(payload["log_safe"])
        self.assertEqual(payload["turns_taken"], 3)
        self.assertNotIn("user_message", payload)
        self.assertNotIn("messages", payload)
        self.assertNotIn("prompt", payload)
        self.assertNotIn("deadline_days", payload)

    def test_raw_user_message_is_not_stored(self):
        secret = "SECRET_USER_MESSAGE_ONCOLOGY_PRODUCT_X"
        with TemporaryDirectory() as tmp:
            path = save_intake_record(self.record(), turns_taken=2, output_dir=Path(tmp))
            text = path.read_text(encoding="utf-8")

        self.assertNotIn(secret, text)
        self.assertNotIn("user", json.loads(text))

    def test_save_happens_only_after_confirmation(self):
        state = ConversationState()
        extracted = PartialIntakeRecord(
            query_type="inspection",
            regulation_ref="FDA_21CFR",
            product_area="oncology",
            submitting_team="CMC",
            deadline_days=1,
        )
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            with patch("flow.extract_turn", return_value=extracted):
                first = process_turn(state, "full regulatory query including deadline tomorrow")
            self.assertTrue(first.awaiting_confirmation)
            self.assertEqual(list(output_dir.glob("intake_*.json")), [])

            with patch(
                "flow.save_intake_record",
                side_effect=lambda record, turns: save_intake_record(record, turns, output_dir),
            ):
                second = process_turn(state, "yes")

            files = list(output_dir.glob("intake_*.json"))
            self.assertEqual(len(files), 1)
            payload = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertTrue(payload["log_safe"])
            self.assertEqual(payload["query_type"], "inspection")
            self.assertIsNotNone(second.saved_path)

    def test_debug_log_is_token_only_json(self):
        with TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "debug.json"
            log_llm_usage(120, 85, elapsed_ms=40, log_path=log_path)
            text = log_path.read_text(encoding="utf-8")
            payload = json.loads(text)

        self.assertEqual(payload["event"], "llm_call_completed")
        self.assertEqual(payload["input_tokens"], 120)
        self.assertEqual(payload["output_tokens"], 85)
        self.assertEqual(payload["elapsed_ms"], 40)
        self.assertTrue(payload["log_safe"])
        self.assertIn("timestamp", payload)
        self.assertNotIn("user_message", payload)
        self.assertNotIn("prompt", payload)
        self.assertNotIn("oncology", text)
        self.assertNotIn("User asked", text)
        self.assertNotIn("FDA", text)

    def test_error_log_is_json_and_log_safe(self):
        with TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "debug.json"
            log_error("APIError", 1, log_path=log_path)
            payload = json.loads(log_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["event"], "llm_error")
        self.assertEqual(payload["error_type"], "APIError")
        self.assertEqual(payload["attempt"], 1)
        self.assertTrue(payload["log_safe"])
        self.assertNotIn("user_message", payload)


if __name__ == "__main__":
    unittest.main()
