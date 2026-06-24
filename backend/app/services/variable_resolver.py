import re
from collections.abc import Mapping
from urllib.parse import urlparse, urlunparse

PLACEHOLDER_PATTERN = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}")
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1"})


class MissingVariableError(KeyError):
    """Raised when a template references an undefined environment variable."""


def build_variable_map(variables: Mapping[str, str]) -> dict[str, str]:
    """Build a lookup map from the selected environment variables as-is."""
    return {key: value for key, value in variables.items()}


def rewrite_loopback_host(url: str, host_alias: str | None) -> str:
    """Rewrite loopback hosts in a resolved URL for Docker runners.

    Environment variable values are left unchanged; only the final request URL
    is adapted so localhost/127.0.0.1 reach the host machine from a container.
    """
    if not host_alias or not url:
        return url

    parsed = urlparse(url)
    if parsed.hostname not in LOOPBACK_HOSTS:
        return url

    port_suffix = f":{parsed.port}" if parsed.port else ""
    return urlunparse(parsed._replace(netloc=f"{host_alias}{port_suffix}"))


def resolve_template(
    template: str,
    variables: Mapping[str, str],
    *,
    strict: bool = True,
) -> str:
    """Replace `{{var}}` placeholders in a string with environment variable values."""

    def replace_match(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            if strict:
                raise MissingVariableError(f"Missing environment variable: {key}")
            return match.group(0)
        return variables[key]

    return PLACEHOLDER_PATTERN.sub(replace_match, template)


def variables_to_map(variables: Mapping[str, str] | list[tuple[str, str]]) -> dict[str, str]:
    """Convert environment variable records to a lookup map."""
    if isinstance(variables, Mapping):
        return dict(variables)

    return {key: value for key, value in variables}
