from unittest.mock import AsyncMock

import pytest

from tests.unit.test_support.async_session_iter import make_single_session_getter


@pytest.mark.asyncio
async def test_make_single_session_getter_yields_once() -> None:
    session = AsyncMock()
    getter = make_single_session_getter(session)

    values = []
    async for value in getter():
        values.append(value)

    assert values == [session]
