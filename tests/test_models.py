import unittest

from pydantic import ValidationError

from models import (
    IntakeRecord,
    PartialIntakeRecord,
    match_query_type,
    match_regulation_ref,
    match_product_area,
    normalize_submitting_team,
    urgency_from_deadline_days,
)


class TestIntakeRecord(unittest.TestCase):
    def valid_payload(self, **overrides):
        data = {
            "query_type": "inspection",
            "regulation_ref": "FDA_21CFR",
            "product_area": "oncology",
            "urgency": "urgent",
            "submitting_team": "CMC",
        }
        data.update(overrides)
        return data

    def test_valid_final_record(self):
        record = IntakeRecord(**self.valid_payload())
        self.assertEqual(record.query_type, "inspection")
        self.assertEqual(record.regulation_ref, "FDA_21CFR")
        self.assertEqual(record.product_area, "oncology")
        self.assertEqual(record.urgency, "urgent")
        self.assertEqual(record.submitting_team, "CMC")

    def test_invalid_query_type_rejected(self):
        with self.assertRaises(ValidationError):
            IntakeRecord(**self.valid_payload(query_type="not_a_type"))

    def test_invalid_regulation_ref_rejected(self):
        with self.assertRaises(ValidationError):
            IntakeRecord(**self.valid_payload(regulation_ref="MHRA"))

    def test_invalid_product_area_rejected(self):
        with self.assertRaises(ValidationError):
            IntakeRecord(**self.valid_payload(product_area="packaging"))

    def test_invalid_urgency_rejected(self):
        with self.assertRaises(ValidationError):
            IntakeRecord(**self.valid_payload(urgency="asap"))

    def test_empty_submitting_team_rejected(self):
        with self.assertRaises(ValidationError):
            IntakeRecord(**self.valid_payload(submitting_team=""))

    def test_person_name_rejected_as_team(self):
        with self.assertRaises(ValidationError):
            IntakeRecord(**self.valid_payload(submitting_team="John"))
        with self.assertRaises(ValidationError):
            IntakeRecord(**self.valid_payload(submitting_team="John Smith"))

    def test_known_teams_normalised(self):
        self.assertEqual(IntakeRecord(**self.valid_payload(submitting_team="pv")).submitting_team, "PV")
        self.assertEqual(
            IntakeRecord(**self.valid_payload(submitting_team="clinical")).submitting_team,
            "Clinical",
        )
        self.assertEqual(
            IntakeRecord(**self.valid_payload(submitting_team="labelling")).submitting_team,
            "Labelling",
        )


class TestMatching(unittest.TestCase):
    def test_mhra_maps_to_other(self):
        self.assertEqual(match_regulation_ref("MHRA"), "other")
        self.assertEqual(PartialIntakeRecord(regulation_ref="MHRA").regulation_ref, "other")

    def test_unknown_regulation_not_hallucinated_when_junk(self):
        self.assertIsNone(match_regulation_ref("asdf"))
        self.assertIsNone(PartialIntakeRecord(regulation_ref="asdf").regulation_ref)

    def test_invalid_query_type_becomes_none_on_partial(self):
        self.assertIsNone(match_query_type("not_a_type"))
        self.assertIsNone(PartialIntakeRecord(query_type="not_a_type").query_type)

    def test_invalid_product_area_becomes_none_on_partial(self):
        self.assertIsNone(match_product_area("packaging"))
        self.assertIsNone(PartialIntakeRecord(product_area="packaging").product_area)

    def test_person_name_helper(self):
        self.assertIsNone(normalize_submitting_team("John"))
        self.assertIsNone(normalize_submitting_team("John Smith"))
        self.assertEqual(normalize_submitting_team("PV"), "PV")
        self.assertEqual(normalize_submitting_team("Quality team"), "Quality Team")


class TestDeadlineUrgency(unittest.TestCase):
    def test_deadline_mapping(self):
        self.assertEqual(urgency_from_deadline_days(0), "critical")
        self.assertEqual(urgency_from_deadline_days(-1), "critical")
        self.assertEqual(urgency_from_deadline_days(1), "urgent")
        self.assertEqual(urgency_from_deadline_days(7), "urgent")
        self.assertEqual(urgency_from_deadline_days(10), "standard")
        self.assertEqual(urgency_from_deadline_days(30), "standard")
        self.assertEqual(urgency_from_deadline_days(45), "routine")

    def test_tone_does_not_set_urgency(self):
        partial = PartialIntakeRecord(urgency="urgent")
        self.assertIsNone(partial.urgency)
        self.assertIsNone(partial.deadline_days)

    def test_deadline_sets_urgency_on_partial(self):
        partial = PartialIntakeRecord(deadline_days=1)
        self.assertEqual(partial.urgency, "urgent")
        ten_days = PartialIntakeRecord(deadline_days=10)
        self.assertEqual(ten_days.urgency, "standard")


class TestPartialExtraction(unittest.TestCase):
    def test_partial_extraction_keeps_missing_fields_none(self):
        partial = PartialIntakeRecord(
            query_type="safety_signal",
            product_area="oncology",
        )
        self.assertEqual(partial.query_type, "safety_signal")
        self.assertEqual(partial.product_area, "oncology")
        self.assertIsNone(partial.regulation_ref)
        self.assertIsNone(partial.urgency)
        self.assertIsNone(partial.submitting_team)


if __name__ == "__main__":
    unittest.main()
