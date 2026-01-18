"""Unit tests for single instance enforcement."""

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tmux_dashboard.instance_lock import (
    InstanceLock,
    InstanceLockError,
    LockAcquisitionError,
    LockFileError,
    cleanup_stale_locks,
    ensure_single_instance,
    get_status,
    is_locked,
)


class TestInstanceLock(unittest.TestCase):
    """Test cases for the InstanceLock class."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.lock_file = self.temp_dir / "test_lock"
        self.pid_file = self.temp_dir / "test_pid"
        self.lock = InstanceLock(lock_file=self.lock_file, pid_file=self.pid_file, timeout=1.0)

    def tearDown(self):
        """Clean up test environment."""
        if hasattr(self.lock, '_lock_fd') and self.lock._lock_fd is not None:
            self.lock.release()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_acquire_and_release(self):
        """Test basic lock acquisition and release."""
        self.assertTrue(self.lock.acquire())
        self.assertTrue(self.lock.is_locked())
        self.lock.release()
        self.assertFalse(self.lock.is_locked())

    def test_double_acquire_fails(self):
        """Test that acquiring the same lock twice fails."""
        self.assertTrue(self.lock.acquire())
        lock2 = InstanceLock(lock_file=self.lock_file, pid_file=self.pid_file, timeout=0.1)
        self.assertFalse(lock2.acquire())
        lock2.release()

    def test_context_manager(self):
        """Test context manager functionality."""
        with self.lock:
            self.assertTrue(self.lock.is_locked())
        self.assertFalse(self.lock.is_locked())

    def test_context_manager_exception_handling(self):
        """Test that context manager properly releases lock on exception."""
        try:
            with self.lock:
                self.assertTrue(self.lock.is_locked())
                raise ValueError("Test exception")
        except ValueError:
            pass
        self.assertFalse(self.lock.is_locked())

    @patch('fcntl.flock')
    def test_fcntl_failure_fallback(self, mock_flock):
        """Test fallback to PID file when fcntl fails."""
        mock_flock.side_effect = OSError("fcntl failed")

        lock = InstanceLock(lock_file=self.lock_file, pid_file=self.pid_file, timeout=0.1)
        self.assertTrue(lock.acquire())
        self.assertTrue(lock.is_locked())
        lock.release()

    def test_pid_file_cleanup(self):
        """Test that PID files are cleaned up properly."""
        with self.lock:
            self.assertTrue(self.pid_file.exists())
        self.assertFalse(self.pid_file.exists())

    def test_stale_pid_file_cleanup(self):
        """Test cleanup of stale PID files."""
        # Create a stale PID file
        with open(self.pid_file, 'w') as f:
            f.write('999999\n')  # Non-existent PID

        lock = InstanceLock(lock_file=self.lock_file, pid_file=self.pid_file)
        self.assertTrue(lock.acquire())  # Should succeed after cleanup
        self.assertTrue(lock.is_locked())
        lock.release()

    def test_get_lock_info(self):
        """Test lock information retrieval."""
        info = self.lock.get_lock_info()
        self.assertIn('lock_file', info)
        self.assertIn('pid_file', info)
        self.assertIn('locked', info)
        self.assertIn('our_pid', info)
        self.assertIn('locking_pid', info)

        # After acquiring lock
        self.lock.acquire()
        info = self.lock.get_lock_info()
        self.assertTrue(info['locked'])
        self.assertIsNotNone(info['our_pid'])
        self.lock.release()


class TestEnsureSingleInstance(unittest.TestCase):
    """Test cases for ensure_single_instance function."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.lock_file = self.temp_dir / "test_lock"
        self.pid_file = self.temp_dir / "test_pid"

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('sys.exit')
    def test_ensure_single_instance_blocks_conflict(self, mock_exit):
        """Test that ensure_single_instance blocks when another instance exists."""
        # Acquire lock manually first
        lock1 = InstanceLock(lock_file=self.lock_file, pid_file=self.pid_file)
        self.assertTrue(lock1.acquire())

        # Try to ensure single instance (should block and exit)
        ensure_single_instance(lock_file=self.lock_file, pid_file=self.pid_file, timeout=0.1)
        mock_exit.assert_called_once_with(1)

        lock1.release()

    def test_ensure_single_instance_no_conflict(self):
        """Test that ensure_single_instance succeeds when no conflict exists."""
        # Should succeed without exiting
        with ensure_single_instance(lock_file=self.lock_file, pid_file=self.pid_file, exit_on_conflict=False):
            self.assertTrue(is_locked(lock_file=self.lock_file, pid_file=self.pid_file))

        self.assertFalse(is_locked(lock_file=self.lock_file, pid_file=self.pid_file))

    def test_ensure_single_instance_raises_on_conflict(self):
        """Test that ensure_single_instance raises exception on conflict when configured."""
        # Acquire lock manually first
        lock1 = InstanceLock(lock_file=self.lock_file, pid_file=self.pid_file)
        self.assertTrue(lock1.acquire())

        # Try to ensure single instance (should raise exception)
        with self.assertRaises(LockAcquisitionError):
            ensure_single_instance(
                lock_file=self.lock_file,
                pid_file=self.pid_file,
                timeout=0.1,
                exit_on_conflict=False,
                verbose=False
            )

        lock1.release()


class TestRaceConditions(unittest.TestCase):
    """Test cases for race condition handling."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.lock_file = self.temp_dir / "test_lock"
        self.pid_file = self.temp_dir / "test_pid"

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_concurrent_lock_acquisition(self):
        """Test concurrent lock acquisition - only one should succeed."""
        results = []

        def try_acquire():
            try:
                lock = InstanceLock(lock_file=self.lock_file, pid_file=self.pid_file, timeout=0.5)
                if lock.acquire():
                    results.append("success")
                    time.sleep(0.1)  # Hold lock briefly
                    lock.release()
                else:
                    results.append("failed")
            except Exception:
                results.append("error")

        # Start multiple threads simultaneously
        threads = [threading.Thread(target=try_acquire) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Only one should succeed
        success_count = results.count("success")
        self.assertEqual(success_count, 1, f"Expected 1 success, got {success_count}")

    def test_timeout_handling(self):
        """Test timeout handling when lock cannot be acquired."""
        # Acquire lock first
        lock1 = InstanceLock(lock_file=self.lock_file, pid_file=self.pid_file)
        self.assertTrue(lock1.acquire())

        # Try to acquire with short timeout
        lock2 = InstanceLock(lock_file=self.lock_file, pid_file=self.pid_file, timeout=0.1)
        start_time = time.time()
        result = lock2.acquire()
        end_time = time.time()

        # Should fail and timeout quickly
        self.assertFalse(result)
        self.assertLess(end_time - start_time, 0.5)  # Should timeout quickly

        lock1.release()


class TestCleanupFunctions(unittest.TestCase):
    """Test cases for cleanup utility functions."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.lock_file = self.temp_dir / "test_lock"
        self.pid_file = self.temp_dir / "test_pid"

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cleanup_stale_locks(self):
        """Test cleanup of stale lock files."""
        # Create stale PID file
        with open(self.pid_file, 'w') as f:
            f.write('999999\n')  # Non-existent PID

        # Create stale lock file
        with open(self.lock_file, 'w') as f:
            f.write('stale\n')

        # Cleanup should succeed
        result = cleanup_stale_locks(lock_file=self.lock_file, pid_file=self.pid_file)
        self.assertTrue(result)

        # Files should be cleaned up
        self.assertFalse(self.pid_file.exists())
        self.assertFalse(self.lock_file.exists())

    def test_cleanup_with_active_process(self):
        """Test cleanup when process is still active."""
        # Create PID file with current process ID
        with open(self.pid_file, 'w') as f:
            f.write(f'{os.getpid()}\n')

        # Cleanup should not remove active PID file
        result = cleanup_stale_locks(pid_file=self.pid_file)
        self.assertTrue(result)

        # PID file should still exist
        self.assertTrue(self.pid_file.exists())


class TestStatusFunctions(unittest.TestCase):
    """Test cases for status monitoring functions."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.lock_file = self.temp_dir / "test_lock"
        self.pid_file = self.temp_dir / "test_pid"

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_is_locked_function(self):
        """Test is_locked utility function."""
        # Initially not locked
        self.assertFalse(is_locked(lock_file=self.lock_file, pid_file=self.pid_file))

        # After acquiring lock
        lock = InstanceLock(lock_file=self.lock_file, pid_file=self.pid_file)
        self.assertTrue(lock.acquire())
        self.assertTrue(is_locked(lock_file=self.lock_file, pid_file=self.pid_file))
        lock.release()
        self.assertFalse(is_locked(lock_file=self.lock_file, pid_file=self.pid_file))

    def test_get_status_function(self):
        """Test get_status utility function."""
        status = get_status(lock_file=self.lock_file, pid_file=self.pid_file)
        self.assertIsInstance(status, dict)
        self.assertIn('locked', status)
        self.assertFalse(status['locked'])

        # After acquiring lock
        lock = InstanceLock(lock_file=self.lock_file, pid_file=self.pid_file)
        self.assertTrue(lock.acquire())
        status = get_status(lock_file=self.lock_file, pid_file=self.pid_file)
        self.assertTrue(status['locked'])
        lock.release()


class TestErrorHandling(unittest.TestCase):
    """Test cases for error handling and edge cases."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.lock_file = self.temp_dir / "test_lock"
        self.pid_file = self.temp_dir / "test_pid"

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_lock_file_permission_error(self):
        """Test handling of permission errors."""
        # Make directory read-only
        self.temp_dir.chmod(0o444)

        try:
            lock = InstanceLock(lock_file=self.lock_file, pid_file=self.pid_file)
            # Should handle permission errors gracefully
            result = lock.acquire()
            # May succeed or fail depending on system, but shouldn't crash
        finally:
            # Restore permissions
            self.temp_dir.chmod(0o755)

    def test_exception_hierarchy(self):
        """Test exception class hierarchy."""
        self.assertTrue(issubclass(LockAcquisitionError, InstanceLockError))
        self.assertTrue(issubclass(LockFileError, InstanceLockError))

        # Test raising exceptions
        with self.assertRaises(LockAcquisitionError):
            raise LockAcquisitionError("Test message")

        with self.assertRaises(LockFileError):
            raise LockFileError("Test message")


class TestPerformance(unittest.TestCase):
    """Test cases for performance characteristics."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.lock_file = self.temp_dir / "test_lock"
        self.pid_file = self.temp_dir / "test_pid"

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_lock_acquisition_performance(self):
        """Test that lock acquisition is fast enough."""
        times = []
        lock = InstanceLock(lock_file=self.lock_file, pid_file=self.pid_file)

        # Measure multiple acquisitions
        for _ in range(50):
            start = time.time()
            lock.acquire()
            end = time.time()
            times.append((end - start) * 1000)  # Convert to milliseconds
            lock.release()

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # Performance requirements: < 10ms average, < 50ms max
        self.assertLess(avg_time, 10.0, f"Average lock time too slow: {avg_time:.2f}ms")
        self.assertLess(max_time, 50.0, f"Maximum lock time too slow: {max_time:.2f}ms")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
