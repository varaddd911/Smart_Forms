from typing import Optional
from datetime import date

from models import FIELD_ORDER, REQUIRED_FIELDS, LeaveRequest, PartialLeaveRequest


class ConversationState:
    def __init__(self):
        self.employee_name: Optional[str] = None
        self.employee_id: Optional[str] = None
        self.leave_type: Optional[str] = None
        self.start_date: Optional[date] = None
        self.end_date: Optional[date] = None
        self.reason: Optional[str] = None

    def get_state(self):
        return {field: getattr(self, field) for field in FIELD_ORDER}

    def update_from(self, partial: PartialLeaveRequest) -> list[str]:
        """Apply one turn's extraction, ignoring fields the turn left empty.

        Skipping None is what makes the conversation cumulative: a turn that only
        mentions the leave type must not erase the name captured earlier.
        """
        changed = []

        for field, value in partial.model_dump().items():
            if value is None or value == getattr(self, field):
                continue

            setattr(self, field, value)
            changed.append(field)

        return changed

    def missing_required_fields(self):
        return [
            field
            for field in REQUIRED_FIELDS
            if getattr(self, field) is None
        ]

    def is_complete(self) -> bool:
        return not self.missing_required_fields()

    def to_leave_request(self) -> LeaveRequest:
        return LeaveRequest.model_validate(self.get_state())

    def clear(self, *fields: str) -> None:
        for field in fields:
            setattr(self, field, None)
