"""Pydantic models.

Two groups live here:

* **API models** (`RequirementsRequest`) describe the HTTP request body.
* **Output models** (`RequirementsDocument` and its children) describe the
  structured JSON that Claude is constrained to return. The SDK derives a JSON
  Schema from `RequirementsDocument` and enforces it on the model's output, so
  every field below becomes a guarantee about the response shape.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Priority = Literal["must_have", "should_have", "could_have", "wont_have"]
Severity = Literal["low", "medium", "high", "critical"]


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class RequirementsRequest(BaseModel):
    """Input for the /requirements endpoint."""

    idea: str = Field(
        ...,
        min_length=10,
        description="A plain-language description of the product or feature.",
        examples=[
            "A mobile app that lets neighbours lend and borrow tools from each other."
        ],
    )
    audience: str | None = Field(
        default=None,
        description="Optional target audience or user segment.",
        examples=["Homeowners in suburban neighbourhoods"],
    )
    context: str | None = Field(
        default=None,
        description="Optional extra context: constraints, platform, timeline, etc.",
    )


# --------------------------------------------------------------------------- #
# Output models — these define the structured JSON contract with Claude
# --------------------------------------------------------------------------- #
class FunctionalRequirement(BaseModel):
    id: str = Field(description="Stable identifier, e.g. FR-1.")
    title: str
    description: str
    priority: Priority


class NonFunctionalRequirement(BaseModel):
    id: str = Field(description="Stable identifier, e.g. NFR-1.")
    category: str = Field(
        description="e.g. performance, security, usability, scalability."
    )
    description: str


class UserStory(BaseModel):
    as_a: str = Field(description="The role/persona ('As a ...').")
    i_want: str = Field(description="The goal ('I want ...').")
    so_that: str = Field(description="The benefit ('so that ...').")
    acceptance_criteria: list[str] = Field(
        description="Testable conditions that mark the story as done."
    )


class Risk(BaseModel):
    description: str
    severity: Severity
    mitigation: str


class RequirementsDocument(BaseModel):
    """The complete structured requirements document Claude returns."""

    project_name: str = Field(description="A concise name for the project.")
    summary: str = Field(description="A one-paragraph overview of the solution.")
    functional_requirements: list[FunctionalRequirement]
    non_functional_requirements: list[NonFunctionalRequirement]
    user_stories: list[UserStory]
    assumptions: list[str] = Field(
        description="Assumptions made while drafting the requirements."
    )
    out_of_scope: list[str] = Field(
        description="Things explicitly not covered by this iteration."
    )
    risks: list[Risk]
    clarifying_questions: list[str] = Field(
        description="Questions to ask the stakeholder before building."
    )


class RequirementsResponse(BaseModel):
    """The endpoint's response envelope."""

    request_id: str
    model: str
    document: RequirementsDocument
