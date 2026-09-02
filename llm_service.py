"""OpenAI SDK extraction. No LangChain."""

import os
import time
from functools import lru_cache

from dotenv import load_dotenv
from openai import APIError, OpenAI

from audit import log_error, log_llm_usage
from models import PartialIntakeRecord
from prompts import get_smart_form_prompt

load_dotenv(override=True)

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_RETRIES = 2
MAX_TOKENS = 300


class ExtractionError(RuntimeError):
    pass


class ConfigurationError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ConfigurationError("OPENAI_API_KEY is not set. Add it to .env.")
    return OpenAI(api_key=api_key)


def _extract_once(user_input: str, known=None, awaiting=None, deadline_days=None) -> PartialIntakeRecord:
    started = time.perf_counter()
    response = get_client().chat.completions.parse(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": get_smart_form_prompt(known, awaiting, deadline_days=deadline_days),
            },
            {"role": "user", "content": user_input},
        ],
        response_format=PartialIntakeRecord,
        max_tokens=MAX_TOKENS,
    )
    usage = getattr(response, "usage", None)
    log_llm_usage(
        getattr(usage, "prompt_tokens", 0) or 0,
        getattr(usage, "completion_tokens", 0) or 0,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )

    message = response.choices[0].message
    if message.refusal or not message.parsed:
        raise ExtractionError("the model did not return intake fields")
    return message.parsed


def extract_turn(user_input: str, known=None, awaiting=None, deadline_days=None) -> PartialIntakeRecord:
    last_error = None
    for attempt in range(1, 1 + MAX_RETRIES + 1):
        try:
            return _extract_once(user_input, known, awaiting, deadline_days)
        except ConfigurationError:
            raise
        except (APIError, ExtractionError) as exc:
            last_error = ExtractionError(str(exc))
            log_error(kind=type(exc).__name__, attempt=attempt)
        except Exception:
            last_error = ExtractionError("extraction failed")
            log_error(kind="Exception", attempt=attempt)
    raise ExtractionError("extraction failed after retries") from last_error
