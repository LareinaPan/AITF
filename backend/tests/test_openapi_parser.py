import json
import uuid
from pathlib import Path

import pytest
import yaml

from app.services.openapi_parser import (
    OpenAPIParseError,
    UnsupportedOpenAPIFormatError,
    get_upload_directory,
    load_openapi_document,
    parse_openapi_content,
    parse_openapi_document,
    save_openapi_upload,
)

SAMPLE_OPENAPI: dict = {
    "openapi": "3.0.3",
    "info": {"title": "Demo API", "version": "1.0.0"},
    "paths": {
        "/users": {
            "parameters": [{"name": "X-Trace", "in": "header"}],
            "get": {
                "summary": "List users",
                "description": "Return paginated users",
                "parameters": [{"name": "page", "in": "query", "schema": {"type": "integer"}}],
                "responses": {"200": {"description": "OK"}},
            },
            "post": {
                "summary": "Create user",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"type": "object", "properties": {"name": {"type": "string"}}},
                        }
                    }
                },
                "responses": {"201": {"description": "Created"}},
            },
        },
        "/users/{id}": {
            "get": {
                "summary": "Get user",
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
            },
        },
    },
}


def test_parse_openapi_document_extracts_operations() -> None:
    endpoints = parse_openapi_document(SAMPLE_OPENAPI)

    assert len(endpoints) == 3

    list_users = next(item for item in endpoints if item.method == "GET" and item.path == "/users")
    assert list_users.summary == "List users"
    assert list_users.description == "Return paginated users"
    assert any(param["name"] == "page" for param in list_users.parameters_json)
    assert any(param["name"] == "X-Trace" for param in list_users.parameters_json)
    assert "200" in list_users.responses_json

    create_user = next(item for item in endpoints if item.method == "POST")
    assert create_user.request_body_json is not None
    assert "application/json" in create_user.request_body_json["content"]


def test_parse_openapi_content_from_json_bytes() -> None:
    content = json.dumps(SAMPLE_OPENAPI).encode("utf-8")
    endpoints = parse_openapi_content(content, "demo.json")

    assert len(endpoints) == 3
    assert endpoints[0].method in {"GET", "POST"}


def test_parse_openapi_content_from_yaml_bytes() -> None:
    content = yaml.safe_dump(SAMPLE_OPENAPI).encode("utf-8")
    endpoints = parse_openapi_content(content, "demo.yaml")

    assert len(endpoints) == 3


def test_parse_openapi_document_rejects_swagger_v2() -> None:
    with pytest.raises(UnsupportedOpenAPIFormatError):
        parse_openapi_document({"swagger": "2.0", "paths": {}})


def test_parse_openapi_document_requires_paths() -> None:
    with pytest.raises(OpenAPIParseError):
        parse_openapi_document({"openapi": "3.0.0"})


def test_load_openapi_document_invalid_json() -> None:
    with pytest.raises(OpenAPIParseError):
        load_openapi_document(b"{invalid", "demo.json")


def test_save_openapi_upload_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.openapi_parser.STORAGE_DIR", tmp_path)
    project_id = uuid.uuid4()
    content = json.dumps(SAMPLE_OPENAPI).encode("utf-8")

    saved_path = save_openapi_upload(project_id, "demo.json", content)

    assert saved_path == get_upload_directory(project_id) / "demo.json"
    assert saved_path.exists()
    assert json.loads(saved_path.read_text(encoding="utf-8"))["info"]["title"] == "Demo API"


def test_save_openapi_upload_rejects_unsupported_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.openapi_parser.STORAGE_DIR", tmp_path)

    with pytest.raises(UnsupportedOpenAPIFormatError):
        save_openapi_upload(uuid.uuid4(), "demo.txt", b"plain")
