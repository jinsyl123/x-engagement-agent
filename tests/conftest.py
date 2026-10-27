import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def workdir(tmp_path):
    shutil.copy(ROOT / "config.example.toml", tmp_path / "config.toml")
    return tmp_path
