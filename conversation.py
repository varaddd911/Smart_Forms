"""Conversation memory: keep the five fields across turns."""

from typing import Optional

from models import FIELDS, IntakeRecord, PartialIntakeRecord, resolve_urgency


class ConversationState:
    def __init__(self):
        self.query_type = None
        self.regulation_ref = None
        self.product_area = None
        self.urgency = None
        self.submitting_team = None
        self.deadline_days = None
        self.is_expedited_safety = False
        self.is_form_483 = False
        self.turns_taken = 0
        self.awaiting_confirmation = False
        self.pending_record: Optional[IntakeRecord] = None

    def get_state(self) -> dict:
        return {name: getattr(self, name) for name in FIELDS}

    def update_from(self, partial: PartialIntakeRecord) -> list[str]:
        """Copy non-None values. None means 'not mentioned this turn'."""
        changed = []
        data = partial.model_dump()
        for name in FIELDS + ["deadline_days"]:
            value = data.get(name)
            if value is None or value == getattr(self, name):
                continue
            setattr(self, name, value)
            if name in FIELDS:
                changed.append(name)

        if data.get("is_expedited_safety"):
            self.is_expedited_safety = True
        if data.get("is_form_483"):
            self.is_form_483 = True

        computed = resolve_urgency(
            deadline_days=self.deadline_days,
            is_expedited_safety=self.is_expedited_safety,
            is_form_483=self.is_form_483,
        )
        if computed != self.urgency:
            self.urgency = computed
            if "urgency" not in changed:
                changed.append("urgency")

        return [name for name in changed if name in FIELDS]

    def missing_required_fields(self) -> list[str]:
        return [name for name in FIELDS if getattr(self, name) is None]

    def to_intake_record(self) -> IntakeRecord:
        return IntakeRecord.model_validate(self.get_state())

    def reset(self) -> None:
        self.__init__()
