import pytest

from augneta.config import Config


@pytest.fixture
def config():
    return Config(steps=40, evaluation_start_step=4, evaluation_end_step=40)
