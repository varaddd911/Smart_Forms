import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from conversation import ConversationState
from flow import is_user_confirmation, process_turn
from llm_service import ExtractionError, MAX_RETRIES, extract_turn
from models import PartialIntakeRecord
from prompts import OUT_OF_SCOPE_MESSAGE
from storage import save_intake_record


def partial(**overrides) -> PartialIntakeRecord:
    data = {
        "query_type": None,
        "regulation_ref": None,
        "product_area": None,
        "urgency": None,
        "submitting_team": None,
        "deadline_days": None,
        "out_of_scope": False,
    }
    data.update(overrides)
    return PartialIntakeRecord(**data)


class TestConfirmationPhrases(unittest.TestCase):
    def test_confirmation_phrases(self):
        self.assertTrue(is_user_confirmation("yes"))
        self.assertTrue(is_user_confirmation("confirm"))
        self.assertTrue(is_user_confirmation("looks good"))
        self.assertFalse(is_user_confirmation("yesterday"))
        self.assertFalse(is_user_confirmation("change team to PV"))


class TestMultiTurnFlow(unittest.TestCase):
    def test_partial_then_missing_field_question(self):
        state = ConversationState()
        with patch("flow.extract_turn", return_value=partial(query_type="safety_signal", product_area="oncology")):
            result = process_turn(state, "We have a safety issue with our oncology product.")

        self.assertEqual(state.query_type, "safety_signal")
        self.assertEqual(state.product_area, "oncology")
        self.assertIn("regulation_ref", state.missing_required_fields())
        self.assertEqual(result.next_field, "regulation_ref")
        self.assertIsNone(result.saved_path)
        self.assertFalse(result.awaiting_confirmation)

    def test_multi_turn_accumulation(self):
        state = ConversationState()
        with patch("flow.extract_turn", return_value=partial(query_type="safety_signal", product_area="oncology")):
            process_turn(state, "We have a safety issue with our oncology product.")

        with patch("flow.extract_turn", return_value=partial(regulation_ref="ICH_E2A", submitting_team="PV")):
            process_turn(state, "It is under ICH E2A and PV is handling it.")

        self.assertEqual(state.query_type, "safety_signal")
        self.assertEqual(state.regulation_ref, "ICH_E2A")
        self.assertEqual(state.product_area, "oncology")
        self.assertEqual(state.submitting_team, "PV")
        self.assertEqual(state.missing_required_fields(), ["urgency"])

    def test_none_does_not_erase_known_values(self):
        state = ConversationState()
        state.update_from(partial(query_type="inspection", regulation_ref="FDA_21CFR"))
        changed = state.update_from(partial(product_area="oncology"))
        self.assertEqual(state.query_type, "inspection")
        self.assertEqual(state.regulation_ref, "FDA_21CFR")
        self.assertEqual(changed, ["product_area"])

    def test_missing_field_detection(self):
        state = ConversationState()
        self.assertEqual(
            state.missing_required_fields(),
            ["query_type", "regulation_ref", "product_area", "urgency", "submitting_team"],
        )
        state.update_from(partial(query_type="inspection"))
        self.assertNotIn("query_type", state.missing_required_fields())


class TestHappyPathAndConfirmation(unittest.TestCase):
    def complete_extraction(self):
        return partial(
            query_type="inspection",
            regulation_ref="FDA_21CFR",
            product_area="oncology",
            submitting_team="CMC",
            deadline_days=1,
        )

    def test_happy_path_asks_for_confirmation_and_does_not_save(self):
        state = ConversationState()
        with patch("flow.extract_turn", return_value=self.complete_extraction()):
            with patch("flow.save_intake_record") as save:
                result = process_turn(
                    state,
                    "We received an FDA inspection issue related to manufacturing of our oncology product. "
                    "The regulator response is due tomorrow and CMC will handle it.",
                )

        save.assert_not_called()
        self.assertTrue(result.awaiting_confirmation)
        self.assertIn("Please confirm", result.confirmation_message)
        self.assertIn("FDA_21CFR", result.confirmation_message)
        self.assertEqual(state.urgency, "urgent")
        self.assertTrue(state.awaiting_confirmation)
        self.assertIsNone(result.saved_path)

    def test_confirmation_saves(self):
        state = ConversationState()
        with patch("flow.extract_turn", return_value=self.complete_extraction()):
            process_turn(state, "complete query")

        with TemporaryDirectory() as tmp:
            with patch("flow.save_intake_record", side_effect=lambda record, turns: save_intake_record(record, turns, Path(tmp))) as save:
                result = process_turn(state, "yes")

        self.assertIsNotNone(result.saved_path)
        self.assertEqual(result.saved_record.query_type, "inspection")
        self.assertEqual(result.saved_record.urgency, "urgent")
        self.assertFalse(state.awaiting_confirmation)
        self.assertIsNone(state.pending_record)
        save.assert_called_once()

    def test_correction_before_save_reconfirms(self):
        state = ConversationState()
        with patch("flow.extract_turn", return_value=self.complete_extraction()):
            process_turn(state, "complete query")

        with patch("flow.extract_turn", return_value=partial(submitting_team="PV")):
            with patch("flow.save_intake_record") as save:
                result = process_turn(state, "PV will handle it instead")

        save.assert_not_called()
        self.assertTrue(result.awaiting_confirmation)
        self.assertEqual(state.submitting_team, "PV")
        self.assertEqual(state.query_type, "inspection")
        self.assertIn("PV", result.confirmation_message)

        with TemporaryDirectory() as tmp:
            with patch(
                "flow.save_intake_record",
                side_effect=lambda record, turns: save_intake_record(record, turns, Path(tmp)),
            ):
                result = process_turn(state, "looks good")

        self.assertEqual(result.saved_record.submitting_team, "PV")
        self.assertIsNotNone(result.saved_path)


class TestOutOfScopeAndFallback(unittest.TestCase):
    def test_out_of_scope_does_not_fill_schema(self):
        state = ConversationState()
        with patch("flow.extract_turn", return_value=partial(out_of_scope=True)):
            result = process_turn(state, "What is the weather today?")

        self.assertTrue(result.out_of_scope)
        self.assertEqual(result.fallback_message, OUT_OF_SCOPE_MESSAGE)
        self.assertEqual(state.missing_required_fields()[0], "query_type")
        self.assertIsNone(result.saved_path)
        self.assertFalse(result.awaiting_confirmation)

    def test_extraction_failure_does_not_crash(self):
        state = ConversationState()
        with patch("flow.extract_turn", side_effect=ExtractionError("extraction failed after retries")):
            result = process_turn(state, "unclear text")

        self.assertIn("could not read that", result.error)
        self.assertEqual(result.next_field, "query_type")
        self.assertIsNone(result.saved_path)


class TestRetryBehavior(unittest.TestCase):
    def test_retry_is_limited(self):
        failures = ExtractionError("boom")
        with patch("llm_service._extract_once", side_effect=failures) as mocked:
            with patch("llm_service.log_error"):
                with self.assertRaises(ExtractionError) as ctx:
                    extract_turn("any message")

        self.assertEqual(mocked.call_count, 1 + MAX_RETRIES)
        self.assertIn("after retries", str(ctx.exception))

    def test_retry_then_success(self):
        ok = partial(query_type="complaint")
        with patch(
            "llm_service._extract_once",
            side_effect=[ExtractionError("once"), ExtractionError("twice"), ok],
        ) as mocked:
            with patch("llm_service.log_error"):
                result = extract_turn("product complaint")

        self.assertEqual(mocked.call_count, 3)
        self.assertEqual(result.query_type, "complaint")


class TestCapstoneExamples(unittest.TestCase):
    def test_appendix_inspection_example_maps_deadline(self):
        extracted = PartialIntakeRecord(
            query_type="inspection",
            regulation_ref="FDA_21CFR",
            product_area="cmc",
            submitting_team="CMC",
            deadline_days=10,
        )
        self.assertEqual(extracted.urgency, "standard")

        state = ConversationState()
        with patch("flow.extract_turn", return_value=extracted):
            result = process_turn(
                state,
                "We received an FDA inspection observation related to our manufacturing process. "
                "The response is due in 10 days. CMC will handle it.",
            )

        self.assertTrue(result.awaiting_confirmation)
        self.assertEqual(state.product_area, "cmc")
        self.assertEqual(state.submitting_team, "CMC")

    def test_unknown_framework_leaves_regulation_missing(self):
        state = ConversationState()
        with patch(
            "flow.extract_turn",
            return_value=partial(
                query_type="safety_signal",
                product_area="clinical",
                submitting_team="Clinical",
            ),
        ):
            result = process_turn(
                state,
                "We have a safety concern in a clinical trial but I'm not sure which "
                "regulatory framework applies. The Clinical team is handling it.",
            )

        self.assertIsNone(state.regulation_ref)
        self.assertEqual(result.next_field, "regulation_ref")


if __name__ == "__main__":
    unittest.main()
