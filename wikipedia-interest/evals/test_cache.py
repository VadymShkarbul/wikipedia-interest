"""Track G — the on-disk cache and retry policy in wiki_api._get_json.

Every other track pre-seeds a cache and reads from it, so until now the cache *hit* path was the
only one ever executed: the write, the TTL, corrupt-entry recovery and the whole retry loop were
untested. That matters twice over — the skill's promise that "repeat and related queries are
cheap" rests entirely on the write actually happening, and a retry bug would surface as a live
network failure, which is exactly what an offline suite exists to catch first.

Network is replaced by monkeypatching `wiki_api._request`, the single function that owns the
socket. `time.sleep` is stubbed too: the real backoff is 1.5+3.0+4.5s and would otherwise make
this file 9 seconds slower than the entire rest of the suite.
"""
from __future__ import annotations

import json
import os
import time

import pytest

import wiki_api

URL = "https://example.test/api"
PARAMS = {"a": "1"}
BODY = {"items": [{"views": 42}]}


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(wiki_api.time, "sleep", lambda _s: None)


@pytest.fixture
def fake_request(monkeypatch):
    """Install a stub _request; returns a list recording every call made through it."""
    def _install(responses):
        calls = []

        def _fake(url, params):
            calls.append((url, params))
            item = responses[min(len(calls) - 1, len(responses) - 1)]
            if isinstance(item, Exception):
                raise item
            return item

        monkeypatch.setattr(wiki_api, "_request", _fake)
        return calls

    return _install


def test_response_is_written_to_cache_and_reused(tmp_path, fake_request):
    """The core promise: a repeat query must not touch the network a second time."""
    calls = fake_request([(200, BODY)])
    first = wiki_api._get_json(URL, PARAMS, cache_dir=str(tmp_path))
    second = wiki_api._get_json(URL, PARAMS, cache_dir=str(tmp_path))

    assert first == (200, BODY) and second == (200, BODY)
    assert len(calls) == 1, "second call should have been served from cache"
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_different_params_are_cached_separately(tmp_path, fake_request):
    calls = fake_request([(200, BODY)])
    wiki_api._get_json(URL, {"a": "1"}, cache_dir=str(tmp_path))
    wiki_api._get_json(URL, {"a": "2"}, cache_dir=str(tmp_path))
    assert len(calls) == 2
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_expired_entry_is_refetched(tmp_path, fake_request):
    """A stale entry must not be served: pageview history grows month by month."""
    calls = fake_request([(200, BODY)])
    wiki_api._get_json(URL, PARAMS, cache_dir=str(tmp_path), ttl_seconds=3600)
    entry = next(tmp_path.glob("*.json"))
    stale = time.time() - 7200
    os.utime(entry, (stale, stale))

    wiki_api._get_json(URL, PARAMS, cache_dir=str(tmp_path), ttl_seconds=3600)
    assert len(calls) == 2


def test_corrupt_entry_is_refetched_rather_than_raising(tmp_path, fake_request):
    """A truncated write (killed process, full disk) must self-heal, not poison every later run."""
    calls = fake_request([(200, BODY)])
    wiki_api._get_json(URL, PARAMS, cache_dir=str(tmp_path))
    next(tmp_path.glob("*.json")).write_text("{not json", encoding="utf-8")

    assert wiki_api._get_json(URL, PARAMS, cache_dir=str(tmp_path)) == (200, BODY)
    assert len(calls) == 2


def test_404_is_returned_and_cached_not_raised(tmp_path, fake_request):
    """404 means 'this article has no data', which is an answer the analysis reports as a gap."""
    calls = fake_request([(404, {"detail": "not found"})])
    status, body = wiki_api._get_json(URL, PARAMS, cache_dir=str(tmp_path))

    assert status == 404 and body == {"detail": "not found"}
    wiki_api._get_json(URL, PARAMS, cache_dir=str(tmp_path))
    assert len(calls) == 1, "a 404 should be cached like any other answer"


def test_transient_failure_is_retried_then_succeeds(tmp_path, fake_request, no_sleep):
    calls = fake_request([(503, None), (200, BODY)])
    assert wiki_api._get_json(URL, PARAMS, cache_dir=str(tmp_path)) == (200, BODY)
    assert len(calls) == 2


def test_transport_error_is_retried_then_succeeds(tmp_path, fake_request, no_sleep):
    """DNS/reset errors propagate out of _request and must be caught by the retry loop."""
    calls = fake_request([OSError("connection reset"), (200, BODY)])
    assert wiki_api._get_json(URL, PARAMS, cache_dir=str(tmp_path)) == (200, BODY)
    assert len(calls) == 2


def test_persistent_failure_raises_wikierror_after_three_attempts(tmp_path, fake_request, no_sleep):
    """The CLI turns WikiError into {"error": ...}; a traceback here would break that contract."""
    calls = fake_request([(503, None)])
    with pytest.raises(wiki_api.WikiError, match="Request failed after retries"):
        wiki_api._get_json(URL, PARAMS, cache_dir=str(tmp_path))

    assert len(calls) == 3
    assert list(tmp_path.glob("*.json")) == [], "a failed fetch must not be cached"


def test_failed_fetch_leaves_no_partial_entry(tmp_path, fake_request, no_sleep):
    """Guards the sequel to a corrupt entry: an error must not be recorded as an answer."""
    fake_request([OSError("down")])
    with pytest.raises(wiki_api.WikiError):
        wiki_api._get_json(URL, PARAMS, cache_dir=str(tmp_path))
    assert list(tmp_path.glob("*.json")) == []
