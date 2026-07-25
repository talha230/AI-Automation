"""Unit tests for the Pydantic schemas — no network or API key required."""

import pytest
from pydantic import ValidationError

from app.schemas import (
    FunctionalRequirement,
    RequirementsDocument,
    RequirementsRequest,
)


def test_request_rejects_too_short_idea():
    with pytest.raises(ValidationError):
        RequirementsRequest(idea="short")


def test_request_accepts_valid_idea():
    req = RequirementsRequest(idea="A tool-sharing app for neighbours.")
    assert req.audience is None
    assert req.context is None


def test_functional_requirement_priority_is_constrained():
    with pytest.raises(ValidationError):
        FunctionalRequirement(
            id="FR-1", title="x", description="y", priority="urgent"
        )


def test_document_round_trips_through_json():
    doc = RequirementsDocument(
        project_name="ToolShare",
        summary="An app to borrow and lend tools.",
        functional_requirements=[
            FunctionalRequirement(
                id="FR-1",
                title="List a tool",
                description="Users can list tools they own.",
                priority="must_have",
            )
        ],
        non_functional_requirements=[],
        user_stories=[],
        assumptions=["Users have smartphones."],
        out_of_scope=["Payments."],
        risks=[],
        clarifying_questions=["What is the target region?"],
    )
    restored = RequirementsDocument.model_validate_json(doc.model_dump_json())
    assert restored == doc
