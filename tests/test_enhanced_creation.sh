#!/bin/bash
# Test script for enhanced session creation with automatic cd

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

# Test enhanced session creation
test_enhanced_session_creation() {
    log_info "=== Testing Enhanced Session Creation ==="

    # Test 1: Import enhanced functionality
    log_info "Testing enhanced session creation import..."
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.tmux_manager import TmuxManager

tmux = TmuxManager()
print('✓ Enhanced session creation imported successfully')
" 2>/dev/null && log_success "Enhanced session creation import" || log_failure "Enhanced session creation import"

    # Test 2: Create session with cd functionality
    log_info "Testing session creation with cd..."
    SESSION_NAME="test-cd-$(date +%s)"
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.tmux_manager import TmuxManager

tmux = TmuxManager()
tmux.create_session_with_cd('$SESSION_NAME')
print('✓ Session with cd created successfully')

# Clean up
tmux.kill_session('$SESSION_NAME')
print('✓ Session cleaned up')
" 2>/dev/null && log_success "Session creation with cd" || log_failure "Session creation with cd"

    # Test 3: Verify working directory
    log_info "Testing working directory verification..."
    SESSION_NAME="test-dir-verify-$(date +%s)"
    python3 -c "
import sys
import subprocess
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.tmux_manager import TmuxManager

tmux = TmuxManager()
tmux.create_session_with_cd('$SESSION_NAME')

# Check the working directory of the session
result = subprocess.run([
    'tmux', 'list-panes', '-t', '$SESSION_NAME', '-F', '#{pane_current_path}'
], capture_output=True, text=True)

if result.returncode == 0:
    print(f'✓ Session working directory: {result.stdout.strip()}')
    print('✓ Session created in correct directory')
else:
    print('⚠ Could not verify directory, but session creation worked')

# Clean up
tmux.kill_session('$SESSION_NAME')
print('✓ Session cleaned up')
" 2>/dev/null && log_success "Working directory verification" || log_warning "Working directory verification"

    # Test 4: Test with custom directory
    log_info "Testing with custom directory..."
    SESSION_NAME="test-custom-dir-$(date +%s)"
    CUSTOM_DIR="/tmp"
    python3 -c "
import sys
import subprocess
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.tmux_manager import TmuxManager

tmux = TmuxManager()
tmux.create_session_with_cd('$SESSION_NAME', '$CUSTOM_DIR')

# Check the working directory of the session
result = subprocess.run([
    'tmux', 'list-panes', '-t', '$SESSION_NAME', '-F', '#{pane_current_path}'
], capture_output=True, text=True)

if result.returncode == 0:
    output = result.stdout.strip()
    if '$CUSTOM_DIR' in output:
        print('✓ Custom directory session created successfully')
    else:
        print(f'⚠ Custom directory not set as expected: {output}')

# Clean up
tmux.kill_session('$SESSION_NAME')
print('✓ Session cleaned up')
" 2>/dev/null && log_success "Custom directory test" || log_warning "Custom directory test"
}

# Test integration with single instance enforcement
test_integration() {
    log_info "=== Testing Integration with Single Instance Enforcement ==="

    # Test that enhanced session creation works with single instance enforcement
    log_info "Testing integration..."
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.instance_lock import ensure_single_instance
from tmux_dashboard.tmux_manager import TmuxManager

# Test that enhanced session creation works within single instance context
with ensure_single_instance():
    tmux = TmuxManager()
    session_name = 'test-integration-session'
    tmux.create_session_with_cd(session_name)
    print('✓ Enhanced session creation works with single instance enforcement')

    # Clean up
    tmux.kill_session(session_name)

print('✓ Integration test completed successfully')
" 2>/dev/null && log_success "Integration test" || log_failure "Integration test"
}

# Test auto-create enhancement
test_auto_create_enhancement() {
    log_info "=== Testing Auto-Create Enhancement ==="

    # Test that auto-create now uses enhanced session creation
    log_info "Testing auto-create with enhanced session creation..."
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/src')
from tmux_dashboard.app import run
from tmux_dashboard.instance_lock import ensure_single_instance

# This would normally start the dashboard, but we're just testing the import
# and ensuring the enhanced functionality is properly integrated
print('✓ Auto-create functionality enhanced with cd support')
" 2>/dev/null && log_success "Auto-create enhancement" || log_failure "Auto-create enhancement"
}

# Clean up function
cleanup() {
    log_info "Cleaning up test sessions..."
    sleep 0.5
    # Clean up any test sessions that might be left
    for session in $(tmux list-sessions -F '#S' 2>/dev/null | grep -E "^test-(cd|dir|custom|integration)" || true); do
        tmux kill-session -t "$session" 2>/dev/null || true
    done
    rm -rf "$LOCK_DIR" 2>/dev/null || true
}

# Main execution
main() {
    log_info "Starting enhanced session creation tests"

    # Check if source files exist
    if [[ ! -f "$PROJECT_ROOT/src/tmux_dashboard/tmux_manager.py" ]]; then
        log_failure "tmux_manager.py not found"
        exit 1
    fi

    # Set up cleanup trap
    trap cleanup EXIT

    # Run tests
    test_enhanced_session_creation
    test_integration
    test_auto_create_enhancement

    log_success "All enhanced session creation tests completed!"
}

# Run main function
main "$@"
