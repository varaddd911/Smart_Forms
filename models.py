"""SmartIntake Pydantic models.

PartialIntakeRecord = one turn (any field may be missing).
IntakeRecord = the final five fields, only built when everything is valid.
"""

from typing import Literal, Optional, get_args

from pydantic import BaseModel, Field, field_validator, model_validator

QueryType = Literal[
    "complaint",
    "submission",
    "variation",
    "safety_signal",
    "label_update",
    "inspection",
    "general_enquiry",
]
RegulationRef = Literal[
    "FDA_21CFR",
    "EMA_CTR",
    "ICH_E2A",
    "ICH_Q10",
    "CDSCO_NDC",
    "GxP_GMP",
    "GxP_GCP",
    "other",
]
ProductArea = Literal[
    "oncology",
    "cardiovascular",
    "infectious_disease",
    "cmc",
    "clinical",
    "labelling",
    "general",
]
Urgency = Literal["routine", "standard", "urgent", "critical"]

QUERY_TYPES = get_args(QueryType)
REGULATION_REFS = get_args(RegulationRef)
PRODUCT_AREAS = get_args(ProductArea)
URGENCY_LEVELS = get_args(Urgency)

FIELDS = [
    "query_type",
    "regulation_ref",
    "product_area",
    "urgency",
    "submitting_team",
]
REQUIRED_FIELDS = FIELDS
FIELD_ORDER = FIELDS
BUSINESS_FIELDS = FIELDS

KNOWN_TEAMS = {
    "pv": "PV",
    "cmc": "CMC",
    "clinical": "Clinical",
    "labelling": "Labelling",
    "labeling": "Labelling",
    "submissions": "Submissions",
    "cmc regulatory": "CMC Regulatory",
}


def resolve_urgency(
    deadline_days: Optional[int] = None,
    is_expedited_safety: bool = False,
    is_form_483: bool = False,
) -> Optional[str]:
    """Domain urgency from the primer — not from words like ASAP.

    critical: ≤48 hours, or a legally mandated expedited safety report (SUSAR / ICH E2A)
    urgent: 24–72 hours, or an FDA Form 483 response
    standard: days to 2 weeks
    routine: weeks to months
    """
    if is_expedited_safety:
        return "critical"
    if is_form_483:
        return "urgent"
    if deadline_days is None:
        return None
    if deadline_days <= 2:
        return "critical"
    if deadline_days <= 3:
        return "urgent"
    if deadline_days <= 14:
        return "standard"
    return "routine"


def urgency_from_deadline_days(days: int) -> str:
    return resolve_urgency(deadline_days=days) or "routine"


def refine_partial(partial: "PartialIntakeRecord", user_input: str) -> "PartialIntakeRecord":
    """Prefer an explicit guideline citation over an agency name (EMA vs ICH E2A)."""
    text = user_input.lower()
    compact = text.replace(" ", "").replace("-", "").replace("_", "")
    data = partial.model_dump()

    if "iche2a" in compact or "susar" in text:
        data["regulation_ref"] = "ICH_E2A"
        data["is_expedited_safety"] = True
        if data.get("query_type") is None:
            data["query_type"] = "safety_signal"

    if "483" in text:
        data["is_form_483"] = True
        if data.get("query_type") is None:
            data["query_type"] = "inspection"
        if data.get("regulation_ref") is None:
            data["regulation_ref"] = "FDA_21CFR"

    return PartialIntakeRecord(**data)


def _pick(value, allowed) -> Optional[str]:
    """Return the allowed value if it matches, otherwise None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text in allowed:
        return text
    lowered = text.lower().replace(" ", "_").replace("-", "_")
    for item in allowed:
        if lowered == item.lower():
            return item
    return None


def match_query_type(value: str) -> Optional[str]:
    return _pick(value, QUERY_TYPES)


def match_product_area(value: str) -> Optional[str]:
    return _pick(value, PRODUCT_AREAS)


def match_regulation_ref(value: str) -> Optional[str]:
    matched = _pick(value, REGULATION_REFS)
    if matched:
        return matched
    text = str(value).strip().lower()
    if not text:
        return None
    short = {
        "fda": "FDA_21CFR",
        "21cfr": "FDA_21CFR",
        "ema": "EMA_CTR",
        "e2a": "ICH_E2A",
        "q10": "ICH_Q10",
        "cdsco": "CDSCO_NDC",
        "gmp": "GxP_GMP",
        "gcp": "GxP_GCP",
    }
    compact = text.replace(" ", "").replace("-", "").replace("_", "")
    if compact in short:
        return short[compact]
    if "mhra" in text:
        return "other"
    return None


def normalize_submitting_team(value: str) -> Optional[str]:
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in KNOWN_TEAMS:
        return KNOWN_TEAMS[lowered]
    if "team" in lowered:
        return text.title()
    parts = text.split()
    if len(parts) >= 2 and all(part.isalpha() for part in parts):
        return None
    if text.istitle() and text.isalpha() and lowered not in KNOWN_TEAMS:
        return None
    return text


class PartialIntakeRecord(BaseModel):
    query_type: Optional[QueryType] = None
    regulation_ref: Optional[RegulationRef] = None
    product_area: Optional[ProductArea] = None
    urgency: Optional[Urgency] = None
    submitting_team: Optional[str] = None
    deadline_days: Optional[int] = Field(
        default=None,
        description="Days until the stated deadline. Tomorrow=1. Null if none given.",
    )
    is_expedited_safety: bool = Field(
        default=False,
        description="True for SUSAR / ICH E2A expedited safety reporting.",
    )
    is_form_483: bool = Field(
        default=False,
        description="True for an FDA Form 483 inspection observation.",
    )
    out_of_scope: bool = False

    @model_validator(mode="before")
    @classmethod
    def clean(cls, data):
        if not isinstance(data, dict):
            return data
        cleaned = dict(data)
        if isinstance(cleaned.get("query_type"), str):
            cleaned["query_type"] = match_query_type(cleaned["query_type"])
        if isinstance(cleaned.get("regulation_ref"), str):
            cleaned["regulation_ref"] = match_regulation_ref(cleaned["regulation_ref"])
        if isinstance(cleaned.get("product_area"), str):
            cleaned["product_area"] = match_product_area(cleaned["product_area"])
        if isinstance(cleaned.get("submitting_team"), str):
            cleaned["submitting_team"] = normalize_submitting_team(cleaned["submitting_team"])
        days = cleaned.get("deadline_days")
        if isinstance(days, str) and days.strip().lstrip("-").isdigit():
            cleaned["deadline_days"] = int(days.strip())
        elif days in ("", None):
            cleaned["deadline_days"] = None
        cleaned["urgency"] = None
        return cleaned

    @model_validator(mode="after")
    def set_urgency_from_domain_rules(self):
        self.urgency = resolve_urgency(
            deadline_days=self.deadline_days,
            is_expedited_safety=self.is_expedited_safety,
            is_form_483=self.is_form_483,
        )
        return self


class IntakeRecord(BaseModel):
    query_type: QueryType
    regulation_ref: RegulationRef
    product_area: ProductArea
    urgency: Urgency
    submitting_team: str = Field(min_length=1)

    @field_validator("submitting_team")
    @classmethod
    def must_be_a_team(cls, value: str) -> str:
        team = normalize_submitting_team(value)
        if not team:
            raise ValueError("submitting_team must be a team, not a person's name")
        return team
