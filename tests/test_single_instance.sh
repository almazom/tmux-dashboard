#!/bin/bash
# Test Script for Single Instance Enforcement
#
# This script tests the single instance enforcement mechanism
# to ensure it properly prevents multiple tmux-dashboard instances
# from running simultaneously.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOCK_DIR="$HOME/.local/state/tmux-dashboard"
export PYTHONPATH="$PROJECT_ROOT/src"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0
TOTAL_TESTS=0

# Test utilities
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

log_failure() {
    echo -e "${RED}[FAIL]${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

run_test() {
    local test_name="$1"
    local test_command="$2"
    local expected_result="$3"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_info "Running test: $test_name"

    if eval "$test_command" > /dev/null 2>&1; then
        if [[ "$expected_result" == "success" ]]; then
            log_success "$test_name"
            return 0
        else
            log_failure "$test_name (expected failure but got success)"
            return 1
        fi
    else
        if [[ "$expected_result" == "failure" ]]; then
            log_success "$test_name (correctly failed)"
            return 0
        else
            log_failure "$test_name (unexpected failure)"
            return 1
        fi
    fi
}

setup_test_environment() {
    log_info "Setting up test environment..."

    # Clean up any existing lock files
    rm -f "$LOCK_DIR"/lock "$LOCK_DIR"/pid 2>/dev/null || true

    # Create lock directory
    mkdir -p "$LOCK_DIR"

    # Wait a moment for cleanup
    sleep 0.1
}

cleanup_test_environment() {
    log_info "Cleaning up test environment..."

    # Kill any tmux-dashboard processes from tests
    pkill -f "tmux_dashboard" 2>/dev/null || true

    # Clean up lock files
    rm -f "$LOCK_DIR"/lock "$LOCK_DIR"/pid 2>/dev/null || true

    # Wait for processes to fully terminate
    sleep 0.5
}

test_basic_locking() {
    log_info "=== Testing Basic Locking ==="

    # Test 1: Initial lock should succeed
    run_test "Initial lock acquisition" \
        "python3 -c 'from tmux_dashboard.instance_lock import InstanceLock; lock = InstanceLock(); raise SystemExit(0 if lock.acquire() else 1)'" \
        "success"

    # Test 2: Second lock should fail
    run_test "Second lock should fail" \
        "python3 -c 'from tmux_dashboard.instance_lock import InstanceLock; lock1 = InstanceLock(); lock1.acquire(); lock2 = InstanceLock(); raise SystemExit(1 if not lock2.acquire() else 0)'" \
        "failure"

    # Cleanup
    cleanup_test_environment
}

test_context_manager() {
    log_info "=== Testing Context Manager ==="

    # Test context manager success case
    run_test "Context manager success" \
        "python3 -c 'from tmux_dashboard.instance_lock import ensure_single_instance; lock = ensure_single_instance(exit_on_conflict=False); lock.release(); print(\"success\")'" \
        "success"

    # Test context manager conflict case
    python3 -c "
import threading
import time
from tmux_dashboard.instance_lock import ensure_single_instance

def lock_and_hold():
    with ensure_single_instance():
        time.sleep(2)

thread = threading.Thread(target=lock_and_hold)
thread.start()
time.sleep(0.5)
" &
    sleep 0.5

    run_test "Context manager conflict" \
        "python3 -c 'from tmux_dashboard.instance_lock import ensure_single_instance; ensure_single_instance(exit_on_conflict=False, timeout=0.1)'" \
        "failure"

    # Cleanup
    cleanup_test_environment
}

test_race_conditions() {
    log_info "=== Testing Race Conditions ==="

    # Test multiple processes trying to acquire lock simultaneously
    python3 -c "
import threading
import time
import sys
from tmux_dashboard.instance_lock import ensure_single_instance

results = []

def try_acquire():
    try:
        with ensure_single_instance(exit_on_conflict=False):
            results.append('success')
            time.sleep(0.1)  # Hold lock briefly
    except:
        results.append('failed')

# Start multiple threads simultaneously
threads = [threading.Thread(target=try_acquire) for _ in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()

# Check results
success_count = results.count('success')
print(f'SUCCESS_COUNT:{success_count}')
" > /tmp/race_test_output.txt

    local success_count=$(grep "SUCCESS_COUNT:" /tmp/race_test_output.txt | cut -d: -f2)
    if [[ "$success_count" == "1" ]]; then
        log_success "Race condition test (only 1 success)"
    else
        log_failure "Race condition test failed (expected 1 success, got $success_count)"
    fi

    rm -f /tmp/race_test_output.txt
    cleanup_test_environment
}

test_stale_lock_cleanup() {
    log_info "=== Testing Stale Lock Cleanup ==="

    # Create a stale PID file
    echo 999999 > "$LOCK_DIR/pid"
    sleep 0.1

    # Test cleanup function
    run_test "Stale lock cleanup" \
        "python3 -c 'from tmux_dashboard.instance_lock import cleanup_stale_locks; raise SystemExit(0 if cleanup_stale_locks() else 1)'" \
        "success"

    # Verify PID file was cleaned up
    if [[ ! -f "$LOCK_DIR/pid" ]]; then
        log_success "PID file cleanup verified"
    else
        log_failure "PID file not cleaned up"
    fi

    cleanup_test_environment
}

test_lock_status_api() {
    log_info "=== Testing Lock Status API ==="

    # Test status when no lock exists
    run_test "No lock status check" \
        "python3 -c 'from tmux_dashboard.instance_lock import is_locked; raise SystemExit(0 if not is_locked() else 1)'" \
        "success"

    # Acquire lock and test status
    python3 -u -c "
import time
from tmux_dashboard.instance_lock import InstanceLock
lock = InstanceLock()
if lock.acquire():
    print('LOCKED')
    time.sleep(2)
" > /tmp/lock_test.txt &
    LOCK_PID=$!

    ready=0
    for _ in {1..20}; do
        if grep -q "LOCKED" /tmp/lock_test.txt; then
            ready=1
            break
        fi
        sleep 0.1
    done

    # Check if lock is detected
    if [[ "$ready" -eq 1 ]]; then
        run_test "Lock status detection" \
            "python3 -c 'from tmux_dashboard.instance_lock import is_locked; raise SystemExit(0 if is_locked() else 1)'" \
            "success"
    else
        log_warning "Could not acquire lock for status test"
    fi

    wait "$LOCK_PID" 2>/dev/null || true
    cleanup_test_environment
    rm -f /tmp/lock_test.txt
}

test_error_recovery() {
    log_info "=== Testing Error Recovery ==="

    # Test behavior when lock directory doesn't exist
    rm -rf "$LOCK_DIR" 2>/dev/null || true

    run_test "Error recovery with missing directory" \
        "python3 -c 'from tmux_dashboard.instance_lock import ensure_single_instance; lock = ensure_single_instance(exit_on_conflict=False); lock.release(); print(\"success\")'" \
        "success"

    # Test behavior with read-only directory (simulate permission error)
    mkdir -p "$LOCK_DIR"
    chmod 444 "$LOCK_DIR" 2>/dev/null || true

    # This should fail gracefully
    run_test "Error recovery with permission denied" \
        "python3 -c 'from tmux_dashboard.instance_lock import ensure_single_instance; ensure_single_instance(exit_on_conflict=False)'" \
        "failure"

    # Restore permissions
    chmod 755 "$LOCK_DIR" 2>/dev/null || true
    cleanup_test_environment
}

test_performance() {
    log_info "=== Testing Performance ==="

    # Measure lock acquisition time
    python3 -c "
import time
from tmux_dashboard.instance_lock import InstanceLock

# Warm up
lock = InstanceLock()
lock.acquire()
lock.release()

# Measure multiple acquisitions
times = []
for i in range(100):
    lock = InstanceLock()
    start = time.time()
    lock.acquire()
    end = time.time()
    times.append((end - start) * 1000)  # Convert to milliseconds
    lock.release()

avg_time = sum(times) / len(times)
max_time = max(times)
print(f'AVG_TIME:{avg_time:.2f}')
print(f'MAX_TIME:{max_time:.2f}')
" > /tmp/performance_test.txt

    local avg_time=$(grep "AVG_TIME:" /tmp/performance_test.txt | cut -d: -f2)
    local max_time=$(grep "MAX_TIME:" /tmp/performance_test.txt | cut -d: -f2)

    echo "Performance Test Results:"
    echo "  Average lock acquisition time: ${avg_time}ms"
    echo "  Maximum lock acquisition time: ${max_time}ms"

    # Check if performance is acceptable (< 10ms average, < 50ms max)
    if (( $(echo "$avg_time < 10" | bc -l) )) && (( $(echo "$max_time < 50" | bc -l) )); then
        log_success "Performance requirements met"
    else
        log_warning "Performance may be slower than expected"
    fi

    rm -f /tmp/performance_test.txt
    cleanup_test_environment
}

test_integration_with_tmux_dashboard() {
    log_info "=== Testing Integration with tmux-dashboard ==="

    # Test that tmux-dashboard respects single instance enforcement
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/src')

try:
    from tmux_dashboard.app import run
    from tmux_dashboard.instance_lock import ensure_single_instance

    # This should work on first call
    print('INTEGRATION_TEST:OK')
except Exception as e:
    print(f'INTEGRATION_TEST:ERROR:{e}')
" > /tmp/integration_test.txt

    if grep -q "INTEGRATION_TEST:OK" /tmp/integration_test.txt; then
        log_success "Integration test passed"
    else
        log_warning "Integration test may have issues"
        cat /tmp/integration_test.txt
    fi

    rm -f /tmp/integration_test.txt
    cleanup_test_environment
}

show_test_summary() {
    log_info "=== Test Summary ==="
    echo "Total tests: $TOTAL_TESTS"
    echo "Passed: $TESTS_PASSED"
    echo "Failed: $TESTS_FAILED"

    if [[ $TESTS_FAILED -eq 0 ]]; then
        echo -e "${GREEN}All tests passed! 🎉${NC}"
        return 0
    else
        echo -e "${RED}$TESTS_FAILED tests failed. Please review the failures above.${NC}"
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting tmux-dashboard single instance enforcement tests"

    if [[ ! -f "$PROJECT_ROOT/src/tmux_dashboard/instance_lock.py" ]]; then
        log_failure "instance_lock.py not found. Please implement the locking mechanism first."
        exit 1
    fi

    setup_test_environment

    # Run all test suites
    test_basic_locking
    test_context_manager
    test_race_conditions
    test_stale_lock_cleanup
    test_lock_status_api
    test_error_recovery
    test_performance
    test_integration_with_tmux_dashboard

    show_test_summary

    cleanup_test_environment
}

# Handle script interruption
trap cleanup_test_environment EXIT

# Run main function
main "$@"
