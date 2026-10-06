import pytest

from hsdeck import CardDB


@pytest.fixture(scope="session")
def db() -> CardDB:
    return CardDB.load()
