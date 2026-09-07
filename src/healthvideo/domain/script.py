from pydantic import BaseModel, Field


class Delivery(BaseModel):
    schema_version: str = "1.0"
    intent: str
    pace: str = "normal"
    pause_before_ms: int = 0
    pause_after_ms: int = 0
    emphasis_words: list[str] = Field(default_factory=list)
    emotional_color: str = ""


class ScriptLine(BaseModel):
    schema_version: str = "1.0"
    id: str
    text: str
    claim_id: str | None = None
    source_marker: str | None = None
    delivery: Delivery


class Script(BaseModel):
    schema_version: str = "1.0"
    title: str
    language: str = "vi"
    lines: list[ScriptLine] = Field(default_factory=list)
