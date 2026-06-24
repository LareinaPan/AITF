#!/usr/bin/env python3
"""CLI entrypoint for seeding AITF demo data."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal
from app.services.demo_seed_service import (
    DEMO_ENV_NAME,
    DEMO_OPENAPI_PATH,
    DEMO_PASSWORD,
    DEMO_USERNAME,
    seed_demo_data,
)


def main() -> None:
    if not DEMO_OPENAPI_PATH.is_file():
        raise SystemExit(f"Demo OpenAPI file not found: {DEMO_OPENAPI_PATH}")

    with SessionLocal() as session:
        summary = seed_demo_data(session)

    print("Demo data seeded successfully.")
    print(f"  user:       {DEMO_USERNAME} / {DEMO_PASSWORD}")
    print(f"  project_id: {summary.project_id}")
    print(f"  env:        {DEMO_ENV_NAME} ({summary.environment_id})")
    print(f"  endpoints:  created={summary.endpoints_created}, updated={summary.endpoints_updated}")
    print(f"  test_cases: created={summary.test_cases_created}")
    print(f"  test_plans: created={summary.test_plans_created}")


if __name__ == "__main__":
    main()
