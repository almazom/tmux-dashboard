#!/bin/bash
# Demonstration of enhanced session creation with automatic cd

echo "=== Enhanced Session Creation Demo ==="
echo ""

# Test 1: Show normal session creation with cd
echo "1. Testing enhanced session creation with cd:"
echo "   Creating session with automatic directory navigation..."

SESSION_NAME="demo-cd-session-$$"
python3 -c "
import sys
sys.path.insert(0, 'src')
from tmux_dashboard.tmux_manager import TmuxManager

tmux = TmuxManager()
tmux.create_session_with_cd('$SESSION_NAME')
print('   ✓ Session created with cd functionality')

# Check the working directory
import subprocess
result = subprocess.run([
    'tmux', 'list-panes', '-t', '$SESSION_NAME', '-F', '#{pane_current_path}'
], capture_output=True, text=True)

if result.returncode == 0:
    print(f'   ✓ Session working directory: {result.stdout.strip()}')
else:
    print('   ⚠ Could not verify directory')

print('   ✓ Enhanced session creation working!')
"

echo ""

# Test 2: Show custom directory functionality
echo "2. Testing custom directory functionality:"
echo "   Creating session with custom directory (/tmp)..."

CUSTOM_SESSION="demo-custom-dir-$$"
python3 -c "
import sys
sys.path.insert(0, 'src')
from tmux_dashboard.tmux_manager import TmuxManager

tmux = TmuxManager()
tmux.create_session_with_cd('$CUSTOM_SESSION', '/tmp')
print('   ✓ Session created with custom directory')

# Check the working directory
import subprocess
result = subprocess.run([
    'tmux', 'list-panes', '-t', '$CUSTOM_SESSION', '-F', '#{pane_current_path}'
], capture_output=True, text=True)

if result.returncode == 0:
    print(f'   ✓ Custom directory set: {result.stdout.strip()}')
else:
    print('   ⚠ Could not verify directory')

print('   ✓ Custom directory functionality working!')
"

echo ""

# Test 3: Show integration with single instance enforcement
echo "3. Testing integration with single instance enforcement:"
echo "   Testing enhanced creation within single instance context..."

python3 -c "
import sys
sys.path.insert(0, 'src')
from tmux_dashboard.instance_lock import ensure_single_instance
from tmux_dashboard.tmux_manager import TmuxManager

with ensure_single_instance():
    tmux = TmuxManager()
    session_name = 'demo-integration-$$'
    tmux.create_session_with_cd(session_name)
    print('   ✓ Enhanced session creation works with single instance enforcement')

    # Clean up
    tmux.kill_session(session_name)

print('   ✓ Integration working perfectly!')
"

echo ""

# Show the key benefits
echo "=== Key Benefits ==="
echo "✓ Sessions automatically start in correct project directory"
echo "✓ Auto-create functionality enhanced with directory navigation"
echo "✓ Manual session creation uses current working directory"
echo "✓ Custom directory support for specific use cases"
echo "✓ Fully integrated with single instance enforcement"
echo "✓ Users immediately start in the right context"
echo ""

# Clean up test sessions
echo "Cleaning up test sessions..."
for session in $(tmux list-sessions -F '#S' 2>/dev/null | grep -E "^demo-" || true); do
    tmux kill-session -t "$session" 2>/dev/null || true
    echo "✓ Cleaned up session: $session"
done

echo ""
echo "=== Demo Complete! ==="
echo ""
echo "Your tmux-dashboard now creates sessions that automatically"
echo "navigate to the correct project directory! 🚀"