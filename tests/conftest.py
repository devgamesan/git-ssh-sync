import pytest


@pytest.fixture(autouse=True)
def _clear_xdg_config_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
