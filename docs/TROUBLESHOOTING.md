# Single Instance Enforcement - Troubleshooting Guide

## Overview

This guide helps diagnose and resolve issues related to the single instance enforcement mechanism in tmux-dashboard.

## Common Issues and Solutions

### ❌ "Another tmux-dashboard instance is already running"

**Problem**: tmux-dashboard won't start because it detects another instance running.

**Diagnosis**:
```bash
# Check if another instance is actually running
python -c "from tmux_dashboard.instance_lock import get_status; print(get_status())"

# Check for tmux-dashboard processes
ps aux | grep tmux_dashboard

# Check lock files
ls -la ~/.local/state/tmux-dashboard/
```

**Solutions**:

1. **Kill the existing instance**:
   ```bash
   # Find the PID from lock file or process list
   cat ~/.local/state/tmux-dashboard/pid
   # Then kill it
   kill <PID>
   ```

2. **Force kill if unresponsive**:
   ```bash
   pkill -f tmux_dashboard
   ```

3. **Clean up stale locks**:
   ```bash
   python -c "from tmux_dashboard.instance_lock import cleanup_stale_locks; cleanup_stale_locks()"
   ```

### 🔒 Lock file permission issues

**Problem**: "Permission denied" when trying to create lock files.

**Diagnosis**:
```bash
# Check directory permissions
ls -ld ~/.local/state/tmux-dashboard/
ls -ld ~/.local/state/

# Check if directory exists
ls -la ~/.local/state/
```

**Solutions**:

1. **Create directory with correct permissions**:
   ```bash
   mkdir -p ~/.local/state/tmux-dashboard
   chmod 755 ~/.local/state/tmux-dashboard
   chmod 755 ~/.local/state
   ```

2. **Fix existing directory permissions**:
   ```bash
   sudo chown $USER:$USER ~/.local/state/tmux-dashboard
   chmod 755 ~/.local/state/tmux-dashboard
   ```

### 🐌 Slow startup or timeouts

**Problem**: tmux-dashboard takes a long time to start or times out.

**Diagnosis**:
```bash
# Check lock file contents
cat ~/.local/state/tmux-dashboard/pid
cat ~/.local/state/tmux-dashboard/lock

# Check if process exists
ps -p $(cat ~/.local/state/tmux-dashboard/pid)
```

**Solutions**:

1. **Clean up stale locks**:
   ```bash
   python -c "from tmux_dashboard.instance_lock import cleanup_stale_locks; cleanup_stale_locks()"
   ```

2. **Check disk I/O**:
   ```bash
   # Check if disk is slow or full
   df -h ~/.local/state
   iostat -x 1 5  # Check I/O stats
   ```

3. **Reduce timeout** (for testing):
   ```python
   from tmux_dashboard.instance_lock import ensure_single_instance
   ensure_single_instance(timeout=2.0)  # 2 second timeout
   ```

### 🚨 "Lock file corruption" or "JSON decode error"

**Problem**: Error messages about corrupted lock files or invalid JSON.

**Diagnosis**:
```bash
# Check lock file contents
cat ~/.local/state/tmux-dashboard/lock
cat ~/.local/state/tmux-dashboard/pid
```

**Solutions**:

1. **Manual cleanup**:
   ```bash
   rm -f ~/.local/state/tmux-dashboard/lock
   rm -f ~/.local/state/tmux-dashboard/pid
   ```

2. **Use cleanup utility**:
   ```bash
   python -c "from tmux_dashboard.instance_lock import cleanup_stale_locks; cleanup_stale_locks()"
   ```

### 🔄 Race condition during startup

**Problem**: Multiple instances sometimes start simultaneously despite locking.

**Diagnosis**:
This usually happens during rapid restarts or when processes are killed abruptly.

**Solutions**:

1. **Wait between restarts**:
   ```bash
   # Kill existing instance
   pkill tmux_dashboard
   # Wait a moment
   sleep 2
   # Start new instance
   tmux-dashboard
   ```

2. **Verify cleanup**:
   ```bash
   # Ensure no lock files remain
   ls -la ~/.local/state/tmux-dashboard/
   # If files exist, remove them
   rm -f ~/.local/state/tmux-dashboard/*
   ```

### 🐧 Windows-specific issues

**Problem**: Locking doesn't work properly on Windows.

**Diagnosis**: Windows doesn't support fcntl locking.

**Solutions**:

1. **PID file fallback should work automatically**, but you can force it:
   ```python
   # Custom lock implementation for Windows
   import sys
   if sys.platform == 'win32':
       # Use PID file only
       lock = InstanceLock(lock_file=None)  # Disable fcntl
   ```

2. **Check antivirus interference**:
   Some antivirus software may interfere with file locking. Add tmux-dashboard to exclusions.

## Debugging Tools

### Lock Status Check

```python
from tmux_dashboard.instance_lock import get_status, is_locked

# Check if locked
if is_locked():
    print("System is locked")
else:
    print("System is not locked")

# Get detailed status
status = get_status()
print(f"Lock file: {status['lock_file']}")
print(f"PID file: {status['pid_file']}")
print(f"Locked: {status['locked']}")
print(f"Our PID: {status['our_pid']}")
print(f"Locking PID: {status['locking_pid']}")
```

### Manual Lock Testing

```python
from tmux_dashboard.instance_lock import InstanceLock

# Test lock acquisition
lock = InstanceLock()
if lock.acquire():
    print("Lock acquired successfully")
    lock.release()
    print("Lock released")
else:
    print("Failed to acquire lock")
```

### Performance Testing

```python
import time
from tmux_dashboard.instance_lock import InstanceLock

# Test lock acquisition time
times = []
for i in range(10):
    lock = InstanceLock()
    start = time.time()
    lock.acquire()
    end = time.time()
    times.append((end - start) * 1000)  # Convert to ms
    lock.release()

avg_time = sum(times) / len(times)
print(f"Average lock time: {avg_time:.2f}ms")
```

## Configuration Options

### Custom Lock Locations

```python
from tmux_dashboard.instance_lock import ensure_single_instance

# Custom lock file paths
ensure_single_instance(
    lock_file="/custom/path/lock",
    pid_file="/custom/path/pid"
)
```

### Timeout Configuration

```python
# Short timeout for quick checks
ensure_single_instance(timeout=1.0)

# Long timeout for slow systems
ensure_single_instance(timeout=30.0)
```

### Verbose Mode

```python
# Enable detailed output
ensure_single_instance(verbose=True)

# Disable output
ensure_single_instance(verbose=False)
```

## Monitoring and Logging

### Health Check Script

```bash
#!/bin/bash
# health_check.sh

python -c "
from tmux_dashboard.instance_lock import is_locked, get_status

if is_locked():
    status = get_status()
    print(f'HEALTH: LOCKED (PID: {status.get(\"locking_pid\")})')
    exit(1)
else:
    print('HEALTH: OK (no active instances)')
    exit(0)
"
```

### Log Integration

```python
import logging
from tmux_dashboard.instance_lock import ensure_single_instance

# Custom logging function
def log_lock_action(level, message):
    logging.log(getattr(logging, level.upper()), message)

# Use with logging
ensure_single_instance(log_function=log_lock_action)
```

## Emergency Procedures

### Force Reset

If the system is completely locked and normal cleanup fails:

```bash
#!/bin/bash
# emergency_reset.sh

echo "Performing emergency lock reset..."

# Kill all tmux-dashboard processes
pkill -f tmux_dashboard || true

# Wait for processes to terminate
sleep 2

# Remove all lock files
rm -f ~/.local/state/tmux-dashboard/lock
rm -f ~/.local/state/tmux-dashboard/pid

# Verify cleanup
if [ -f ~/.local/state/tmux-dashboard/lock ] || [ -f ~/.local/state/tmux-dashboard/pid ]; then
    echo "ERROR: Lock files still exist"
    exit 1
else
    echo "SUCCESS: Lock files cleaned up"
    exit 0
fi
```

### System Recovery

If tmux-dashboard won't start due to persistent issues:

1. **Backup configuration**:
   ```bash
   cp ~/.config/tmux-dashboard/config.json ~/.config/tmux-dashboard/config.json.backup
   ```

2. **Reset configuration**:
   ```bash
   rm ~/.config/tmux-dashboard/config.json
   ```

3. **Clean up all state**:
   ```bash
   rm -rf ~/.local/state/tmux-dashboard/
   ```

4. **Restart tmux-dashboard**:
   ```bash
   tmux-dashboard
   ```

## Prevention Best Practices

### 1. Graceful Shutdown

Always exit tmux-dashboard properly rather than killing processes abruptly.

### 2. Monitor Lock Files

Regularly check for stale lock files in automated scripts:

```bash
# Add to cron or monitoring scripts
if [ -f ~/.local/state/tmux-dashboard/pid ]; then
    PID=$(cat ~/.local/state/tmux-dashboard/pid)
    if ! kill -0 $PID 2>/dev/null; then
        echo "Found stale PID file, cleaning up..."
        rm -f ~/.local/state/tmux-dashboard/pid
    fi
fi
```

### 3. Resource Limits

Ensure adequate disk space and file descriptors:

```bash
# Check disk space
df -h ~/.local/state

# Check file descriptor limits
ulimit -n
```

### 4. Backup Lock Strategy

For critical systems, implement backup lock strategy:

```python
from tmux_dashboard.instance_lock import InstanceLock
import tempfile

# Secondary lock location as backup
backup_lock_dir = tempfile.mkdtemp()
backup_lock = InstanceLock(lock_file=Path(backup_lock_dir) / "lock")

# Try primary, fallback to backup
if not lock.acquire():
    if backup_lock.acquire():
        print("Using backup lock mechanism")
    else:
        print("All lock mechanisms failed")
```

## Getting Help

If you encounter persistent issues:

1. **Collect diagnostic information**:
   ```bash
   echo "=== System Info ==="
   uname -a
   python --version
   echo "=== Lock Status ==="
   python -c "from tmux_dashboard.instance_lock import get_status; print(get_status())"
   echo "=== Process List ==="
   ps aux | grep tmux_dashboard
   echo "=== Lock Files ==="
   ls -la ~/.local/state/tmux-dashboard/
   cat ~/.local/state/tmux-dashboard/pid 2>/dev/null || echo "No PID file"
   ```

2. **Check logs**:
   ```bash
   tail -20 ~/.local/state/tmux-dashboard/log.jsonl
   ```

3. **Test with minimal configuration**:
   ```bash
   TMUX_DASHBOARD_CONFIG=/dev/null tmux-dashboard
   ```

This guide covers the most common issues with single instance enforcement. If problems persist, consult the implementation documentation or create an issue with detailed diagnostic information.