"""Parse Apache JMeter .jmx test plans into HTTP sampler definitions."""

from __future__ import annotations

import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.config import STORAGE_DIR, get_settings

HTTP_SAMPLER_TAGS = frozenset({"HTTPSamplerProxy", "HttpTestSample"})
HTTP_DEFAULTS_TAGS = frozenset({"ConfigTestElement"})
THREAD_GROUP_TAGS = frozenset({"ThreadGroup", "SetupThreadGroup"})
VARIABLE_PATTERN = re.compile(r"\$\{[^}]+\}")


class PtJmxParseError(ValueError):
    """Raised when a JMX file cannot be parsed."""


class PtJmxSizeLimitError(ValueError):
    """Raised when an uploaded JMX exceeds the configured size limit."""


class UnsupportedPtJmxFormatError(ValueError):
    """Raised when the uploaded file is not a .jmx file."""


@dataclass
class ParsedSamplerHeader:
    name: str
    value: str


@dataclass
class ParsedSampler:
    key: str
    name: str
    method: str
    url: str
    headers: list[ParsedSamplerHeader] = field(default_factory=list)
    has_variables: bool = False
    thread_group_name: str | None = None


@dataclass
class ParsedThreadGroup:
    name: str
    num_threads: int | None = None
    ramp_time: int | None = None


@dataclass
class HttpSamplerDefaults:
    protocol: str = "http"
    domain: str = ""
    port: str = ""


@dataclass
class ParsedJmxPlan:
    thread_groups: list[ParsedThreadGroup] = field(default_factory=list)
    samplers: list[ParsedSampler] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "thread_groups": [asdict(item) for item in self.thread_groups],
            "samplers": [
                {
                    **asdict(item),
                    "headers": [asdict(header) for header in item.headers],
                }
                for item in self.samplers
            ],
            "parse_warnings": list(self.parse_warnings),
        }


def pt_upload_dir(pt_project_id: uuid.UUID) -> Path:
    return STORAGE_DIR / "pt-uploads" / str(pt_project_id)


def resolve_file_type(filename: str) -> str:
    lowered = filename.lower()
    if not lowered.endswith(".jmx"):
        raise UnsupportedPtJmxFormatError("Only .jmx files are supported")
    return "jmx"


def _local_tag(element: ET.Element) -> str:
    if "}" in element.tag:
        return element.tag.rsplit("}", 1)[-1]
    return element.tag


def _get_prop(element: ET.Element, prop_name: str) -> str:
    for child in element:
        tag = _local_tag(child)
        if tag in {"stringProp", "boolProp", "intProp", "longProp"} and child.get("name") == prop_name:
            return (child.text or "").strip()
    return ""


def _is_enabled(element: ET.Element) -> bool:
    """JMeter marks disabled elements with enabled=\"false\"; omitted means enabled."""
    return element.get("enabled", "true").lower() != "false"


def _build_url(element: ET.Element, defaults: HttpSamplerDefaults | None = None) -> str:
    path = _get_prop(element, "HTTPSampler.path") or _get_prop(element, "HTTPSampler.url") or "/"
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if path.startswith("${") or _contains_variables(path):
        return path

    protocol = (
        _get_prop(element, "HTTPSampler.protocol")
        or (defaults.protocol if defaults else "")
        or "http"
    )
    domain = _get_prop(element, "HTTPSampler.domain") or (defaults.domain if defaults else "")
    port = _get_prop(element, "HTTPSampler.port") or (defaults.port if defaults else "")

    if domain:
        base = f"{protocol}://{domain}"
        if port and port not in {"80", "443"}:
            base = f"{base}:{port}"
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base}{path}"

    return path


def _is_http_defaults_element(element: ET.Element) -> bool:
    if _local_tag(element) not in HTTP_DEFAULTS_TAGS:
        return False
    if element.get("guiclass") == "HttpDefaultsGui":
        return True
    return bool(
        _get_prop(element, "HTTPSampler.domain")
        or _get_prop(element, "HTTPSampler.port")
        or _get_prop(element, "HTTPSampler.protocol")
    )


def _parse_http_defaults(element: ET.Element) -> HttpSamplerDefaults:
    return HttpSamplerDefaults(
        protocol=_get_prop(element, "HTTPSampler.protocol") or "http",
        domain=_get_prop(element, "HTTPSampler.domain"),
        port=_get_prop(element, "HTTPSampler.port"),
    )


def _merge_headers(
    scope_headers: list[ParsedSamplerHeader],
    sampler_headers: list[ParsedSamplerHeader],
) -> list[ParsedSamplerHeader]:
    merged = {header.name.lower(): header for header in scope_headers}
    for header in sampler_headers:
        merged[header.name.lower()] = header
    return list(merged.values())


def _extract_headers(header_manager: ET.Element) -> list[ParsedSamplerHeader]:
    headers: list[ParsedSamplerHeader] = []
    for child in header_manager.iter():
        if _local_tag(child) != "elementProp":
            continue
        if child.get("elementType") != "Header":
            continue
        name = _get_prop(child, "Header.name")
        value = _get_prop(child, "Header.value")
        if name:
            headers.append(ParsedSamplerHeader(name=name, value=value))
    return headers


def _find_headers_in_hash_tree(hash_tree: ET.Element) -> list[ParsedSamplerHeader]:
    for child in hash_tree:
        if _local_tag(child) == "HeaderManager":
            return _extract_headers(child)
    return []


def _parse_thread_group(element: ET.Element) -> ParsedThreadGroup:
    num_threads_raw = _get_prop(element, "ThreadGroup.num_threads")
    ramp_time_raw = _get_prop(element, "ThreadGroup.ramp_time")
    return ParsedThreadGroup(
        name=element.get("testname") or "Thread Group",
        num_threads=int(num_threads_raw) if num_threads_raw.isdigit() else None,
        ramp_time=int(ramp_time_raw) if ramp_time_raw.isdigit() else None,
    )


def _contains_variables(*values: str) -> bool:
    return any(VARIABLE_PATTERN.search(value) for value in values if value)


def _walk_hash_tree(
    hash_tree: ET.Element,
    plan: ParsedJmxPlan,
    *,
    current_thread_group: str | None,
    sampler_index: int,
    http_defaults: HttpSamplerDefaults | None = None,
    scope_headers: list[ParsedSamplerHeader] | None = None,
) -> int:
    children = list(hash_tree)
    active_scope_headers = list(scope_headers or [])
    index = 0
    while index < len(children):
        child = children[index]
        tag = _local_tag(child)

        if tag in THREAD_GROUP_TAGS:
            thread_group = _parse_thread_group(child)
            plan.thread_groups.append(thread_group)
            if index + 1 < len(children) and _local_tag(children[index + 1]) == "hashTree":
                sampler_index = _walk_hash_tree(
                    children[index + 1],
                    plan,
                    current_thread_group=thread_group.name,
                    sampler_index=sampler_index,
                    http_defaults=http_defaults,
                    scope_headers=active_scope_headers,
                )
            index += 2
            continue

        if _is_http_defaults_element(child):
            if _is_enabled(child):
                http_defaults = _parse_http_defaults(child)
            index += 2
            continue

        if tag == "HeaderManager":
            if _is_enabled(child):
                active_scope_headers = _extract_headers(child)
            index += 2
            continue

        if tag in HTTP_SAMPLER_TAGS:
            if not _is_enabled(child):
                index += 2
                continue

            if sampler_index >= get_settings().pt_max_samplers_per_script:
                plan.parse_warnings.append(
                    f"Sampler limit reached ({get_settings().pt_max_samplers_per_script}); remaining samplers ignored"
                )
                return sampler_index

            method = (_get_prop(child, "HTTPSampler.method") or "GET").upper()
            url = _build_url(child, http_defaults)
            sampler_headers: list[ParsedSamplerHeader] = list(active_scope_headers)
            if index + 1 < len(children) and _local_tag(children[index + 1]) == "hashTree":
                sampler_headers = _merge_headers(
                    sampler_headers,
                    _find_headers_in_hash_tree(children[index + 1]),
                )

            sampler_index += 1
            plan.samplers.append(
                ParsedSampler(
                    key=f"sampler-{sampler_index:03d}",
                    name=child.get("testname") or f"HTTP Sampler {sampler_index}",
                    method=method,
                    url=url,
                    headers=sampler_headers,
                    has_variables=_contains_variables(url),
                    thread_group_name=current_thread_group,
                )
            )
            index += 2
            continue

        if tag == "hashTree":
            sampler_index = _walk_hash_tree(
                child,
                plan,
                current_thread_group=current_thread_group,
                sampler_index=sampler_index,
                http_defaults=http_defaults,
                scope_headers=active_scope_headers,
            )
            index += 1
            continue

        if tag.endswith("Sampler") or tag.endswith("Controller"):
            test_name = child.get("testname") or tag
            if tag not in HTTP_SAMPLER_TAGS:
                plan.parse_warnings.append(f"Ignored {tag}: {test_name}")
        index += 1

    return sampler_index


def parse_jmx_content(content: bytes) -> ParsedJmxPlan:
    if not content.strip():
        raise PtJmxParseError("JMX file is empty")

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise PtJmxParseError(f"Invalid JMX XML: {exc}") from exc

    if _local_tag(root) != "jmeterTestPlan":
        raise PtJmxParseError("Root element must be jmeterTestPlan")

    plan = ParsedJmxPlan()
    for child in root:
        if _local_tag(child) == "hashTree":
            _walk_hash_tree(child, plan, current_thread_group=None, sampler_index=0)
            break

    if not plan.samplers:
        raise PtJmxParseError("No HTTP Sampler found in JMX file")

    return plan


def parse_jmx_file(file_path: Path) -> ParsedJmxPlan:
    content = file_path.read_bytes()
    return parse_jmx_content(content)


def save_pt_jmx_upload(
    *,
    pt_project_id: uuid.UUID,
    filename: str,
    content: bytes,
) -> tuple[Path, int]:
    settings = get_settings()
    max_bytes = settings.pt_max_jmx_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise PtJmxSizeLimitError(
            f"JMX file exceeds size limit ({settings.pt_max_jmx_size_mb} MB)"
        )

    resolve_file_type(filename)
    target_dir = pt_upload_dir(pt_project_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4()}.jmx"
    target_path = target_dir / stored_name
    target_path.write_bytes(content)
    return target_path, len(content)


def delete_pt_jmx_file(file_path: str | None) -> None:
    if not file_path:
        return
    path = Path(file_path)
    if path.is_file():
        path.unlink(missing_ok=True)
