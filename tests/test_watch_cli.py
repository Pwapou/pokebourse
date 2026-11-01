from pathlib import Path

import pytest

from app import cli
from app.cli import main
from app.monitoring.models import WatchNotFoundError


def test_watch_commands_create_list_pause_resume_and_unknown_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "watch-cli.db"
    assert main(["--database", str(database), "migrate"]) == 0

    invalid = main(
        [
            "--database",
            str(database),
            "add-watch",
            "vinted",
            "Intervalle invalide",
            "Pikachu",
            "--interval-seconds",
            "60",
        ]
    )
    assert invalid == 1
    assert "intervalle minimum" in capsys.readouterr().err

    created = main(
        [
            "--database",
            str(database),
            "add-watch",
            "vinted",
            "Pikachu Vinted",
            "Carte Pokémon Pikachu",
            "--price-from-cents",
            "1000",
            "--price-to-cents",
            "5000",
            "--interval-seconds",
            "180",
        ]
    )
    assert created == 0
    assert "Veille créée et activée : #1" in capsys.readouterr().out

    assert main(["--database", str(database), "list-watches"]) == 0
    output = capsys.readouterr().out
    assert "Pikachu Vinted" in output
    assert "active" in output
    assert "180 s" in output

    assert main(["--database", str(database), "pause-watch", "1"]) == 0
    assert main(["--database", str(database), "resume-watch", "1"]) == 0
    capsys.readouterr()
    assert main(["--database", str(database), "pause-watch", "999"]) == 1
    assert "Veille introuvable" in capsys.readouterr().err


def test_run_watch_returns_success_and_failure_codes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "watch-run-cli.db"
    assert main(["--database", str(database), "migrate"]) == 0
    assert (
        main(
            [
                "--database",
                str(database),
                "add-watch",
                "leboncoin",
                "Mew LBC",
                "Carte Pokémon Mew",
                "--interval-seconds",
                "180",
            ]
        )
        == 0
    )
    capsys.readouterr()

    class SuccessfulService:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def run_watch_once(self, _connection: object, watch_id: int) -> dict[str, int]:
            assert watch_id == 1
            return {
                "result_count": 2,
                "created_count": 1,
                "updated_count": 1,
            }

    monkeypatch.setattr(cli, "WatchService", SuccessfulService)
    assert main(["--database", str(database), "run-watch", "1"]) == 0
    assert "2 résultat(s)" in capsys.readouterr().out

    class FailingService:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def run_watch_once(self, _connection: object, _watch_id: int) -> dict[str, int]:
            raise WatchNotFoundError("Veille introuvable : 1.")

    monkeypatch.setattr(cli, "WatchService", FailingService)
    assert main(["--database", str(database), "run-watch", "1"]) == 1
    assert "Veille introuvable" in capsys.readouterr().err
