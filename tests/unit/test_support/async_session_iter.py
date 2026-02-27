"""Helpers for mocking async session iterators in consumer tests."""

from __future__ import annotations

from typing import Any, Callable


class _SingleSessionIterator:
    def __init__(self, session: Any) -> None:
        self._session = session
        self._consumed = False

    def __aiter__(self) -> "_SingleSessionIterator":
        return self

    async def __anext__(self) -> Any:
        if self._consumed:
            raise StopAsyncIteration
        self._consumed = True
        return self._session


def make_single_session_getter(session: Any) -> Callable[[], _SingleSessionIterator]:
    """Return a get_async_db_session-compatible callable for tests."""

    def _get_async_db_session() -> _SingleSessionIterator:
        return _SingleSessionIterator(session)

    return _get_async_db_session
