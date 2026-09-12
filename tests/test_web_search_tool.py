import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.web_search_tool import SerperSearchError, _run_serper_search


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self) -> bytes:
        return self._payload


def test_serper_search_builds_get_request(monkeypatch):
    captured = {}
    expected = {"organic": [{"title": "Pasta", "link": "https://example.com"}]}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(expected)

    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    monkeypatch.setattr("app.web_search_tool.urlopen", fake_urlopen)

    result = _run_serper_search("easy pasta & tomatoes", limit=5)

    request = captured["request"]
    query = parse_qs(urlsplit(request.full_url).query)
    assert result == expected
    assert request.get_method() == "GET"
    assert query == {
        "q": ["easy pasta & tomatoes"],
        "apiKey": ["test-key"],
        "num": ["5"],
    }
    assert captured["timeout"] == 30.0


def test_serper_search_requires_api_key(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)

    with pytest.raises(SerperSearchError, match="SERPER_API_KEY"):
        _run_serper_search("easy pasta")


@pytest.mark.parametrize("query", ["", "   "])
def test_serper_search_rejects_empty_query(query):
    with pytest.raises(ValueError, match="must not be empty"):
        _run_serper_search(query)


@pytest.mark.parametrize("limit", [0, 101])
def test_serper_search_rejects_invalid_limit(monkeypatch, limit):
    monkeypatch.setenv("SERPER_API_KEY", "test-key")

    with pytest.raises(ValueError, match="between 1 and 100"):
        _run_serper_search("easy pasta", limit=limit)
