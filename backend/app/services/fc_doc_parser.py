import uuid
from io import BytesIO
from pathlib import Path

from docx import Document

from app.config import STORAGE_DIR, get_settings

ALLOWED_EXTENSIONS = frozenset({".txt", ".md", ".docx"})
EXTENSION_TO_FILE_TYPE = {
    ".txt": "txt",
    ".md": "md",
    ".docx": "docx",
}
MAX_FILENAME_LENGTH = 255
MAX_PARSED_TEXT_CHARS = 100_000


class FcDocParseError(ValueError):
    """Raised when requirement document content cannot be parsed."""


class UnsupportedFcDocFormatError(FcDocParseError):
    """Raised when the uploaded file type is unsupported."""


class FcDocSizeLimitError(FcDocParseError):
    """Raised when the uploaded file exceeds the configured size limit."""


def sanitize_fc_upload_filename(filename: str) -> str:
    """Validate the original upload filename (supports Unicode names)."""
    safe_name = Path(filename).name
    if not safe_name or safe_name in {".", ".."}:
        raise FcDocParseError("Invalid upload filename")
    if any(char in safe_name for char in ("/", "\\", "\x00")):
        raise FcDocParseError("Invalid upload filename")
    if len(safe_name) > MAX_FILENAME_LENGTH:
        raise FcDocParseError("Upload filename too long")
    return safe_name


def build_storage_filename(original_filename: str) -> str:
    """Build a filesystem-safe stored name while preserving the extension."""
    extension = Path(original_filename).suffix.lower()
    return f"{uuid.uuid4()}{extension}"


def resolve_file_type(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFcDocFormatError(
            f"不支持的文件格式：{extension or '(无扩展名)'}，仅支持 .txt / .md / .docx"
        )
    return EXTENSION_TO_FILE_TYPE[extension]


def get_fc_upload_directory(fc_project_id: uuid.UUID) -> Path:
    return STORAGE_DIR / "fc-uploads" / str(fc_project_id)


def validate_upload_size(content: bytes) -> None:
    max_bytes = get_settings().fc_max_doc_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise FcDocSizeLimitError(
            f"文件大小超过上限（{get_settings().fc_max_doc_size_mb} MB）"
        )


def save_fc_requirement_upload(
    fc_project_id: uuid.UUID,
    filename: str,
    content: bytes,
) -> Path:
    """Save uploaded requirement document under storage/fc-uploads/{fc_project_id}/."""
    validate_upload_size(content)
    sanitize_fc_upload_filename(filename)
    resolve_file_type(filename)

    upload_dir = get_fc_upload_directory(fc_project_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    target_path = upload_dir / build_storage_filename(filename)
    target_path.write_bytes(content)
    return target_path


def _truncate_parsed_text(text: str) -> str:
    if len(text) <= MAX_PARSED_TEXT_CHARS:
        return text
    return text[:MAX_PARSED_TEXT_CHARS]


def parse_txt_or_md(content: bytes) -> str:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FcDocParseError("Text file must be UTF-8 encoded") from exc

    normalized = text.strip()
    if not normalized:
        raise FcDocParseError("Document is empty after parsing")
    return _truncate_parsed_text(normalized)


def parse_docx(content: bytes) -> str:
    try:
        document = Document(BytesIO(content))
    except Exception as exc:
        raise FcDocParseError(f"Invalid DOCX document: {exc}") from exc

    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    if not paragraphs:
        raise FcDocParseError("DOCX document contains no readable text")

    return _truncate_parsed_text("\n".join(paragraphs))


def parse_requirement_content(content: bytes, filename: str) -> str:
    """Parse requirement document bytes into plain text."""
    file_type = resolve_file_type(filename)
    if file_type in {"txt", "md"}:
        return parse_txt_or_md(content)
    if file_type == "docx":
        return parse_docx(content)
    raise UnsupportedFcDocFormatError(f"Unsupported file type: {file_type}")


def delete_fc_requirement_file(file_path: str) -> None:
    path = Path(file_path)
    if path.is_file():
        path.unlink()
