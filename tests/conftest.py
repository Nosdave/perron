"""Make the repo's custom_components visible next to the test harness' own testing_config."""
from pathlib import Path

import pytest

REPO_CC = str(Path(__file__).resolve().parents[1] / "custom_components")


@pytest.fixture(autouse=True)
def _repo_custom_components(hass):
    import custom_components

    if REPO_CC not in custom_components.__path__:
        custom_components.__path__.append(REPO_CC)
    yield
