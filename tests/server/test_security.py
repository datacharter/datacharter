from starlette.requests import Request

from datacharter.server.security import (
    allowed_hosts,
    host_allowed,
    is_request_allowed,
    origin_allowed,
)


def _req(headers: dict) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw})


def test_allowed_hosts_includes_loopback_and_bind():
    ah = allowed_hosts("127.0.0.1")
    assert ah is not None and "127.0.0.1" in ah and "localhost" in ah


def test_all_interfaces_disables_allowlist():
    assert allowed_hosts("0.0.0.0") is None


def test_loopback_host_allowed():
    assert host_allowed(_req({"host": "127.0.0.1:8765"}), allowed_hosts("127.0.0.1")) is True


def test_foreign_host_rejected():
    assert host_allowed(_req({"host": "evil.example.com"}), allowed_hosts("127.0.0.1")) is False


def test_cross_origin_rejected():
    ah = allowed_hosts("127.0.0.1")
    assert origin_allowed(_req({"origin": "http://evil.example.com"}), ah) is False


def test_cross_site_secfetch_rejected():
    ah = allowed_hosts("127.0.0.1")
    assert origin_allowed(_req({"sec-fetch-site": "cross-site"}), ah) is False


def test_same_origin_allowed():
    req = _req({"origin": "http://127.0.0.1", "sec-fetch-site": "same-origin"})
    assert origin_allowed(req, allowed_hosts("127.0.0.1")) is True


def test_is_request_allowed_combines_host_and_origin():
    ah = allowed_hosts("127.0.0.1")
    assert is_request_allowed(_req({"host": "127.0.0.1:8765"}), ah) is True
    bad = _req({"host": "127.0.0.1", "origin": "http://evil.example.com"})
    assert is_request_allowed(bad, ah) is False
