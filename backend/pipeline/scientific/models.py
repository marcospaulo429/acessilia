from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RequestedDocumentProfile = Literal["auto", "scientific", "general"]
EffectiveDocumentProfile = Literal["scientific", "general"]
DecisionSource = Literal["detector", "override", "unsupported"]


class DocumentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_profile: RequestedDocumentProfile
    effective_profile: EffectiveDocumentProfile
    decision_source: DecisionSource
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)

    @property
    def is_scientific(self) -> bool:
        return self.effective_profile == "scientific"