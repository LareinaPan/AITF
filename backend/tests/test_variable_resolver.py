import pytest

from app.services.variable_resolver import MissingVariableError, build_variable_map, resolve_template


def test_resolve_template_replaces_base_url() -> None:
    variables = {"base_url": "http://localhost:8080"}

    result = resolve_template("{{base_url}}/api/users", variables)

    assert result == "http://localhost:8080/api/users"


def test_resolve_template_replaces_multiple_variables() -> None:
    variables = {
        "base_url": "http://localhost:8080",
        "token": "abc123",
    }

    result = resolve_template(
        "GET {{base_url}}/health Authorization: Bearer {{token}}",
        variables,
    )

    assert result == "GET http://localhost:8080/health Authorization: Bearer abc123"


def test_resolve_template_without_placeholders() -> None:
    result = resolve_template("plain-text", {"base_url": "http://localhost:8080"})

    assert result == "plain-text"


def test_resolve_template_missing_variable_strict() -> None:
    with pytest.raises(MissingVariableError, match="base_url"):
        resolve_template("{{base_url}}/api", {}, strict=True)


def test_resolve_template_missing_variable_non_strict() -> None:
    result = resolve_template("{{base_url}}/api", {}, strict=False)

    assert result == "{{base_url}}/api"


def test_build_variable_map_uses_environment_values_as_is() -> None:
    source = {
        "base_url": "http://127.0.0.1:8001",
        "token": "real-token",
    }

    result = build_variable_map(source)

    assert result == source
    assert result is not source


def test_rewrite_loopback_host_only_affects_resolved_url() -> None:
    from app.services.variable_resolver import rewrite_loopback_host

    assert (
        rewrite_loopback_host("http://127.0.0.1:8001/api", "host.docker.internal")
        == "http://host.docker.internal:8001/api"
    )
    assert rewrite_loopback_host("http://api.example.com/users", "host.docker.internal") == (
        "http://api.example.com/users"
    )
