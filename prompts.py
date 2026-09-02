"""Prompt, labels, and follow-up questions."""

from models import PRODUCT_AREAS, QUERY_TYPES, REGULATION_REFS

FIELD_LABELS = {
    "query_type": "Query type",
    "regulation_ref": "Regulation reference",
    "product_area": "Product area",
    "urgency": "Urgency",
    "submitting_team": "Submitting team",
}

QUESTIONS = {
    "query_type": (
        "Is this a complaint, submission, variation, safety signal, "
        "label update, inspection, or general enquiry?"
    ),
    "regulation_ref": "Which regulatory framework applies, if known?",
    "product_area": (
        "Which product area is this: oncology, cardiovascular, "
        "infectious disease, CMC, clinical, labelling, or general?"
    ),
    "urgency": "What is the actual regulatory deadline or required response date?",
    "submitting_team": (
        "Which team is submitting this: PV, CMC, Clinical, Labelling, Submissions, or another team?"
    ),
}

OUT_OF_SCOPE_MESSAGE = (
    "SmartIntake is for pharmaceutical regulatory-affairs intake. "
    "Please describe a regulatory query."
)


def get_smart_form_prompt(known=None, awaiting=None, deadline_days=None) -> str:
    filled = []
    for name, label in FIELD_LABELS.items():
        value = (known or {}).get(name)
        if value is not None:
            filled.append(f"- {label}: {value}")
    recorded = "\n".join(filled) if filled else "nothing yet"

    hint = ""
    if awaiting:
        hint = f"\nThe user is answering: {FIELD_LABELS.get(awaiting, awaiting)}."
    if deadline_days is not None:
        hint += f"\nKnown deadline: {deadline_days} day(s) from today."

    return f"""
You are a pharmaceutical regulatory-affairs intake assistant.

Extract only what the latest user message actually says.
Return structured fields. Do not invent missing information.

Fields:
- query_type: {", ".join(QUERY_TYPES)}
- regulation_ref: {", ".join(REGULATION_REFS)}
- product_area: {", ".join(PRODUCT_AREAS)}
- urgency: always null (Python sets this from deadline_days)
- submitting_team: a team name, never a person
- deadline_days: days until the stated deadline (tomorrow=1). Null if none.
- out_of_scope: true only if this is not a regulatory-affairs request

Rules:
- Null means "not in this message". Do not overwrite known values with null.
- If the regulation is named but not in the list (for example MHRA), use other.
- If the user does not know the regulation, return null.
- Do not set deadline_days from words like ASAP or urgent. Only a real date/deadline counts.
- product_area is the product/therapeutic area, not the submitting team.
- If this is not a regulatory query, set out_of_scope true and leave other fields null.

Already recorded:
{recorded}
{hint}

Example 1
User: "We received an FDA inspection observation related to our manufacturing process. The response is due in 10 days. CMC will handle it."
query_type=inspection, regulation_ref=FDA_21CFR, product_area=cmc, submitting_team=CMC, deadline_days=10, urgency=null

Example 2
User: "We have a safety concern in a clinical trial but I'm not sure which regulatory framework applies. The Clinical team is handling it."
query_type=safety_signal, regulation_ref=null, product_area=clinical, submitting_team=Clinical, deadline_days=null, urgency=null
""".strip()
