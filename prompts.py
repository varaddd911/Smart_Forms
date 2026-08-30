from datetime import date

from models import LEAVE_TYPES

FIELD_LABELS = {
    "employee_name": "Employee name",
    "employee_id": "Employee ID",
    "leave_type": "Leave type",
    "start_date": "Start date",
    "end_date": "End date",
    "reason": "Reason",
}

QUESTIONS = {
    "employee_name": "What is your name?",
    "employee_id": "What is your employee ID?",
    "leave_type": f"What type of leave is this ({', '.join(LEAVE_TYPES)})?",
    "start_date": "Which date does the leave start?",
    "end_date": "Which date does the leave end?",
    "reason": "What is the reason for the leave?",
}


def get_smart_form_prompt(known=None, awaiting=None) -> str:
    today = date.today()

    prompt = f"""
You are a Smart Form assistant collecting an employee leave request across
several turns of conversation.

Today's date is {today.strftime("%Y-%m-%d")}.

Read the user's latest message and return the leave-request details it contains.

Rules:
1. Return null for every field the latest message does not mention.
2. Never invent information. Extract only what the user states.
3. Dates must be returned in YYYY-MM-DD format.
4. If a date has no year, choose the reading closest to today's date.
   Never return a year in the past.
5. If the user changes a value that is already recorded, return the new value.
6. The user may answer with a bare value such as "E1024" or "next Monday".
   Read it as the answer to the question that was just asked.
7. Leave type must be exactly one of: {", ".join(LEAVE_TYPES)}.
8. Return null when an answer is not a plausible value for the field, even if it
   was given in reply to a direct question. A stray character such as "w" or "asdf"
   is not an answer. Never force an unclear reply into a field.
"""

    filled = {
        field: value
        for field, value in (known or {}).items()
        if value is not None
    }

    if filled:
        recorded = "\n".join(
            f"- {FIELD_LABELS[field]}: {value}"
            for field, value in filled.items()
        )
        prompt += f"\nAlready recorded:\n{recorded}\n"

    if awaiting:
        prompt += f"\nThe question just asked was: {FIELD_LABELS[awaiting]}\n"

    return prompt
