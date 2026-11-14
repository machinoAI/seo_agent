"""Exponential backoff (CrawlThrottle, HTTP retry wait) and the circuit breaker."""

import pytest

from src.tools.crawling import CrawlThrottle, page_failed, site_struggling
from src.tools.http import _backoff

OK = {"url": "u", "status_code": 200}
NOT_FOUND = {"url": "u", "status_code": 404}
OVERLOADED = {"url": "u", "status_code": 503}
NETWORK = {"url": "u", "status_code": None, "error": "network_error"}


def test_what_counts_as_failed_and_as_struggling() -> None:
    assert page_failed(OVERLOADED) and page_failed(NETWORK)
    assert not page_failed(OK) and not page_failed(NOT_FOUND)  # a 404 is a finding, not a failure
    assert site_struggling(OVERLOADED) and site_struggling(NETWORK)
    assert site_struggling({"status_code": 429})
    assert not site_struggling(NOT_FOUND)
    assert not site_struggling({"status_code": None, "error": "out_of_scope"})


def test_backoff_doubles_from_one_second_and_steps_back_down() -> None:
    throttle = CrawlThrottle(base_delay=1.0, max_delay=30, threshold=100)
    assert throttle.delay == 1.0

    delays = []
    for i in range(6):
        throttle.record(OVERLOADED, i)
        delays.append(throttle.delay)
    assert delays == [2, 4, 8, 16, 30, 30]  # 1 s base × 2^n, capped at 30 s

    recovered = []
    for i in range(6):
        throttle.record(OK, 10 + i)
        recovered.append(throttle.delay)
    assert recovered == [16, 8, 4, 2, 1, 1]  # one step down per healthy page, never below base


def test_robots_crawl_delay_or_zero_base_still_backs_off() -> None:
    zero = CrawlThrottle(base_delay=0, max_delay=30, threshold=100)
    zero.record(OVERLOADED, 1)
    assert zero.delay == 2.0  # backoff unit falls back to 1 s
    zero.record(OK, 2)
    assert zero.delay == 0  # back to the configured base


def test_jitter_stays_within_ten_percent() -> None:
    throttle = CrawlThrottle(base_delay=1.0, max_delay=30)
    assert all(0.9 <= throttle.jittered_delay() <= 1.1 for _ in range(200))


def test_breaker_pauses_once_then_stops() -> None:
    throttle = CrawlThrottle(base_delay=1.0, max_delay=30, threshold=3)
    actions = [throttle.record(OVERLOADED, 50 + i) for i in range(6)]

    assert actions == ["slowed", "slowed", "pause", "slowed", "slowed", "stop"]
    assert throttle.stopped
    health = throttle.health()
    assert health["first_server_error_after_pages"] == 50
    assert health["server_errors"] == 6
    assert health["paused"] and health["stopped_early"]
    assert health["max_delay_s"] == 30


def test_ordinary_404s_never_trip_the_breaker() -> None:
    throttle = CrawlThrottle(base_delay=1.0, max_delay=30, threshold=3)
    assert {throttle.record(NOT_FOUND, i) for i in range(20)} == {"ok"}
    assert not throttle.stopped
    assert throttle.delay == 1.0


@pytest.mark.parametrize(("attempt", "expected"), [(1, 2.0), (2, 4.0), (3, 8.0), (10, 30.0)])
def test_http_retry_wait_is_exponential_with_jitter(attempt: int, expected: float) -> None:
    for _ in range(50):
        assert expected * 0.9 <= _backoff(attempt, None, base=1.0, cap=30) <= expected * 1.1


def test_retry_after_header_wins_and_is_capped() -> None:
    assert _backoff(1, "3", base=1.0) == 3.0
    assert _backoff(1, "3600", base=1.0) == 30.0
