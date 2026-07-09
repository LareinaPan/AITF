from io import BytesIO

import pytest
from openpyxl import Workbook

from app.services.fc_experience_importer import (
    FcExperienceImportError,
    TEMPLATE_HEADERS,
    parse_experience_case_excel,
)


def _build_workbook(rows: list[tuple]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(TEMPLATE_HEADERS))
    for row in rows:
        sheet.append(list(row))
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_parse_experience_case_excel_success() -> None:
    content = _build_workbook(
        [
            ("EXP-001", "用户登录", "正确密码登录", "已注册", "1. 输入账号\n2. 登录", "登录成功", "P0", "正向"),
            ("", "用户登录", "错误密码登录", None, "1. 输入错误密码", "提示密码错误", "P1", "异常"),
        ]
    )

    result = parse_experience_case_excel(content)

    assert len(result.valid_rows) == 2
    assert result.errors == []
    assert result.valid_rows[0].case_type == "positive"
    assert result.valid_rows[1].case_type == "negative"
    assert result.valid_rows[1].priority == "P1"


def test_parse_experience_case_excel_rejects_invalid_header() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["wrong", "header"])
    buffer = BytesIO()
    workbook.save(buffer)

    with pytest.raises(FcExperienceImportError, match="表头不符合模板"):
        parse_experience_case_excel(buffer.getvalue())


def test_parse_experience_case_excel_collects_row_errors() -> None:
    content = _build_workbook(
        [
            ("EXP-002", "", "缺少模块", None, "步骤", "预期", "P2", "正向"),
            ("EXP-003", "支付", "无效类型", None, "步骤", "预期", "P2", "未知类型"),
        ]
    )

    result = parse_experience_case_excel(content)

    assert result.valid_rows == []
    assert len(result.errors) == 2
