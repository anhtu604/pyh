from typing import Literal

from pydantic import BaseModel, Field


class SourceRecord(BaseModel):
    schema_version: str = "1.0"
    id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    study_design: str = ""
    sample_size: int | None = None
    doi: str | None = None
    pmid: str | None = None
    url: str | None = None


class EvidenceClaim(BaseModel):
    schema_version: str = "1.0"
    id: str
    text_public: str
    text_technical: str
    type: Literal["evidence", "interpretation", "professional_opinion"]
    sources: list[str] = Field(default_factory=list)
