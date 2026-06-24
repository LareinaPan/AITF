import re
import uuid

from pydantic import BaseModel, Field, field_validator

ENV_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
VAR_KEY_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class EnvironmentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    is_default: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not ENV_NAME_PATTERN.fullmatch(normalized):
            raise ValueError(
                "Environment name must be 1-64 characters and contain only letters, numbers, underscores, or hyphens"
            )
        return normalized


class EnvironmentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    is_default: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not ENV_NAME_PATTERN.fullmatch(normalized):
            raise ValueError(
                "Environment name must be 1-64 characters and contain only letters, numbers, underscores, or hyphens"
            )
        return normalized


class EnvironmentResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_default: bool

    model_config = {"from_attributes": True}


class EnvironmentVariableItem(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    value: str = Field(default="", max_length=2048)
    is_secret: bool = False

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        normalized = value.strip()
        if not VAR_KEY_PATTERN.fullmatch(normalized):
            raise ValueError(
                "Variable key must start with a letter or underscore and contain only letters, numbers, or underscores"
            )
        return normalized


class EnvironmentVariableResponse(BaseModel):
    id: uuid.UUID
    key: str
    value: str
    is_secret: bool

    model_config = {"from_attributes": True}


class EnvironmentVariablesBatchRequest(BaseModel):
    variables: list[EnvironmentVariableItem] = Field(default_factory=list)

    @field_validator("variables")
    @classmethod
    def validate_unique_keys(
        cls,
        variables: list[EnvironmentVariableItem],
    ) -> list[EnvironmentVariableItem]:
        keys = [item.key for item in variables]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate variable keys are not allowed")
        return variables
