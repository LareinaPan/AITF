import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.config import STORAGE_DIR

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})
ALLOWED_UPLOAD_EXTENSIONS = frozenset({".json", ".yaml", ".yml"})
SAFE_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")


class OpenAPIParseError(ValueError):
    """Raised when OpenAPI content cannot be parsed."""


class UnsupportedOpenAPIFormatError(OpenAPIParseError):
    """Raised when the uploaded file type or OpenAPI version is unsupported."""


@dataclass(frozen=True)
class ParsedApiEndpoint:
    method: str
    path: str
    summary: str | None
    description: str | None
    parameters_json: list[dict[str, Any]]
    request_body_json: dict[str, Any] | None
    responses_json: dict[str, Any]


def sanitize_upload_filename(filename: str) -> str:
    safe_name = Path(filename).name
    if not safe_name or safe_name in {".", ".."}:
        raise OpenAPIParseError("Invalid upload filename")
    if not SAFE_FILENAME_PATTERN.fullmatch(safe_name):
        raise OpenAPIParseError("Upload filename contains unsupported characters")
    return safe_name


def get_upload_directory(project_id: uuid.UUID) -> Path:
    return STORAGE_DIR / "uploads" / str(project_id)


def save_openapi_upload(project_id: uuid.UUID, filename: str, content: bytes) -> Path:
    """Save uploaded OpenAPI document under storage/uploads/{project_id}/."""
    safe_name = sanitize_upload_filename(filename)
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise UnsupportedOpenAPIFormatError(
            f"Unsupported file extension: {extension or '(none)'}"
        )

    upload_dir = get_upload_directory(project_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    target_path = upload_dir / safe_name
    target_path.write_bytes(content)
    return target_path


def load_openapi_document(content: bytes, filename: str) -> dict[str, Any]:
    """Load OpenAPI document from JSON or YAML bytes."""
    extension = Path(filename).suffix.lower()
    text = content.decode("utf-8")

    try:
        if extension == ".json":
            document = json.loads(text)
        elif extension in {".yaml", ".yml"}:
            document = yaml.safe_load(text)
        else:
            raise UnsupportedOpenAPIFormatError(
                f"Unsupported file extension: {extension or '(none)'}"
            )
    except json.JSONDecodeError as exc:
        raise OpenAPIParseError(f"Invalid JSON OpenAPI document: {exc}") from exc
    except yaml.YAMLError as exc:
        raise OpenAPIParseError(f"Invalid YAML OpenAPI document: {exc}") from exc

    if not isinstance(document, dict):
        raise OpenAPIParseError("OpenAPI document must be a JSON object")

    return document


def parse_openapi_document(document: dict[str, Any]) -> list[ParsedApiEndpoint]:
    """Extract API endpoints from an OpenAPI 3.x document."""
    if "swagger" in document and "openapi" not in document:
        raise UnsupportedOpenAPIFormatError(
            "Swagger 2.0 is not supported in MVP; please use OpenAPI 3.x"
        )

    openapi_version = document.get("openapi")
    if not isinstance(openapi_version, str) or not openapi_version.startswith("3."):
        raise OpenAPIParseError("Only OpenAPI 3.x documents are supported")

    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise OpenAPIParseError("OpenAPI document is missing a valid paths object")

    endpoints: list[ParsedApiEndpoint] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        shared_parameters = _normalize_parameters(path_item.get("parameters"))

        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                continue

            operation_parameters = _normalize_parameters(operation.get("parameters"))
            merged_parameters = _merge_parameters(shared_parameters, operation_parameters)

            request_body = operation.get("requestBody")
            request_body_json = request_body if isinstance(request_body, dict) else None

            responses = operation.get("responses", {})
            responses_json = responses if isinstance(responses, dict) else {}

            endpoints.append(
                ParsedApiEndpoint(
                    method=method.upper(),
                    path=str(path),
                    summary=_as_optional_str(operation.get("summary")),
                    description=_as_optional_str(operation.get("description")),
                    parameters_json=merged_parameters,
                    request_body_json=request_body_json,
                    responses_json=responses_json,
                )
            )

    return endpoints


def parse_openapi_content(content: bytes, filename: str) -> list[ParsedApiEndpoint]:
    """Load and parse an uploaded OpenAPI file."""
    document = load_openapi_document(content, filename)
    return parse_openapi_document(document)


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_parameters(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _merge_parameters(
    shared: list[dict[str, Any]],
    operation: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}

    for item in shared + operation:
        name = str(item.get("name", "")).strip()
        location = str(item.get("in", "")).strip()
        if not name or not location:
            continue
        merged[(name, location)] = item

    return list(merged.values())
