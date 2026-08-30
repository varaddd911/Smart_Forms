import os
from functools import lru_cache

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import ValidationError

from models import PartialLeaveRequest
from prompts import get_smart_form_prompt


# override=True so a stale machine-level GEMINI_API_KEY cannot shadow .env.
load_dotenv(override=True)

DEFAULT_MODEL = "gemini-3.5-flash-lite"


def get_setting(name: str, default=None):
    """Read config from the environment, then from Streamlit secrets.

    A deployed app has no .env file, so on Streamlit Cloud the key comes from
    the app's secrets instead.
    """
    value = os.getenv(name)

    if value:
        return value

    try:
        import streamlit as st

        return st.secrets.get(name, default)
    except Exception:
        return default


MODEL = get_setting("GEMINI_MODEL", DEFAULT_MODEL)


class ExtractionError(RuntimeError):
    """The model did not return usable leave-request details for this turn."""


class ConfigurationError(RuntimeError):
    """The app has no API key to talk to Gemini with."""


def describe_config_sources() -> str:
    """Report where config was looked for, naming no values.

    A deployed app gives no other way to see why a key was not picked up.
    """
    notes = []

    raw = os.environ.get("GEMINI_API_KEY")

    if raw is None:
        notes.append("no GEMINI_API_KEY environment variable")
    elif not raw.strip():
        notes.append("GEMINI_API_KEY environment variable is set but empty")

    try:
        from dotenv import dotenv_values, find_dotenv

        path = find_dotenv()
        found = list(dotenv_values(path)) if path else []
        notes.append(f".env at {path or '<none found>'} defines: {found or 'nothing'}")
    except Exception:
        notes.append(".env could not be read")

    try:
        import streamlit as st

        notes.append(f"secrets define: {list(st.secrets.keys()) or 'nothing'}")
    except Exception:
        notes.append("no Streamlit secrets available")

    return "; ".join(notes)


@lru_cache(maxsize=1)
def get_client():
    api_key = get_setting("GEMINI_API_KEY")

    if not api_key:
        raise ConfigurationError(
            "GEMINI_API_KEY is not set. Add it to .env when running locally, or to "
            "the app's secrets when deploying to Streamlit Cloud. "
            f"Checked: {describe_config_sources()}."
        )

    # vertexai=False keeps "AQ."-prefixed keys on the Gemini Developer API.
    return genai.Client(api_key=api_key, vertexai=False)


def extract_turn(
    user_input: str,
    known=None,
    awaiting=None,
) -> PartialLeaveRequest:
    try:
        response = get_client().models.generate_content(
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
