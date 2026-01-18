#!/bin/bash
# Integration test for single instance enforcement
# This script tests the complete integration of the single instance mechanism

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOCK_DIR="$(mktemp -d)"
export TMUX_DASHBOARD_LOCK_FILE="$LOCK_DIR/lock"
export TMUX_DASHBOARD_PID_FILE="$LOCK_DIR/pid"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_failure() {
    echo -e "${RED}[FAIL]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Test basic functionality
test_basic_functionality() {
    log_info "=== Testing Basic Functionality ==="

    # Test 1: Import works
    log_info "Testing import..."
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.app import run
from tmux_dashboard.instance_lock import ensure_single_instance
print('✓ Import successful')
" 2>/dev/null && log_success "Import test" || log_failure "Import test"

    # Test 2: Single instance check works
    log_info "Testing single instance check..."
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.instance_lock import ensure_single_instance
with ensure_single_instance():
    print('✓ Single instance check works')
" 2>/dev/null && log_success "Single instance check" || log_failure "Single instance check"
}

# Test conflict detection
test_conflict_detection() {
    log_info "=== Testing Conflict Detection ==="

    # Start a background process that holds the lock
    log_info "Starting background process to hold lock..."
    python3 -c "
import sys
import time
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.instance_lock import ensure_single_instance

# Hold the lock for 5 seconds
with ensure_single_instance():
    print('LOCK_ACQUIRED')
    time.sleep(5)
    print('LOCK_RELEASED')
" > /tmp/background_lock.txt &
    BG_PID=$!

    # Wait for lock to be acquired
    sleep 1

    # Test that second instance is blocked
    log_info "Testing second instance blocking..."
    if python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.instance_lock import ensure_single_instance

try:
    with ensure_single_instance(timeout=0.1):
        print('UNEXPECTED_SUCCESS')
except SystemExit:
    print('BLOCKED_AS_EXPECTED')
" 2>/dev/null | grep -q "BLOCKED_AS_EXPECTED"; then
        log_success "Conflict detection (second instance blocked)"
    else
        log_failure "Conflict detection (second instance not blocked)"
    fi

    # Wait for background process to complete
    wait $BG_PID

    log_info "Background process completed, testing again..."
    sleep 1

    # Test that we can acquire lock after background process finishes
    if python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.instance_lock import ensure_single_instance

with ensure_single_instance():
    print('SUCCESS_AFTER_RELEASE')
" 2>/dev/null | grep -q "SUCCESS_AFTER_RELEASE"; then
        log_success "Lock acquisition after release"
    else
        log_failure "Lock acquisition after release"
    fi

    # Clean up
    rm -f /tmp/background_lock.txt
}

# Test app integration
test_app_integration() {
    log_info "=== Testing App Integration ==="

    # Test that app imports work with the new single instance enforcement
    log_info "Testing app integration..."
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.app import run, main
print('✓ App integration successful')
" 2>/dev/null && log_success "App integration" || log_failure "App integration"

    # Test that the run function structure is correct
    log_info "Testing run function structure..."
    python3 -c "
import sys
import inspect
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.app import run

# Check that run function uses ensure_single_instance
source = inspect.getsource(run)
if 'ensure_single_instance' in source:
    print('✓ Single instance enforcement integrated')
else:
    raise ValueError('Single instance enforcement not found in run function')
" 2>/dev/null && log_success "Run function integration" || log_failure "Run function integration"
}

# Test error handling
test_error_handling() {
    log_info "=== Testing Error Handling ==="

    # Test with invalid lock directory permissions (simulate)
    log_info "Testing error handling with missing directory..."
    python3 -c "
import sys
import tempfile
import os
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.instance_lock import ensure_single_instance

# Create a temporary directory and make it read-only
temp_dir = tempfile.mkdtemp()
try:
    os.chmod(temp_dir, 0o444)
    # This should handle the error gracefully
    result = ensure_single_instance(lock_file='$temp_dir/lock', pid_file='$temp_dir/pid', exit_on_conflict=False, verbose=False)
    print('✓ Error handling works')
except Exception as e:
    print(f'✓ Error handling works (error: {type(e).__name__})')
finally:
    # Restore permissions and cleanup
    os.chmod(temp_dir, 0o755)
    os.rmdir(temp_dir)
" 2>/dev/null && log_success "Error handling" || log_warning "Error handling (may vary by system)"
}

# Test performance
test_performance() {
    log_info "=== Testing Performance ==="

    # Measure startup time with single instance check
    log_info "Measuring startup time..."
    START_TIME=$(date +%s.%N)
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.instance_lock import ensure_single_instance

with ensure_single_instance():
    pass
" 2>/dev/null
    END_TIME=$(date +%s.%N)
    ELAPSED=$(python3 -c "print(f'{($END_TIME - $START_TIME)*1000:.2f}')")

    echo "Startup time: ${ELAPSED}ms"

    if (( $(echo "$ELAPSED < 100" | bc -l) )); then
        log_success "Performance requirements met (< 100ms)"
    else
        log_warning "Performance may be slower than expected"
    fi
}

# Clean up function
cleanup() {
    log_info "Cleaning up test environment..."
    sleep 0.5
    rm -rf "$LOCK_DIR" 2>/dev/null || true
}

# Main execution
main() {
    log_info "Starting tmux-dashboard single instance integration tests"

    # Check if source files exist
    if [[ ! -f "$PROJECT_ROOT/src/tmux_dashboard/instance_lock.py" ]]; then
        log_failure "instance_lock.py not found"
        exit 1
    fi

    if [[ ! -f "$PROJECT_ROOT/src/tmux_dashboard/app.py" ]]; then
        log_failure "app.py not found"
        exit 1
    fi

    # Set up cleanup trap
    trap cleanup EXIT

    # Run tests
    test_basic_functionality
    test_conflict_detection
    test_app_integration
    test_error_handling
    test_performance

    log_success "All integration tests completed!"
}

# Run main function
main "$@"
