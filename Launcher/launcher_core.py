from __future__ import annotations

import json
import hashlib
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable


StateCallback = Callable[[str], None]
ErrorCallback = Callable[[str, str], None]


class GameStatus(str, Enum):
    READY = "Ready"
    RUNNING = "Running"
    STOP_REQUESTED = "Stop Requested"
    RUNNING_EXTERNALLY = "Running Externally"
    MISSING_BUILD = "Missing Build"
    MISSING_ROM = "Missing ROM"
    UNSUPPORTED_ROM = "Unsupported ROM revision"
    COMING_SOON = "Coming Soon"


@dataclass(frozen=True)
class GameState:
    status: GameStatus
    executable_ready: bool
    rom_ready: bool
    owned_pid: int | None
    external_pids: tuple[int, ...]
    stop_requested: bool
    last_run_at: datetime | None
    last_exit_code: int | None
    rom_compatible: bool = True

    @property
    def can_launch(self) -> bool:
        return self.status is GameStatus.READY

    @property
    def can_stop(self) -> bool:
        return self.status is GameStatus.RUNNING

    @property
    def can_force_quit(self) -> bool:
        return self.status in {
            GameStatus.RUNNING,
            GameStatus.STOP_REQUESTED,
            GameStatus.RUNNING_EXTERNALLY,
        }


@dataclass(frozen=True)
class GameConfig:
    id: str
    display_name: str
    executable_path: Path | None
    rom_path: Path | None
    working_directory: Path | None
    arguments: tuple[str, ...]
    log_path: Path
    save_folder: Path | None = None
    project_path: Path | None = None
    enabled: bool = True
    extras: dict = field(default_factory=dict)

    @property
    def command(self) -> list[str]:
        if self.executable_path is None:
            raise RuntimeError(f"No native executable is configured for {self.display_name}.")
        if self.rom_path is None:
            raise RuntimeError(f"No ROM is configured for {self.display_name}.")
        if self.working_directory is None:
            raise RuntimeError(f"No working directory is configured for {self.display_name}.")
        replacements = {
            "rom_path": str(self.rom_path),
            "executable_path": str(self.executable_path),
            "working_directory": str(self.working_directory),
        }
        extras = self.extras.get("advanced_arguments", ())
        if isinstance(extras, str):
            extras = shlex.split(extras)
        return [str(self.executable_path), *(arg.format(**replacements) for arg in self.arguments), *map(str, extras)]


def _resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def load_games(config_path: Path) -> list[GameConfig]:
    config_path = config_path.resolve()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    games: list[GameConfig] = []
    required = {"id", "display_name", "executable_path", "rom_path", "working_directory", "arguments", "log_path"}
    for item in data["games"]:
        missing = required - item.keys()
        if missing:
            raise ValueError(f"Game config is missing: {', '.join(sorted(missing))}")
        known = required | {"save_folder", "project_path", "enabled"}
        games.append(
            GameConfig(
                id=item["id"],
                display_name=item["display_name"],
                executable_path=_resolve(config_path.parent, item["executable_path"]) if item["executable_path"] else None,
                rom_path=_resolve(config_path.parent, item["rom_path"]) if item["rom_path"] else None,
                working_directory=_resolve(config_path.parent, item["working_directory"]) if item["working_directory"] else None,
                arguments=tuple(item["arguments"]),
                log_path=_resolve(config_path.parent, item["log_path"]),
                save_folder=_resolve(config_path.parent, item["save_folder"]) if item.get("save_folder") else None,
                project_path=_resolve(config_path.parent, item["project_path"]) if item.get("project_path") else None,
                enabled=bool(item.get("enabled", True)),
                extras={key: value for key, value in item.items() if key not in known},
            )
        )
    return games


def exact_external_pids(executable: Path, exclude: set[int] | None = None) -> list[int]:
    """Return PIDs whose argv[0] resolves to exactly executable (never loose name matching)."""
    target = os.path.realpath(executable)
    excluded = (exclude or set()) | {os.getpid()}
    try:
        listing = subprocess.run(
            ["ps", "-ww", "-axo", "pid=,command="],
            text=True,
            capture_output=True,
            check=True,
            timeout=3,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found: list[int] = []
    for line in listing.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2:
            continue
        try:
            pid = int(fields[0])
        except ValueError:
            continue
        if pid in excluded:
            continue
        command = fields[1]
        # Prefer exact path prefixes, including executable paths containing spaces.
        configured = str(executable)
        if command == target or command.startswith(target + " "):
            argv0 = target
        elif command == configured or command.startswith(configured + " "):
            argv0 = configured
        else:
            argv0 = command.split(maxsplit=1)[0]
        candidate = os.path.realpath(argv0) if os.path.isabs(argv0) else None
        if candidate == target:
            found.append(pid)
        elif Path(argv0).name == executable.name and _actual_executable(pid) == target:
            found.append(pid)
    return found


def _actual_executable(pid: int) -> str | None:
    """Resolve a process image on macOS or /proc systems for conservative matching."""
    if sys.platform == "darwin":
        try:
            import ctypes

            libproc = ctypes.CDLL("/usr/lib/libproc.dylib")
            libproc.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
            libproc.proc_pidpath.restype = ctypes.c_int
            buffer = ctypes.create_string_buffer(4096)
            length = libproc.proc_pidpath(pid, buffer, len(buffer))
            if length > 0:
                return os.path.realpath(buffer.value.decode("utf-8", errors="surrogateescape"))
        except (OSError, ValueError):
            return None
    proc_exe = Path(f"/proc/{pid}/exe")
    try:
        if proc_exe.exists():
            return os.path.realpath(proc_exe)
    except OSError:
        pass
    return None


class ManagedGame:
    def __init__(self, config: GameConfig, on_state: StateCallback, on_error: ErrorCallback):
        self.config = config
        self.on_state = on_state
        self.on_error = on_error
        self.process: subprocess.Popen[bytes] | None = None
        existing_logs = sorted(config.log_path.glob("*.log")) if config.log_path.is_dir() else []
        self.latest_log: Path | None = existing_logs[-1] if existing_logs else None
        self.last_exit_code: int | None = None
        self.last_run_at: datetime | None = None
        self._load_latest_metadata()
        self.external_pids: list[int] = []
        self._lock = threading.RLock()
        self._external_lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._log_file = None
        self._started_at = 0.0
        self._stopping = False

    def _load_latest_metadata(self) -> None:
        if self.latest_log is None:
            return
        try:
            for line in self.latest_log.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("timestamp: "):
                    self.last_run_at = datetime.fromisoformat(line.removeprefix("timestamp: "))
                elif line.startswith("exit_code: "):
                    self.last_exit_code = int(line.removeprefix("exit_code: "))
        except (OSError, ValueError):
            pass

    def is_owned_running(self) -> bool:
        with self._lock:
            return self.process is not None and self.process.poll() is None

    def is_stopping(self) -> bool:
        with self._lock:
            return self._stopping and self.is_owned_running()

    def refresh_external(self) -> list[int]:
        with self._external_lock:
            if self.config.executable_path is None:
                self.external_pids = []
                return []
            owned = {self.process.pid} if self.is_owned_running() and self.process else set()
            self.external_pids = exact_external_pids(self.config.executable_path, owned)
            return list(self.external_pids)

    def state(self, refresh_external: bool = True) -> GameState:
        """Return one coherent UI state derived from live process and file reality."""
        executable_ready = bool(
            self.config.executable_path
            and self.config.executable_path.is_file()
            and os.access(self.config.executable_path, os.X_OK)
        )
        rom_ready = bool(self.config.rom_path and self.config.rom_path.is_file())
        expected_hash = self.config.extras.get("expected_rom_sha256")
        rom_compatible = True
        if rom_ready and expected_hash:
            try:
                rom_compatible = sha256_file(self.config.rom_path) == str(expected_hash).lower()
            except OSError:
                rom_compatible = False
        with self._lock:
            process = self.process
            owned_pid = process.pid if process is not None and process.poll() is None else None
            stop_requested = bool(owned_pid is not None and self._stopping)
            last_run_at = self.last_run_at
            last_exit_code = self.last_exit_code

        if not self.config.enabled:
            external_pids: tuple[int, ...] = ()
            with self._external_lock:
                self.external_pids = []
            status = GameStatus.COMING_SOON
        elif owned_pid is not None:
            external_pids = ()
            with self._external_lock:
                self.external_pids = []
            status = GameStatus.STOP_REQUESTED if stop_requested else GameStatus.RUNNING
        else:
            if refresh_external:
                external_pids = tuple(self.refresh_external())
            else:
                with self._external_lock:
                    external_pids = tuple(self.external_pids)
            if external_pids:
                status = GameStatus.RUNNING_EXTERNALLY
            elif not executable_ready:
                status = GameStatus.MISSING_BUILD
            elif not rom_ready:
                status = GameStatus.MISSING_ROM
            elif not rom_compatible:
                status = GameStatus.UNSUPPORTED_ROM
            else:
                status = GameStatus.READY

        return GameState(
            status=status,
            executable_ready=executable_ready,
            rom_ready=rom_ready,
            owned_pid=owned_pid,
            external_pids=external_pids,
            stop_requested=stop_requested,
            last_run_at=last_run_at,
            last_exit_code=last_exit_code,
            rom_compatible=rom_compatible,
        )

    def launch(self) -> Path:
        with self._lock:
            if not self.config.enabled:
                raise RuntimeError(f"{self.config.display_name} is coming soon; no runnable native build is configured.")
            if self.config.executable_path is None:
                raise FileNotFoundError(f"No native executable is configured for {self.config.display_name}.")
            if self.is_owned_running():
                raise RuntimeError(f"{self.config.display_name} is already running from this launcher.")
            external_pids = self.refresh_external()
            if external_pids:
                raise RuntimeError(f"{self.config.display_name} is already running externally (PID {external_pids[0]}).")
            if not self.config.executable_path.is_file():
                raise FileNotFoundError(f"Executable missing:\n{self.config.executable_path}")
            if not os.access(self.config.executable_path, os.X_OK):
                raise PermissionError(f"Executable is not runnable:\n{self.config.executable_path}")
            if self.config.rom_path is None or not self.config.rom_path.is_file():
                raise FileNotFoundError(f"ROM missing:\n{self.config.rom_path}")
            expected_hash = self.config.extras.get("expected_rom_sha256")
            if expected_hash and sha256_file(self.config.rom_path) != str(expected_hash).lower():
                raise ValueError(f"Unsupported ROM revision for {self.config.display_name}. Select a ROM matching the required revision.")
            if self.config.working_directory is None or not self.config.working_directory.is_dir():
                raise FileNotFoundError(f"Working directory missing:\n{self.config.working_directory}")

            self.config.log_path.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
            self.latest_log = self.config.log_path / f"{stamp}.log"
            self._log_file = self.latest_log.open("w", encoding="utf-8", buffering=1)
            command = self.config.command
            self._write_log(
                "\n".join(
                    [
                        f"timestamp: {datetime.now().astimezone().isoformat()}",
                        f"game: {self.config.display_name}",
                        f"executable: {self.config.executable_path}",
                        f"rom: {self.config.rom_path}",
                        f"working_directory: {self.config.working_directory}",
                        f"command: {shlex.join(command)}",
                    ]
                ) + "\n"
            )
            try:
                self.process = subprocess.Popen(
                    command,
                    cwd=self.config.working_directory,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
            except OSError as exc:
                self._write_log(f"launch_error: {exc}\n")
                self._log_file.close()
                self._log_file = None
                if isinstance(exc, FileNotFoundError) and self.config.executable_path.is_file():
                    raise FileNotFoundError(
                        f"Could not start {self.config.display_name}. A required runtime dependency may be missing.\n\n{exc}"
                    ) from exc
                raise
            except Exception:
                self._log_file.close()
                self._log_file = None
                raise
            self._started_at = time.monotonic()
            self.last_run_at = datetime.now().astimezone()
            self.last_exit_code = None
            self._stopping = False
            self._write_log(f"pid: {self.process.pid}\n--- process output ---\n")
            pumps = []
            for name, pipe in (("stdout", self.process.stdout), ("stderr", self.process.stderr)):
                pump = threading.Thread(target=self._pump, args=(name, pipe), daemon=True)
                pump.start()
                pumps.append(pump)
            threading.Thread(target=self._watch, args=(self.process, pumps), daemon=True).start()
        self.on_state(self.config.id)
        return self.latest_log

    def _write_log(self, text: str) -> None:
        with self._log_lock:
            if self._log_file:
                self._log_file.write(text)
                self._log_file.flush()

    def _pump(self, stream_name: str, pipe) -> None:
        if pipe is None:
            return
        try:
            for raw_line in iter(pipe.readline, b""):
                line = raw_line.decode("utf-8", errors="replace")
                self._write_log(f"[{stream_name}] {line}")
        finally:
            pipe.close()

    def _watch(self, watched_process: subprocess.Popen[bytes], pumps: list[threading.Thread]) -> None:
        return_code = watched_process.wait()
        for pump in pumps:
            pump.join(timeout=1.0)
        elapsed = time.monotonic() - self._started_at
        self._write_log(
            f"--- process exited ---\nexit_code: {return_code}\n"
            f"finished_at: {datetime.now().astimezone().isoformat()}\n"
        )
        with self._lock:
            if self.process is watched_process:
                self.process = None
            if self._log_file:
                self._log_file.close()
                self._log_file = None
            was_stopping = self._stopping
            self.last_exit_code = return_code
            self._stopping = False
        self.on_state(self.config.id)
        if return_code != 0 and elapsed < 2.0 and not was_stopping:
            try:
                tail = self.latest_log.read_text(encoding="utf-8", errors="replace")[-5000:] if self.latest_log else ""
            except OSError:
                tail = ""
            dependency_hint = "A required runtime dependency may be missing.\n\n" if (
                "Library not loaded" in tail or "image not found" in tail or "dyld" in tail
            ) else ""
            self.on_error(
                self.config.id,
                f"{self.config.display_name} exited immediately with code {return_code}.\n\n"
                f"{dependency_hint}See log:\n{self.latest_log}",
            )

    def stop(self, timeout: float = 3.0, force_after: bool = False) -> bool:
        with self._lock:
            process = self.process
            if process is None or process.poll() is not None:
                return True
            self._stopping = True
            pid = process.pid
        self.on_state(self.config.id)
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            if force_after:
                return self.force_quit()
            with self._lock:
                self._stopping = False
            self.on_state(self.config.id)
            self.on_error(self.config.id, f"{self.config.display_name} did not stop within {timeout:g} seconds. Use Force Quit.")
            return False
        except (ProcessLookupError, ChildProcessError):
            return True
        except OSError as exc:
            with self._lock:
                self._stopping = False
            self.on_state(self.config.id)
            self.on_error(self.config.id, f"Could not stop {self.config.display_name}: {exc}")
            return False

    def request_stop(self) -> bool:
        """Record a UI stop request synchronously before termination runs in a worker."""
        with self._lock:
            process = self.process
            if process is None or process.poll() is not None:
                return False
            self._stopping = True
        self.on_state(self.config.id)
        return True

    def force_quit(self) -> bool:
        with self._lock:
            process = self.process
            if process is not None and process.poll() is None:
                self._stopping = True
                self.on_state(self.config.id)
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    process.wait(timeout=2.0)
                    return True
                except (ProcessLookupError, ChildProcessError):
                    return True
                except (OSError, subprocess.TimeoutExpired) as exc:
                    self.on_error(self.config.id, f"Force quit failed for {self.config.display_name}: {exc}")
                    return False

        external_pids = self.refresh_external()
        if not external_pids:
            return True
        failed: list[str] = []
        for pid in external_pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                continue
            except OSError as exc:
                failed.append(f"PID {pid}: {exc}")
        remaining_pids = self.refresh_external()
        if failed or remaining_pids:
            details = "; ".join(failed) or f"still running: {remaining_pids}"
            self.on_error(self.config.id, f"Force quit failed for external {self.config.display_name}: {details}")
            return False
        self.on_state(self.config.id)
        return True


class ProcessManager:
    def __init__(self, games: list[GameConfig], on_state: StateCallback, on_error: ErrorCallback):
        self.games = {game.id: ManagedGame(game, on_state, on_error) for game in games}

    def any_owned_running(self) -> bool:
        return any(game.is_owned_running() for game in self.games.values())

    def stop_all_for_exit(self) -> bool:
        okay = True
        for game in self.games.values():
            if game.is_owned_running() and not game.stop(timeout=3.0, force_after=True):
                okay = False
        return okay


_HASH_CACHE: dict[tuple[str, int, int], str] = {}


def sha256_file(path: Path) -> str:
    stat_result = path.stat()
    key = (str(path.resolve()), stat_result.st_size, stat_result.st_mtime_ns)
    if key not in _HASH_CACHE:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        _HASH_CACHE[key] = digest.hexdigest()
    return _HASH_CACHE[key]
