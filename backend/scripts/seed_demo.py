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
    DEMO_JMX_PATH,
    DEMO_OPENAPI_PATH,
    DEMO_PASSWORD,
    DEMO_PT_PROJECT_NAME,
    DEMO_PT_SCENARIO_NAME,
    DEMO_USERNAME,
    seed_demo_data,
)


def main() -> None:
    if not DEMO_OPENAPI_PATH.is_file():
        raise SystemExit(f"Demo OpenAPI file not found: {DEMO_OPENAPI_PATH}")
    if not DEMO_JMX_PATH.is_file():
        raise SystemExit(f"Demo JMX file not found: {DEMO_JMX_PATH}")

    with SessionLocal() as session:
        summary = seed_demo_data(session)

    print("Demo data seeded successfully.")
    print(f"  user:       {DEMO_USERNAME} / {DEMO_PASSWORD}")
    print(f"  project_id: {summary.project_id}")
    print(f"  env:        {DEMO_ENV_NAME} ({summary.environment_id})")
    print(f"  endpoints:  created={summary.endpoints_created}, updated={summary.endpoints_updated}")
    print(f"  test_cases: created={summary.test_cases_created}")
    print(f"  test_plans: created={summary.test_plans_created}")
    print(f"  pt_project: {DEMO_PT_PROJECT_NAME} ({summary.pt_project_id})")
    print(f"  pt_scenario: created={summary.pt_scenarios_created}, jmx_seeded={summary.pt_jmx_seeded}")
    print(f"    scenario: {DEMO_PT_SCENARIO_NAME}")


if __name__ == "__main__":
    main()
