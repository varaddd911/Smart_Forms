import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import ValidationError

from models import PartialLeaveRequest
from prompts import get_smart_form_prompt


load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    vertexai=False
)


class ExtractionError(RuntimeError):
    """The model did not return usable leave-request details for this turn."""


def extract_turn(
    user_input: str,
    known=None,
    awaiting=None,
) -> PartialLeaveRequest:
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=user_input,
            config=types.GenerateContentConfig(
                system_instruction=get_smart_form_prompt(known, awaiting),
                response_mime_type="application/json",
                response_schema=PartialLeaveRequest,
            ),
        )
    except APIError as exc:
        raise ExtractionError(str(exc)) from exc

    if not response.text:
        raise ExtractionError("the model returned an empty response")

    try:
        return PartialLeaveRequest.model_validate_json(response.text)
    except ValidationError as exc:
        raise ExtractionError(exc.errors()[0]["msg"]) from exc
