from pydantic import BaseModel, Field


class AuthorBrief(BaseModel):
    schema_version: str = "1.0"
    title: str
    why_speak: str = ""
    personal_position: str = ""
    desired_audience_action: str = ""
    emotion: str = ""
    phrases_to_keep: list[str] = Field(default_factory=list)
