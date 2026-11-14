import pytest

from seo_agent.tools.http import FetchError, SafeHttpClient, _backoff, is_public_address


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("93.184.216.34", True),
        ("2606:4700::6810:85e5", True),
        ("127.0.0.1", False),
        ("10.0.0.5", False),
        ("172.16.3.1", False),
        ("192.168.1.10", False),
        ("169.254.169.254", False),  # cloud metadata endpoint
        ("100.64.0.1", False),  # carrier-grade NAT
        ("0.0.0.0", False),
        ("::1", False),
        ("fe80::1", False),
        ("fd00::1", False),
        ("::ffff:127.0.0.1", False),  # IPv4-mapped loopback
        ("224.0.0.1", False),
    ],
)
def test_is_public_address(address: str, public: bool) -> None:
    assert is_public_address(address) is public


def _client(allowed_hosts: set[str] | None = None) -> SafeHttpClient:
    return SafeHttpClient(
        user_agent="test", timeout_seconds=5, max_bytes=1000, allowed_hosts=allowed_hosts
    )


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("ftp://machinoai.in/", "unsupported_scheme"),
        ("https://machinoai.in:8443/", "blocked_port"),
        ("https://evil.example/", "out_of_scope"),
    ],
)
async def test_unsafe_urls_are_refused_before_any_request(url: str, code: str) -> None:
    async with _client(allowed_hosts={"machinoai.in"}) as client:
        with pytest.raises(FetchError) as info:
            await client.fetch(url)
    assert info.value.code == code
    assert info.value.transient is False


async def test_private_dns_answer_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_getaddrinfo(host: str) -> list[tuple[object, ...]]:
        return [
            (None, None, None, "", ("93.184.216.34", 0)),
            (None, None, None, "", ("10.1.2.3", 0)),
        ]

    async with _client() as client:
        monkeypatch.setattr(client, "_getaddrinfo", fake_getaddrinfo)
        with pytest.raises(FetchError) as info:
            await client.resolve_public("mixed.example")  # one private answer is enough to block
    assert info.value.code == "blocked_address"


def test_retry_after_is_honoured_and_capped() -> None:
    assert _backoff(1, "3") == 3.0
    assert _backoff(1, "3600") == 30.0
    assert 1.0 <= _backoff(2, None) <= 2.5
