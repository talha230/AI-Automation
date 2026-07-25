"""The Claude-backed requirements engine.

`RequirementsAssistant` wraps the Anthropic SDK and turns a `RequirementsRequest`
into a validated `RequirementsDocument` using structured outputs — the SDK
constrains the model's response to the `RequirementsDocument` JSON Schema, so we
get a typed object back rather than free-form text we'd have to parse.
"""

from __future__ import annotations

import logging

import anthropic

from .config import Settings
from .schemas import RequirementsDocument, RequirementsRequest

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a senior product analyst and requirements engineer. Given a plain-language
product idea, produce a rigorous, well-structured software requirements document.

Guidelines:
- Write functional requirements that are specific, testable, and independent.
- Prioritise them using MoSCoW (must_have / should_have / could_have / wont_have).
- Cover the important non-functional requirements (performance, security,
  usability, reliability, scalability) that the idea implies.
- Write user stories in the "As a / I want / so that" form with concrete,
  testable acceptance criteria.
- Be explicit about assumptions and what is out of scope for a first iteration.
- Surface real risks with a severity and a concrete mitigation.
- Ask clarifying questions where the idea is genuinely ambiguous — do not invent
  facts the stakeholder never stated.
Keep it practical and grounded; avoid filler.
"""


class AssistantError(RuntimeError):
    """Raised when a requirements document cannot be produced."""


class RequirementsAssistant:
    """Generates structured requirements from a product idea via Claude."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # A bare client resolves credentials from the environment
        # (ANTHROPIC_API_KEY) or an `ant auth login` profile. Only pass an
        # explicit key when one was configured, so profile-based auth still works.
        api_key = (
            settings.anthropic_api_key.get_secret_value()
            if settings.anthropic_api_key
            else None
        )
        self._client = anthropic.Anthropic(
            api_key=api_key,
            timeout=settings.request_timeout_seconds,
        )

    def _build_user_prompt(self, req: RequirementsRequest) -> str:
        parts = [f"Product idea:\n{req.idea.strip()}"]
        if req.audience:
            parts.append(f"\nTarget audience:\n{req.audience.strip()}")
        if req.context:
            parts.append(f"\nAdditional context:\n{req.context.strip()}")
        parts.append(
            "\nProduce the structured requirements document for this idea."
        )
        return "\n".join(parts)

    def generate(self, req: RequirementsRequest) -> RequirementsDocument:
        """Call Claude and return a validated requirements document.

        Raises:
            AssistantError: on API failure, a safety refusal, or if the model
                returns output that cannot be validated against the schema.
        """
        settings = self._settings
        logger.info(
            "Generating requirements (model=%s, effort=%s, idea_chars=%d)",
            settings.model,
            settings.effort,
            len(req.idea),
        )

        try:
            response = self._client.messages.parse(
                model=settings.model,
                max_tokens=settings.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": self._build_user_prompt(req)}
                ],
                output_format=RequirementsDocument,
            )
        except (anthropic.AnthropicError, ValueError, TypeError) as exc:
            # anthropic.AnthropicError covers API failures (network, 401, rate
            # limit, 5xx). The SDK also raises a plain TypeError when *no*
            # credentials can be resolved at all, and a ValueError for some
            # malformed requests it rejects before sending — catch those too so
            # a missing key surfaces as a clean error, not an unhandled 500.
            logger.exception("Anthropic API call failed")
            hint = ""
            if not settings.has_api_key:
                hint = (
                    " (no ANTHROPIC_API_KEY configured — set it in the "
                    "environment or run `ant auth login`)"
                )
            raise AssistantError(
                f"Requirements generation failed: {exc}{hint}"
            ) from exc

        # A safety refusal returns HTTP 200 with stop_reason == "refusal" and no
        # usable content — surface it rather than dereferencing empty output.
        if response.stop_reason == "refusal":
            detail = getattr(response.stop_details, "explanation", None) or (
                "The request was declined by the model's safety system."
            )
            logger.warning("Model refused the request: %s", detail)
            raise AssistantError(f"Request refused: {detail}")

        document = response.parsed_output
        if document is None:
            logger.error(
                "Model returned no parseable output (stop_reason=%s)",
                response.stop_reason,
            )
            raise AssistantError(
                "The model did not return a valid requirements document "
                f"(stop_reason={response.stop_reason})."
            )

        logger.info(
            "Requirements generated (input_tokens=%s, output_tokens=%s)",
            getattr(response.usage, "input_tokens", "?"),
            getattr(response.usage, "output_tokens", "?"),
        )
        return document
