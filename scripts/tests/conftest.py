import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def workdir(tmp_path):
    (tmp_path / "config").mkdir()
    shutil.copy(ROOT / "config" / "config.template.toml", tmp_path / "config" / "config.toml")
    return tmp_path
