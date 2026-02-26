from __future__ import annotations

import pytest

from tests.test_support.db_cleanup import truncate_with_deadlock_retry


def test_truncate_with_deadlock_retry_retries_then_succeeds() -> None:
    state = {"calls": 0}

    def flaky() -> None:
        state["calls"] += 1
        if state["calls"] < 3:
            raise RuntimeError("deadlock detected while truncating")

    truncate_with_deadlock_retry(flaky, max_attempts=4, backoff_seconds=0)
    assert state["calls"] == 3


def test_truncate_with_deadlock_retry_raises_non_deadlock() -> None:
    def hard_fail() -> None:
        raise RuntimeError("permission denied")

    with pytest.raises(RuntimeError, match="permission denied"):
        truncate_with_deadlock_retry(hard_fail, max_attempts=4, backoff_seconds=0)
