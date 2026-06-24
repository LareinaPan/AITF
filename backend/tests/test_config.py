from app.config import PROJECT_ROOT, normalize_database_url


def test_normalize_database_url_resolves_relative_path_from_project_root() -> None:
    url = normalize_database_url("sqlite:///./storage/aitf.db")
    assert url == f"sqlite:///{(PROJECT_ROOT / 'storage' / 'aitf.db').resolve()}"
