from collections.abc import Generator

import pytest

from vibectl.memory import clear_memory


@pytest.fixture(autouse=True)
def reset_memory() -> Generator[None, None, None]:
    clear_memory()
    yield
    clear_memory()
