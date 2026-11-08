"""Exécution bornée de Tesseract : échéance, annulation, nettoyage (T06.3).

Le traitement image/OCR s'exécute dans un processus contrôlé : le superviseur
garde le sémaphore, interrompt et récolte le worker et son Tesseract à
l'échéance, à l'annulation ou devant une sortie excessive. Aucun
``Future.cancel()`` ni déconnexion HTTP n'est supposé arrêter Tesseract :
le processus est tué explicitement avec son groupe. Les pipes sont lus de
manière bornée (2 Mio TSV par passe). ``OMP_THREAD_LIMIT=1`` est imposé.

La limite de concurrence est une interface locale : la borne agrégée
app/worker (deux analyses simultanées sur l'ensemble des deux processus)
sera appliquée au job 3 avec un verrou partagé entre processus.
"""

from __future__ import annotations

import os
import select
import shutil
import signal
import subprocess
import threading
import time

from app.identification.ocr_types import Deadline, OcrDeadlineExceeded, OcrError

DEFAULT_GLOBAL_DEADLINE_SECONDS = 20.0
DEFAULT_MAX_PASSES = 6
DEFAULT_MAX_CONCURRENT_ANALYSES = 2


class OcrEngineError(OcrError):
    """Échec du moteur OCR : message utile, réessai ou saisie manuelle."""


class OcrUnavailableError(OcrEngineError):
    """Binaire Tesseract absent."""


class OcrTimeoutError(OcrDeadlineExceeded, OcrEngineError):
    """Échéance globale dépassée : aucun nouvel essai à l'échéance."""


class OcrCancelledError(OcrEngineError):
    """Annulation explicite (client déconnecté, nouvelle image, arrêt)."""


class OcrOutputLimitError(OcrEngineError):
    """Sortie du processus supérieure au plafond : analyse refusée, pas tronquée silencieusement."""


class CancellationToken:
    """Annulation coopérative explicite, indépendante de la déconnexion HTTP."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def throw_if_cancelled(self) -> None:
        if self.cancelled:
            raise OcrCancelledError("Analyse OCR annulée (nouvelle image ou demande client).")


class OcrSupervisor:
    """Sémaphore d'analyses avec récolte des processus et annulation globale.

    Utilisation : ``with supervisor.slot(deadline) as slot:`` garantit la
    libération du sémaphore après erreur ; ``cancel_all()`` tue les processus
    enregistrés et annule leurs jetons. La borne porte ici sur un seul
    processus ; le job 3 composera l'agrégat app/worker.
    """

    def __init__(self, concurrency: int = DEFAULT_MAX_CONCURRENT_ANALYSES) -> None:
        if concurrency <= 0:
            raise ValueError("Concurrence d'analyses strictement positive requise.")
        self._semaphore = threading.BoundedSemaphore(concurrency)
        self._concurrency = concurrency
        self._lock = threading.Lock()
        self._processes: set[subprocess.Popen[bytes]] = set()
        self._tokens: set[CancellationToken] = set()

    @property
    def concurrency(self) -> int:
        return self._concurrency

    def active_analyses(self) -> int:
        """Nombre d'analyses actuellement détenues du sémaphore."""
        return self._concurrency - self._semaphore._value  # type: ignore[attr-defined]

    def slot(self, deadline: Deadline, token: CancellationToken | None = None) -> "SupervisorSlot":
        return SupervisorSlot(self, deadline, token)

    def _acquire(self, deadline: Deadline, token: CancellationToken | None) -> None:
        token = token or CancellationToken()
        with self._lock:
            self._tokens.add(token)
        while True:
            token.throw_if_cancelled()
            deadline.check()
            if self._semaphore.acquire(timeout=min(0.05, max(0.001, deadline.remaining()))):
                return

    def _release(self, token: CancellationToken) -> None:
        try:
            self._semaphore.release()
        except ValueError:
            pass  # double libération : déjà relâché après erreur
        with self._lock:
            self._tokens.discard(token)

    def register(self, process: subprocess.Popen[bytes]) -> None:
        with self._lock:
            self._processes.add(process)

    def unregister(self, process: subprocess.Popen[bytes]) -> None:
        with self._lock:
            self._processes.discard(process)

    def cancel_all(self) -> None:
        """Annule les jetons et tue les processus OCR en cours (tout le groupe)."""
        with self._lock:
            tokens = list(self._tokens)
            processes = list(self._processes)
        for token in tokens:
            token.cancel()
        for process in processes:
            _kill_process_group(process)

    def _remove_token(self, token: CancellationToken) -> None:
        with self._lock:
            self._tokens.discard(token)


class SupervisorSlot:
    """Context manager : acquisition bornée du sémaphore, libération garantie."""

    def __init__(self, supervisor: OcrSupervisor, deadline: Deadline, token: CancellationToken | None) -> None:
        self._supervisor = supervisor
        self._deadline = deadline
        self._token = token or CancellationToken()
        self._held = False

    def __enter__(self) -> "SupervisorSlot":
        self._supervisor._acquire(self._deadline, self._token)
        self._held = True
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._held:
            self._held = False
            self._supervisor._release(self._token)

    @property
    def token(self) -> CancellationToken:
        return self._token


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    """Tue le processus et tout son groupe ; tolère une sortie déjà survenue."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def check_tesseract_available(executable: str = "tesseract") -> None:
    """Refus explicite si le moteur local est absent (réponse 503 côté HTTP)."""
    if shutil.which(executable) is None:
        raise OcrUnavailableError("Moteur OCR indisponible. Reconstruisez l'image Docker de l'application.")


def run_tesseract_tsv(
    image_png: bytes,
    *,
    psm: int,
    deadline: Deadline,
    token: CancellationToken | None = None,
    language: str = "fra+eng",
    max_output_bytes: int = 2 * 1024 * 1024,
    executable: str = "tesseract",
    supervisor: OcrSupervisor | None = None,
) -> str:
    """Exécute ``tesseract stdin stdout -l fra+eng --psm N tsv`` de façon bornée.

    La sortie est lue morceau par morceau avec un plafond strict : une sortie
    excessive entraîne la mort du processus et un refus, jamais une troncature
    silencieuse. L'échéance et l'annulation sont vérifiées pendant la lecture.
    """
    check_tesseract_available(executable)
    token = token or CancellationToken()
    token.throw_if_cancelled()
    deadline.check()
    environment = dict(os.environ, OMP_THREAD_LIMIT="1")
    argv = [executable, "stdin", "stdout", "-l", language, "--psm", str(psm), "tsv"]
    try:
        process: subprocess.Popen[bytes] = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            start_new_session=True,  # groupe dédié : récolte complète à l'échéance
        )
    except OSError as error:
        raise OcrUnavailableError("Moteur OCR indisponible : exécution impossible.") from error
    if supervisor is not None:
        supervisor.register(process)
    try:
        _write_stdin_async(process, image_png)
        output = _read_bounded(process, deadline, token, max_output_bytes)
        remaining = deadline.remaining()
        if remaining <= 0:
            deadline.check()
        try:
            exit_code = process.wait(timeout=min(1.0, remaining))
        except subprocess.TimeoutExpired as error:
            _kill_process_group(process)
            if deadline.expired():
                raise OcrTimeoutError("Échéance globale OCR dépassée : analyse interrompue.") from error
            raise OcrEngineError("Tesseract n'a pas terminé après sa sortie.") from error
        if exit_code != 0:
            raise OcrEngineError("Analyse OCR impossible pour cette image (code de sortie non nul).")
        return output.decode("utf-8", errors="replace")
    finally:
        if supervisor is not None:
            supervisor.unregister(process)
        if process.poll() is None:
            _kill_process_group(process)
        for pipe in (process.stdin, process.stdout):
            try:
                if pipe is not None:
                    pipe.close()
            except OSError:
                pass


def _write_stdin_async(process: subprocess.Popen[bytes], payload: bytes) -> threading.Thread:
    """Alimente stdin dans un thread démon : l'échéance reste vérifiable."""

    def _write() -> None:
        assert process.stdin is not None
        try:
            view = memoryview(payload)
            while view:
                try:
                    written = process.stdin.write(view[:65536])
                    process.stdin.flush()
                except (BrokenPipeError, OSError):
                    break  # le processus a déjà refusé : erreur lue côté stdout
                view = view[written:]
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass

    writer = threading.Thread(target=_write, name="ocr-stdin-writer", daemon=True)
    writer.start()
    return writer


def _read_bounded(
    process: subprocess.Popen[bytes],
    deadline: Deadline,
    token: CancellationToken,
    max_output_bytes: int,
) -> bytes:
    """Lit stdout en non-bloquant avec plafond strict ; tue au dépassement."""
    assert process.stdout is not None
    descriptor = process.stdout.fileno()
    chunks: list[bytes] = []
    total = 0
    while True:
        token.throw_if_cancelled()
        remaining = deadline.remaining()
        if remaining <= 0:
            deadline.check()
        try:
            ready, _, _ = select.select([descriptor], [], [], min(0.1, max(0.001, remaining)))
        except (OSError, ValueError) as error:
            raise OcrEngineError("Lecture de la sortie OCR impossible.") from error
        if not ready:
            if process.poll() is not None:
                # Processus terminé sans plus de données : consomme le reliquat.
                tail = process.stdout.read()
                if not tail:
                    break
                chunks.append(tail)
                total += len(tail)
                if total > max_output_bytes:
                    raise OcrOutputLimitError("Sortie Tesseract supérieure au plafond : analyse refusée.")
                break
            continue
        chunk = os.read(descriptor, 65536)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_output_bytes:
            _kill_process_group(process)
            raise OcrOutputLimitError("Sortie Tesseract supérieure au plafond : analyse refusée.")
    # Une annulation/échéance pendant la lecture prime sur un EOF provoqué
    # par la récolte du processus : le résultat partiel n'est jamais livré.
    token.throw_if_cancelled()
    if deadline.expired():
        deadline.check()
    return b"".join(chunks)


def make_global_deadline(total_seconds: float = DEFAULT_GLOBAL_DEADLINE_SECONDS) -> Deadline:
    """Échéance globale de 20 s par défaut, hors téléversement (§9)."""
    return Deadline(total_seconds)
