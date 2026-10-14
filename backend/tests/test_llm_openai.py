"""The real model behind the LLM seam: LangChain's ChatOpenAI against a fake OpenAI-compatible server in memory.

No network and no key: every request goes to an httpx.MockTransport. Check ids: A08.1 (client), A08.2 (OpenRouter
settings), A08.3 (local servers), A08.4 (cost).
"""
import json

import httpx
import pytest

from app.config import ConfigError, Settings
from app.deps import build_deps
from app.errors import LLMError
from app.llm.providers import local_url_allowed, make_llm
from app.llm.fake import FakeLLM
from app.llm.openai_compat import ChatModelLLM

TOOLS = [{"type": "function", "function": {
    "name": "lookup_cve", "description": "Look up a CVE.",
    "parameters": {"type": "object", "properties": {"cve_id": {"type": "string"}}, "required": ["cve_id"]}}}]


def fake_server(handler):
    """An OpenAI-compatible server in memory: handler(path, body) -> (status, json). Returns the client and the log."""
    seen = []

    def respond(request: httpx.Request):
        body = json.loads(request.content or b"{}")
        seen.append((request.url.path, body))
        status, payload = handler(request.url.path, body)
        return httpx.Response(status, json=payload)
    return httpx.Client(transport=httpx.MockTransport(respond)), seen


def completion(content=None, tool_calls=None, cost=None):
    usage = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    if cost is not None:
        usage["cost"] = cost  # OpenRouter adds this; OpenAI and local servers don't
    return {"id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "finish_reason": "tool_calls" if tool_calls else "stop",
                         "message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}],
            "usage": usage}


def call(name, args, id_="c1"):
    return {"id": id_, "type": "function", "function": {"name": name, "arguments": args}}


def local(http_client, model="qwen3"):
    return ChatModelLLM("local", "http://localhost:11434/v1", model, http_client=http_client)


# --- A08.1: the client wraps ChatOpenAI and declares the tools through bind_tools

def test_a08_1_step_sends_the_tools_and_parses_tool_calls():
    http, seen = fake_server(lambda p, b: (200, completion(None, [call("lookup_cve", '{"cve_id": "CVE-2024-8309"}')])))
    reply = local(http).step([{"role": "user", "content": "Explain CVE-2024-8309"}], TOOLS)
    path, body = seen[0]
    assert path.endswith("/chat/completions") and body["model"] == "qwen3"
    assert body["tools"][0]["function"]["name"] == "lookup_cve"
    assert [(t.id, t.name, t.args) for t in reply.tool_calls] == [("c1", "lookup_cve", {"cve_id": "CVE-2024-8309"})]
    assert (reply.input_tokens, reply.output_tokens, reply.estimated) == (11, 7, False)


def test_a08_1_step_sends_the_whole_conversation_in_openai_format():
    http, seen = fake_server(lambda p, b: (200, completion("CVE-2024-8309 is an SQL injection [1].")))
    messages = [
        {"role": "system", "content": "You are Patch."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "Explain CVE-2024-8309"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "lookup_cve", "arguments": '{"cve_id": "CVE-2024-8309"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "<<<TOOL_OUTPUT lookup_cve>>>{}<<<END_TOOL_OUTPUT>>>"},
    ]
    reply = local(http).step(messages, TOOLS)
    sent = seen[0][1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user", "assistant", "tool"]
    assert sent[4]["tool_calls"][0]["function"] == {"name": "lookup_cve", "arguments": '{"cve_id": "CVE-2024-8309"}'}
    assert sent[5]["tool_call_id"] == "c1" and "TOOL_OUTPUT" in sent[5]["content"]
    assert reply.content == "CVE-2024-8309 is an SQL injection [1]." and reply.tool_calls == []


def test_a08_1_unparseable_tool_arguments_become_a_bad_arguments_call():
    http, _ = fake_server(lambda p, b: (200, completion(None, [call("lookup_cve", '{"cve_id": ')])))
    reply = local(http).step([{"role": "user", "content": "x"}], TOOLS)
    assert reply.tool_calls[0].name == "lookup_cve" and "cve_id" not in reply.tool_calls[0].args


def test_a08_1_translate_returns_the_plan():
    plan_json = {"semantic_query": "rag injection", "rewrites": ["a", "b", "c", "d"], "filters": {"product": "Langflow", "kev": ""}}
    http, seen = fake_server(lambda p, b: (200, completion(json.dumps(plan_json))))
    plan, reply = local(http).translate("How do I stop RAG injection in Langflow?")
    assert (plan.semantic_query, plan.rewrites, plan.filters) == ("rag injection", ["a", "b", "c"], {"product": "Langflow"})
    assert seen[0][1]["response_format"] == {"type": "json_object"} and "tools" not in seen[0][1]
    assert reply.input_tokens == 11


def test_a08_1_a_bad_plan_falls_back_to_the_question():
    http, _ = fake_server(lambda p, b: (200, completion("I can't do JSON today.")))
    plan, _ = local(http).translate("What is prompt injection?")
    assert (plan.semantic_query, plan.rewrites, plan.filters) == ("What is prompt injection?", [], {})


# --- A08.2: OpenRouter and local servers from the settings

def test_a08_2_openrouter_by_default_uses_gpt_oss_120b():
    s = Settings(llm_provider="openrouter", openrouter_api_key="test-not-a-key")
    s.check()
    llm = make_llm(s)
    assert (llm.name, llm.base_url, llm.model) == ("openrouter", "https://openrouter.ai/api/v1", "openai/gpt-oss-120b")
    assert llm.label() == "OpenRouter · openai/gpt-oss-120b"


def test_a08_2_openrouter_without_a_key_fails_at_start_up(tmp_path):
    s = Settings(llm_provider="openrouter", state_path=tmp_path / "s.json")
    with pytest.raises(ConfigError, match="LLM_PROVIDER=openrouter needs OPENROUTER_API_KEY"):
        build_deps(s)


def test_a08_2_settings_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("OPENROUTER_API_KEY", " test-not-a-key ")
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-haiku-5.5")
    monkeypatch.setenv("LOCAL_LLM_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen3")
    monkeypatch.setenv("LOCAL_LLM_HOSTS", "gpu-box, ollama.internal")
    s = Settings.from_env()
    assert (s.llm_provider, s.openrouter_api_key, s.openrouter_model) == ("local", "test-not-a-key", "anthropic/claude-haiku-5.5")
    assert (s.local_llm_url, s.local_llm_model) == ("http://127.0.0.1:1234/v1", "qwen3")
    assert s.local_llm_hosts == ["localhost", "127.0.0.1", "::1", "gpu-box", "ollama.internal"]


def test_a08_2_fake_stays_the_default_without_a_key(monkeypatch, tmp_path):
    for name in ("LLM_PROVIDER", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    s = Settings.from_env()
    assert s.llm_provider == "fake" and isinstance(make_llm(s), FakeLLM)


def test_a08_2_health_names_the_real_model(tmp_path, knowledge, index):
    from fastapi.testclient import TestClient

    from app.main import create_app

    s = Settings(llm_provider="openrouter", openrouter_api_key="test-not-a-key", state_path=tmp_path / "s.json")
    health = TestClient(create_app(build_deps(s, knowledge=knowledge, index=index))).get("/health").json()
    assert (health["llm"], health["model"]) == ("openrouter", "OpenRouter · openai/gpt-oss-120b")  # no call made


# --- A08.3: local servers only on this machine (the SSRF guard)

LOOPBACK = ["localhost", "127.0.0.1", "::1"]


@pytest.mark.parametrize("url", ["http://localhost:11434/v1", "http://127.0.0.1:1234/v1", "http://[::1]:8080/v1",
                                 "https://localhost/v1"])
def test_a08_3_local_urls_on_this_machine_are_allowed(url):
    assert local_url_allowed(url, LOOPBACK)


@pytest.mark.parametrize("url", ["http://169.254.169.254/latest", "http://localhost@evil.test/v1",
                                 "http://user:pw@localhost/v1", "file:///etc/passwd", "http://lan-box:1234/v1",
                                 "http://192.168.1.20:11434/v1", "http://localhost.evil.test/v1", "not a url", ""])
def test_a08_3_other_urls_are_rejected(url):
    assert not local_url_allowed(url, LOOPBACK)


def test_a08_3_a_configured_host_is_allowed():
    assert local_url_allowed("http://gpu-box:11434/v1", [*LOOPBACK, "gpu-box"])


def test_a08_3_local_provider_checks_its_url_and_model_at_start_up():
    with pytest.raises(ConfigError, match="must be on this machine"):
        Settings(llm_provider="local", local_llm_url="http://10.0.0.5:11434/v1", local_llm_model="qwen3").check()
    with pytest.raises(ConfigError, match="LOCAL_LLM_MODEL"):
        Settings(llm_provider="local").check()
    s = Settings(llm_provider="local", local_llm_model="qwen3")
    s.check()
    llm = make_llm(s)
    assert (llm.name, llm.base_url, llm.label()) == ("local", "http://localhost:11434/v1", "Local · qwen3")


def test_a08_3_make_llm_refuses_a_remote_url_even_without_check():
    with pytest.raises(LLMError) as e:
        make_llm(Settings(llm_provider="local", local_llm_url="http://evil.test/v1", local_llm_model="m"))
    assert "must be on this machine" in e.value.public


# --- A08.3: local-server quirks

def test_a08_3_json_mode_rejected_retries_in_plain_text_and_remembers():
    def handler(path, body):
        if "response_format" in body:
            return 400, {"error": {"message": "response_format json_object not supported"}}
        return 200, completion('<think>plan it</think>Sure: ```json\n{"semantic_query": "rag injection", '
                               '"rewrites": ["a", "b", "c"], "filters": {"product": "Langflow"}}\n```')
    http, seen = fake_server(handler)
    llm = local(http)
    plan, _ = llm.translate("q")
    assert (plan.semantic_query, plan.filters) == ("rag injection", {"product": "Langflow"})
    assert llm.json_mode is False and len(seen) == 2
    llm.translate("again")
    assert len(seen) == 3  # remembered: no second rejected attempt


def test_a08_3_think_blocks_are_stripped_from_answers():
    http, _ = fake_server(lambda p, b: (200, completion("<think>The user wants…\nlong</think>\nUse least privilege [1].")))
    assert local(http).step([{"role": "user", "content": "x"}], TOOLS).content == "Use least privilege [1]."


def test_a08_3_server_not_running_says_is_it_running():
    def down(request):
        raise httpx.ConnectError("connection refused")
    llm = local(httpx.Client(transport=httpx.MockTransport(down)))
    with pytest.raises(LLMError) as e:
        llm.step([{"role": "user", "content": "x"}], TOOLS)
    assert "Is it running?" in e.value.public and "localhost:11434" in e.value.public


def test_a08_3_missing_model_says_pull_it():
    http, _ = fake_server(lambda p, b: (404, {"error": {"message": "model 'qwen3' not found"}}))
    with pytest.raises(LLMError) as e:
        local(http).step([{"role": "user", "content": "x"}], TOOLS)
    assert "Load or pull it first" in e.value.public


def test_a08_3_spending_cap_reached_is_plain():
    http, _ = fake_server(lambda p, b: (402, {"error": {"message": "Key limit exceeded", "code": 402}}))
    with pytest.raises(LLMError) as e:
        local(http).step([{"role": "user", "content": "x"}], TOOLS)
    assert "spending cap" in e.value.public


# --- A08.4: cost per response

def test_a08_4_cost_is_read_from_usage_cost():
    http, _ = fake_server(lambda p, b: (200, completion("ok", cost=0.000123)))
    assert local(http).step([{"role": "user", "content": "x"}], TOOLS).cost == pytest.approx(0.000123)
    http, _ = fake_server(lambda p, b: (200, completion('{"semantic_query": "x"}', cost=0.00005)))
    assert local(http).translate("x")[1].cost == pytest.approx(0.00005)


def test_a08_4_no_usage_cost_means_zero():
    http, _ = fake_server(lambda p, b: (200, completion("ok")))
    assert local(http).step([{"role": "user", "content": "x"}], TOOLS).cost == 0
