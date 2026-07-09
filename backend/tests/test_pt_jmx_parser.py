from pathlib import Path

import pytest

from app.services.pt_jmx_parser import (
    PtJmxParseError,
    PtJmxSizeLimitError,
    UnsupportedPtJmxFormatError,
    parse_jmx_content,
    parse_jmx_file,
    save_pt_jmx_upload,
)


SAMPLE_JMX = b"""<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test Plan"/>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="Thread Group 1">
        <stringProp name="ThreadGroup.num_threads">10</stringProp>
        <stringProp name="ThreadGroup.ramp_time">5</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="Login API">
          <stringProp name="HTTPSampler.protocol">https</stringProp>
          <stringProp name="HTTPSampler.domain">api.example.com</stringProp>
          <stringProp name="HTTPSampler.path">${base_url}/api/login</stringProp>
          <stringProp name="HTTPSampler.method">POST</stringProp>
        </HTTPSamplerProxy>
        <hashTree>
          <HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="HTTP Header Manager">
            <collectionProp name="HeaderManager.headers">
              <elementProp name="" elementType="Header">
                <stringProp name="Header.name">Content-Type</stringProp>
                <stringProp name="Header.value">application/json</stringProp>
              </elementProp>
            </collectionProp>
          </HeaderManager>
          <hashTree/>
        </hashTree>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="Profile API">
          <stringProp name="HTTPSampler.path">https://api.example.com/api/profile</stringProp>
          <stringProp name="HTTPSampler.method">GET</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""


def test_parse_jmx_content_extracts_samplers_and_thread_groups() -> None:
    plan = parse_jmx_content(SAMPLE_JMX)

    assert len(plan.thread_groups) == 1
    assert plan.thread_groups[0].name == "Thread Group 1"
    assert plan.thread_groups[0].num_threads == 10
    assert plan.thread_groups[0].ramp_time == 5

    assert len(plan.samplers) == 2
    assert plan.samplers[0].key == "sampler-001"
    assert plan.samplers[0].name == "Login API"
    assert plan.samplers[0].method == "POST"
    assert plan.samplers[0].url == "${base_url}/api/login"
    assert plan.samplers[0].has_variables is True
    assert plan.samplers[0].headers[0].name == "Content-Type"

    assert plan.samplers[1].name == "Profile API"
    assert plan.samplers[1].url == "https://api.example.com/api/profile"
    assert plan.samplers[1].has_variables is False


def test_parse_jmx_file_from_demo_asset() -> None:
    demo_path = Path(__file__).resolve().parents[2] / "docs" / "demo" / "demo-load-test.jmx"
    plan = parse_jmx_file(demo_path)

    assert len(plan.thread_groups) == 1
    assert len(plan.samplers) == 3
    assert plan.samplers[0].method == "GET"
    assert "jsonplaceholder.typicode.com" in plan.samplers[0].url


def test_parse_jmx_content_skips_disabled_http_samplers() -> None:
    content = b"""<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test Plan"/>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="Thread Group 1">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="Disabled API" enabled="false">
          <stringProp name="HTTPSampler.path">https://api.example.com/disabled</stringProp>
          <stringProp name="HTTPSampler.method">GET</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="Active API">
          <stringProp name="HTTPSampler.path">https://api.example.com/active</stringProp>
          <stringProp name="HTTPSampler.method">POST</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""
    plan = parse_jmx_content(content)

    assert len(plan.samplers) == 1
    assert plan.samplers[0].name == "Active API"
    assert plan.samplers[0].method == "POST"
    assert plan.samplers[0].url == "https://api.example.com/active"


def test_parse_jmx_content_raises_when_all_http_samplers_disabled() -> None:
    content = b"""<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test Plan"/>
    <hashTree>
      <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="Disabled API" enabled="false">
        <stringProp name="HTTPSampler.path">https://api.example.com/disabled</stringProp>
        <stringProp name="HTTPSampler.method">GET</stringProp>
      </HTTPSamplerProxy>
      <hashTree/>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""
    with pytest.raises(PtJmxParseError, match="No HTTP Sampler"):
        parse_jmx_content(content)


def test_parse_jmx_content_raises_on_invalid_xml() -> None:
    with pytest.raises(PtJmxParseError, match="Invalid JMX XML"):
        parse_jmx_content(b"<not-xml")


def test_parse_jmx_content_raises_when_no_http_sampler() -> None:
    content = b"""<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test Plan"/>
    <hashTree/>
  </hashTree>
</jmeterTestPlan>
"""
    with pytest.raises(PtJmxParseError, match="No HTTP Sampler"):
        parse_jmx_content(content)


def test_parse_jmx_content_applies_http_request_defaults() -> None:
    content = b"""<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test Plan"/>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="Thread Group 1">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <ConfigTestElement guiclass="HttpDefaultsGui" testclass="ConfigTestElement" testname="HTTP Request Defaults">
          <stringProp name="HTTPSampler.domain">shop.lemonban.com</stringProp>
          <stringProp name="HTTPSampler.port">8107</stringProp>
          <stringProp name="HTTPSampler.protocol">http</stringProp>
        </ConfigTestElement>
        <hashTree/>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="Hot Search">
          <stringProp name="HTTPSampler.path">/search/hotSearch?number=4&amp;sort=1</stringProp>
          <stringProp name="HTTPSampler.method">GET</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""
    plan = parse_jmx_content(content)

    assert len(plan.samplers) == 1
    assert plan.samplers[0].url == "http://shop.lemonban.com:8107/search/hotSearch?number=4&sort=1"
    assert plan.samplers[0].has_variables is False


def test_parse_jmx_content_applies_scope_header_manager() -> None:
    content = b"""<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test Plan"/>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="Thread Group 1">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="HTTP Header Manager">
          <collectionProp name="HeaderManager.headers">
            <elementProp name="" elementType="Header">
              <stringProp name="Header.name">Authorization</stringProp>
              <stringProp name="Header.value">Bearer token</stringProp>
            </elementProp>
          </collectionProp>
        </HeaderManager>
        <hashTree/>
        <ConfigTestElement guiclass="HttpDefaultsGui" testclass="ConfigTestElement" testname="HTTP Request Defaults">
          <stringProp name="HTTPSampler.domain">api.example.com</stringProp>
          <stringProp name="HTTPSampler.protocol">https</stringProp>
        </ConfigTestElement>
        <hashTree/>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="Profile API">
          <stringProp name="HTTPSampler.path">/api/profile</stringProp>
          <stringProp name="HTTPSampler.method">GET</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""
    plan = parse_jmx_content(content)

    assert plan.samplers[0].url == "https://api.example.com/api/profile"
    assert plan.samplers[0].headers[0].name == "Authorization"
    assert plan.samplers[0].headers[0].value == "Bearer token"


def test_parse_user_jmx_applies_http_request_defaults() -> None:
    jmx_path = (
        Path(__file__).resolve().parents[2]
        / "storage/pt-uploads/c3c587f7-594c-4421-bbf9-dfa9e57dd251/401fa9c4-236e-44be-aa5a-bb66f28ff9e0.jmx"
    )
    if not jmx_path.is_file():
        pytest.skip("User JMX fixture not available")

    plan = parse_jmx_file(jmx_path)
    active_sampler = plan.samplers[-1]

    assert active_sampler.name.endswith("aiAppCollection")
    assert active_sampler.url == "http://shop.lemonban.com:8107/search/hotSearch?number=4&sort=1"


def test_save_pt_jmx_upload_rejects_non_jmx(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.pt_jmx_parser.STORAGE_DIR", tmp_path)

    with pytest.raises(UnsupportedPtJmxFormatError):
        save_pt_jmx_upload(
            pt_project_id=__import__("uuid").uuid4(),
            filename="demo.txt",
            content=b"hello",
        )


def test_save_pt_jmx_upload_enforces_size_limit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.pt_jmx_parser.STORAGE_DIR", tmp_path)

    class FakeSettings:
        pt_max_jmx_size_mb = 0

    monkeypatch.setattr("app.services.pt_jmx_parser.get_settings", lambda: FakeSettings())

    with pytest.raises(PtJmxSizeLimitError):
        save_pt_jmx_upload(
            pt_project_id=__import__("uuid").uuid4(),
            filename="demo.jmx",
            content=SAMPLE_JMX,
        )
