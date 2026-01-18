"""Process locking for single tmux-dashboard instance.

This module provides file-based locking mechanisms to ensure only one
tmux-dashboard instance runs at a time, preventing race conditions and
concurrent access conflicts.

Implementation follows the Singleton Pattern for process management.

Author: Tmux Dashboard Team
Created: 2026-01-16
"""

from __future__ import annotations

import errno
import fcntl
import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional

# Lock file location
DEFAULT_LOCK_FILE = Path.home() / ".local" / "state" / "tmux-dashboard" / "lock"
DEFAULT_PID_FILE = Path.home() / ".local" / "state" / "tmux-dashboard" / "pid"
_PROCESS_LOCK = threading.Lock()
_PROCESS_LOCK_HELD = False


class InstanceLockError(Exception):
    """Base exception for instance locking errors."""
    pass


class LockAcquisitionError(InstanceLockError):
    """Raised when unable to acquire the instance lock."""
    pass


class LockFileError(InstanceLockError):
    """Raised when there's an error with the lock file."""
    pass


class InstanceLock:
    """File-based lock to prevent multiple tmux-dashboard instances.

    Uses both file locking (fcntl) and PID file mechanisms for robustness
    across different operating systems and file systems.

    Attributes:
        lock_file: Path to the lock file
        pid_file: Path to the PID file (optional fallback)
        _lock_fd: File descriptor for the lock file
        _pid: Process ID of the locking process
    """

    def __init__(
        self,
        lock_file: Optional[Path] = None,
        pid_file: Optional[Path] = None,
        timeout: float = 5.0
    ) -> None:
        """Initialize the instance lock.

        Args:
            lock_file: Path to the lock file (defaults to ~/.local/state/tmux-dashboard/lock)
            pid_file: Path to the PID file (defaults to ~/.local/state/tmux-dashboard/pid)
            timeout: Maximum time to wait for lock acquisition in seconds
        """
        self.lock_file = lock_file or DEFAULT_LOCK_FILE
        self.pid_file = pid_file or DEFAULT_PID_FILE
        self.timeout = timeout
        self._lock_fd: Optional[int] = None
        self._pid: Optional[int] = None
        self._lock = threading.RLock()  # Internal thread safety
        self._process_lock_acquired = False

        # Ensure directories exist
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)

    def acquire(self) -> bool:
        """Try to acquire the lock. Returns True if successful.

        Uses a two-phase approach:
        1. Try file locking (fcntl) - most reliable
        2. Fallback to PID file check - for systems without fcntl

        Returns:
            bool: True if lock was acquired, False otherwise
        """
        with self._lock:
            if self._lock_fd is not None:
                return True  # Already locked

            start_time = time.monotonic()
            sleep_interval = 0.05
            acquired = False

            if not self._acquire_process_lock():
                return False

            try:
                while True:
                    fcntl_result = self._try_fcntl_lock()
                    if fcntl_result is True:
                        self._write_pid_file()
                        acquired = True
                        self._mark_process_lock_held(True)
                        return True
                    if fcntl_result is False:
                        if time.monotonic() - start_time >= self.timeout:
                            return False
                        time.sleep(min(sleep_interval, max(0.0, self.timeout - (time.monotonic() - start_time))))
                        continue

                    # Phase 2: Fallback to PID file method
                    if self._try_pid_file_lock():
                        acquired = True
                        self._mark_process_lock_held(True)
                        return True

                    if time.monotonic() - start_time >= self.timeout:
                        return False

                    time.sleep(min(sleep_interval, max(0.0, self.timeout - (time.monotonic() - start_time))))
            finally:
                if not acquired:
                    self._release_process_lock()

    def _acquire_process_lock(self) -> bool:
        if self._process_lock_acquired:
            return True
        acquired = _PROCESS_LOCK.acquire(blocking=False)
        self._process_lock_acquired = acquired
        return acquired

    def _release_process_lock(self) -> None:
        if not self._process_lock_acquired:
            return
        try:
            _PROCESS_LOCK.release()
        except RuntimeError:
            pass
        self._process_lock_acquired = False

    def _mark_process_lock_held(self, held: bool) -> None:
        global _PROCESS_LOCK_HELD
        _PROCESS_LOCK_HELD = held

    def _try_fcntl_lock(self) -> Optional[bool]:
        """Try to acquire lock using fcntl (Unix file locking).

        Returns:
            True if acquired, False if another process holds the lock,
            None if fcntl locking is unavailable and PID fallback should be used.
        """
        try:
            self._lock_fd = os.open(
                self.lock_file,
                os.O_CREAT | os.O_WRONLY | os.O_TRUNC
            )
        except OSError:
            self._cleanup_lock_fd()
            return None

        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._pid = os.getpid()
            os.write(self._lock_fd, str(self._pid).encode() + b"\n")
            return True
        except (BlockingIOError, OSError) as exc:
            self._cleanup_lock_fd()
            if isinstance(exc, BlockingIOError) or getattr(exc, "errno", None) in {errno.EACCES, errno.EAGAIN}:
                return False
            return None
        except Exception as exc:
            # Unexpected error - clean up and raise
            self._cleanup_lock_fd()
            raise LockFileError(f"Unexpected error during fcntl lock: {exc}") from exc

    def _write_pid_file(self) -> bool:
        """Write the current PID file. Returns True if successful."""
        try:
            self._pid = os.getpid()
            self.pid_file.write_text(str(self._pid))
            return True
        except OSError:
            return False

    def _try_pid_file_lock(self) -> bool:
        """Fallback method using PID file to detect running instances."""
        try:
            if self.pid_file.exists():
                try:
                    pid_content = self.pid_file.read_text().strip()
                    if not pid_content:
                        self.pid_file.unlink(missing_ok=True)
                        return False

                    pid = int(pid_content)
                    # Check if process exists
                    try:
                        os.kill(pid, 0)  # Signal 0 just checks if process exists
                    except ProcessLookupError:
                        self.pid_file.unlink(missing_ok=True)
                        pid = 0
                    except PermissionError:
                        return False

                    if pid:
                        return False  # Another process owns the lock

                except (ValueError, OSError):
                    # Process doesn't exist or we can't check it
                    # Remove stale PID file if possible
                    self.pid_file.unlink(missing_ok=True)

            # Create new PID file
            return self._write_pid_file()

        except OSError:
            return False
        except Exception as exc:
            raise LockFileError(f"Error during PID file lock: {exc}") from exc

    def release(self) -> None:
        """Release the lock and clean up lock files."""
        with self._lock:
            if self._lock_fd is not None:
                try:
                    fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                    os.close(self._lock_fd)
                except OSError:
                    pass
                self._lock_fd = None

            # Clean up PID file
            try:
                if self.pid_file.exists():
                    # Only remove if it contains our PID
                    try:
                        if self.pid_file.read_text().strip() == str(os.getpid()):
                            self.pid_file.unlink()
                    except (OSError, ValueError):
                        pass
            except Exception:
                pass

            self._pid = None
            if self._process_lock_acquired:
                self._mark_process_lock_held(False)
                self._release_process_lock()

    def is_locked(self) -> bool:
        """Check if the lock is currently held by any process."""
        with self._lock:
            if _PROCESS_LOCK_HELD:
                return True
            if self._lock_fd is not None:
                return True

            # Check if lock file exists and is locked
            try:
                with open(self.lock_file, "r") as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    return False  # We can lock it, so it's not locked
            except FileNotFoundError:
                return False
            except (BlockingIOError, OSError) as exc:
                if isinstance(exc, BlockingIOError) or getattr(exc, "errno", None) in {errno.EACCES, errno.EAGAIN}:
                    return True  # File is locked by another process
                # Fallback to PID file check for unsupported locking
            except Exception:
                pass

            # Fallback to PID file check
            if self.pid_file.exists():
                try:
                    pid = int(self.pid_file.read_text().strip())
                    os.kill(pid, 0)
                    return True
                except (ProcessLookupError, ValueError):
                    return False
                except PermissionError:
                    return True
            return False

    def get_lock_info(self) -> dict[str, Optional[str]]:
        """Get information about the current lock state.

        Returns:
            dict: Lock information including PID and lock file status
        """
        info = {
            "lock_file": str(self.lock_file),
            "pid_file": str(self.pid_file),
            "locked": self.is_locked(),
            "our_pid": str(self._pid) if self._pid else None,
        }

        # Try to get information about the locking process
        try:
            if self.lock_file.exists():
                with open(self.lock_file, "r") as f:
                    content = f.read().strip()
                    if content:
                        info["locking_pid"] = content
                    else:
                        info["locking_pid"] = None
            elif self.pid_file.exists():
                info["locking_pid"] = self.pid_file.read_text().strip()
            else:
                info["locking_pid"] = None
        except Exception:
            info["locking_pid"] = None

        return info

    def _cleanup_lock_fd(self) -> None:
        """Clean up the lock file descriptor if it exists."""
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None

    def __enter__(self) -> InstanceLock:
        """Context manager entry."""
        if not self.acquire():
            raise LockAcquisitionError("Could not acquire instance lock")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.release()


def ensure_single_instance(
    lock_file: Optional[Path] = None,
    pid_file: Optional[Path] = None,
    timeout: float = 5.0,
    exit_on_conflict: bool = True,
    verbose: bool = True
) -> InstanceLock:
    """Ensure only one tmux-dashboard instance runs.

    Args:
        lock_file: Custom lock file path
        pid_file: Custom PID file path
        timeout: Maximum time to wait for lock in seconds
        exit_on_conflict: If True, exit with error code 1 when another instance is running
        verbose: If True, print status messages

    Returns:
        InstanceLock: The acquired lock

    Raises:
        LockAcquisitionError: If unable to acquire lock and exit_on_conflict is False
    """
    lock = InstanceLock(lock_file=lock_file, pid_file=pid_file, timeout=timeout)

    if not lock.acquire():
        if verbose:
            print("❌ Another tmux-dashboard instance is already running.", file=sys.stderr)
            print(f"   Lock file: {lock.lock_file}", file=sys.stderr)
            print(f"   PID file: {lock.pid_file}", file=sys.stderr)

            # Try to provide more information about the running instance
            try:
                lock_info = lock.get_lock_info()
                if lock_info.get("locking_pid"):
                    print(f"   PID: {lock_info['locking_pid']}", file=sys.stderr)
            except Exception:
                pass

            print("\nTo kill the existing instance, you can use:", file=sys.stderr)
            print("  kill <PID>  # Replace <PID> with the process ID shown above", file=sys.stderr)

        if exit_on_conflict:
            sys.exit(1)
        else:
            raise LockAcquisitionError("Another tmux-dashboard instance is running")

    if verbose:
        print(f"🔒 tmux-dashboard instance lock acquired (PID: {os.getpid()})")

    return lock


def cleanup_stale_locks(lock_file: Optional[Path] = None, pid_file: Optional[Path] = None) -> bool:
    """Clean up stale lock files from crashed instances.

    Args:
        lock_file: Path to lock file to clean up
        pid_file: Path to PID file to clean up

    Returns:
        bool: True if cleanup was successful, False otherwise
    """
    lock_file = lock_file or DEFAULT_LOCK_FILE
    pid_file = pid_file or DEFAULT_PID_FILE

    cleanup_successful = True

    # Clean up PID file if process doesn't exist
    if pid_file.exists():
        try:
            pid_content = pid_file.read_text().strip()
            if pid_content:
                pid = int(pid_content)
                try:
                    os.kill(pid, 0)  # Check if process exists
                except ProcessLookupError:
                    # Process doesn't exist, remove stale PID file
                    pid_file.unlink()
                    print(f"🧹 Removed stale PID file: {pid_file}")
        except (ValueError, OSError):
            cleanup_successful = False

    # Clean up lock file if it exists but isn't locked
    if lock_file.exists():
        try:
            with open(lock_file, "r") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                # File wasn't locked, remove it
                lock_file.unlink()
                print(f"🧹 Removed stale lock file: {lock_file}")
        except (IOError, OSError):
            # File is locked by another process, leave it
            pass
        except Exception:
            cleanup_successful = False

    return cleanup_successful


# Module-level convenience functions
def is_locked(lock_file: Optional[Path] = None, pid_file: Optional[Path] = None) -> bool:
    """Check if tmux-dashboard is currently locked (another instance running)."""
    lock = InstanceLock(lock_file=lock_file, pid_file=pid_file)
    return lock.is_locked()


def get_status(lock_file: Optional[Path] = None, pid_file: Optional[Path] = None) -> dict[str, Optional[str]]:
    """Get the current lock status."""
    lock = InstanceLock(lock_file=lock_file, pid_file=pid_file)
    return lock.get_lock_info()
