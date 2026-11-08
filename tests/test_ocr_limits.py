"""Limites d'exécution : échéance, annulation, sortie bornée, sémaphore et passes (T06.3)."""

import io
import os
import stat
import textwrap
import threading
import time

import pytest
from PIL import Image

from app.identification.ocr_runner import (
    CancellationToken,
    Deadline,
    OcrCancelledError,
    OcrEngineError,
    OcrOutputLimitError,
    OcrSupervisor,
    OcrUnavailableError,
    check_tesseract_available,
    run_tesseract_tsv,
)
from app.identification.ocr_types import OcrDeadlineExceeded


def _stub(tmp_path: os.PathLike[str], body: str) -> str:
    """Crée un exécutable de substitution (aucun Tesseract réel requis)."""
    path = os.path.join(tmp_path, "fake-tesseract.py")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("#!/usr/bin/env python3\n" + textwrap.dedent(body))
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (60, 30), "white").save(output, format="PNG")
    return output.getvalue()


def test_missing_engine_is_reported_explicitly() -> None:
    with pytest.raises(OcrUnavailableError):
        check_tesseract_available("tesseract-inexistant-pokebourse")


def test_successful_run_returns_tsv(tmp_path: os.PathLike[str]) -> None:
    executable = _stub(tmp_path, """
        import sys
        data = sys.stdin.buffer.read()
        assert data.startswith(b"\\x89PNG")
        sys.stdout.write("level\\tpage_num\\tblock_num\\tpar_num\\tline_num\\tword_num\\tleft\\ttop\\twidth\\theight\\tconf\\ttext\\n")
        sys.stdout.write("5\\t1\\t1\\t1\\t1\\t1\\t10\\t10\\t20\\t10\\t96\\tok\\n")
    """)
    output = run_tesseract_tsv(_png_bytes(), psm=11, deadline=Deadline(10), executable=executable)
    assert "ok" in output


def test_deadline_kills_process_and_raises(tmp_path: os.PathLike[str]) -> None:
    executable = _stub(tmp_path, """
        import sys, time
        sys.stdin.buffer.read()
        time.sleep(30)
    """)
    deadline = Deadline(0.4)
    with pytest.raises(OcrDeadlineExceeded):
        run_tesseract_tsv(_png_bytes(), psm=11, deadline=deadline, executable=executable)


def test_cancellation_kills_process(tmp_path: os.PathLike[str]) -> None:
    executable = _stub(tmp_path, """
        import sys, time
        sys.stdin.buffer.read()
        for _ in range(300):
            time.sleep(0.1)
    """)
    token = CancellationToken()
    token.cancel()
    with pytest.raises(OcrCancelledError):
        run_tesseract_tsv(_png_bytes(), psm=11, deadline=Deadline(10), token=token, executable=executable)


def test_oversized_output_is_refused_not_truncated(tmp_path: os.PathLike[str]) -> None:
    executable = _stub(tmp_path, """
        import sys
        sys.stdin.buffer.read()
        sys.stdout.write("x" * (3 * 1024 * 1024))
        sys.stdout.flush()
    """)
    with pytest.raises(OcrOutputLimitError):
        run_tesseract_tsv(
            _png_bytes(), psm=11, deadline=Deadline(10),
            max_output_bytes=1024 * 1024, executable=executable,
        )


def test_non_zero_exit_is_an_engine_error(tmp_path: os.PathLike[str]) -> None:
    executable = _stub(tmp_path, """
        import sys
        sys.stdin.buffer.read()
        sys.exit(1)
    """)
    with pytest.raises(OcrEngineError):
        run_tesseract_tsv(_png_bytes(), psm=11, deadline=Deadline(10), executable=executable)


def test_no_orphan_process_survives_deadline(tmp_path: os.PathLike[str]) -> None:
    executable = _stub(tmp_path, """
        import sys, time
        sys.stdin.buffer.read()
        time.sleep(60)
    """)
    with pytest.raises(OcrDeadlineExceeded):
        run_tesseract_tsv(_png_bytes(), psm=11, deadline=Deadline(0.3), executable=executable)
    time.sleep(0.2)
    # pgrep est absent de l'image : inspection directe de /proc.
    survivors = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as handle:
                command = handle.read().replace(b"\x00", b" ")
        except OSError:
            continue
        if os.path.basename(executable).encode() in command and int(pid) != os.getpid():
            survivors.append(pid)
    assert not survivors, f"processus orphelin encore actif : {survivors}"


def test_supervisor_limits_concurrency_and_releases_on_error() -> None:
    supervisor = OcrSupervisor(concurrency=1)
    deadline = Deadline(5)
    with supervisor.slot(deadline):
        assert supervisor.active_analyses() == 1
        with pytest.raises(OcrDeadlineExceeded):
            with supervisor.slot(Deadline(0.2)):
                pass
    assert supervisor.active_analyses() == 0
    # Après erreur dans le bloc, le sémaphore est libéré pour l'analyse suivante.
    with pytest.raises(RuntimeError, match="boom"):
        with supervisor.slot(deadline):
            raise RuntimeError("boom")
    assert supervisor.active_analyses() == 0
    with supervisor.slot(deadline):
        assert supervisor.active_analyses() == 1


def test_supervisor_cancel_all_kills_registered_processes(tmp_path: os.PathLike[str]) -> None:
    executable = _stub(tmp_path, """
        import sys, time
        sys.stdin.buffer.read()
        time.sleep(60)
    """)
    supervisor = OcrSupervisor(concurrency=1)
    deadline = Deadline(10)
    errors: list[BaseException] = []

    def _run() -> None:
        try:
            with supervisor.slot(deadline) as slot:
                run_tesseract_tsv(
                    _png_bytes(), psm=11, deadline=Deadline(10),
                    token=slot.token, executable=executable, supervisor=supervisor,
                )
        except BaseException as exc:  # noqa: BLE001 - propagé vers l'assertion principale
            errors.append(exc)

    worker = threading.Thread(target=_run)
    worker.start()
    time.sleep(0.5)
    supervisor.cancel_all()
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert errors and isinstance(errors[0], OcrCancelledError)
    assert supervisor.active_analyses() == 0


def test_deadline_is_monotonic_and_shared() -> None:
    deadline = Deadline(0.3)
    time.sleep(0.4)
    assert deadline.expired()
    with pytest.raises(OcrDeadlineExceeded):
        deadline.check()
    with pytest.raises(ValueError):
        Deadline(0)
