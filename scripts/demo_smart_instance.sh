#!/bin/bash
# Demonstration of smart single instance enforcement
# This shows how SSH sessions can now access tmux sessions normally

echo "=== Smart Single Instance Enforcement Demo ==="
echo ""
echo "This demo shows the improved behavior:"
echo "- SSH sessions can now access existing tmux sessions"
echo "- Only one dashboard UI runs at a time"
echo "- Multiple SSH sessions work normally"
echo ""

# Scenario 1: First SSH session (creates tmux session)
echo "1. First SSH session (would create tmux session):"
python3 -c "
import sys
sys.path.insert(0, 'src')
from tmux_dashboard.instance_lock import InstanceLock
from tmux_dashboard.tmux_manager import TmuxManager

lock = InstanceLock()
if lock.is_locked():
    print('   Another dashboard running - would attach to existing session')
else:
    print('   ✓ No other dashboard - would run normally')
    tmux = TmuxManager()
    sessions = tmux.list_sessions()
    if not sessions:
        print('   ✓ No sessions - would auto-create one')
    else:
        print(f'   ✓ Found {len(sessions)} session(s)')
"
echo ""

# Scenario 2: Second SSH session (accesses existing session)
echo "2. Second SSH session (accesses existing tmux session):"
python3 -c "
import sys
sys.path.insert(0, 'src')
from tmux_dashboard.instance_lock import InstanceLock
from tmux_dashboard.tmux_manager import TmuxManager

lock = InstanceLock()
if lock.is_locked():
    print('   ✓ Another dashboard instance detected')
    print('   ✓ Checking for tmux sessions...')

    tmux = TmuxManager()
    try:
        sessions = tmux.list_sessions()
        if sessions:
            print(f'   ✓ Found {len(sessions)} tmux session(s)')
            print(f'   ✓ Would attach to: {sessions[0].name}')
            print('   ✓ SSH session would work normally!')
        else:
            print('   ✓ No sessions - would exit cleanly')
    except Exception as e:
        print(f'   Error: {e}')
else:
    print('   No other dashboard - would run normally')
"
echo ""

# Scenario 3: Show the benefit
echo "3. Benefits of smart instance handling:"
echo ""
echo "   ✓ SSH sessions can now connect normally"
echo "   ✓ Existing tmux sessions are accessible"
echo "   ✓ Only one dashboard UI prevents conflicts"
echo "   ✓ No more blocking of SSH connections"
echo ""

echo "=== How It Works ==="
echo ""
echo "When tmux-dashboard starts:"
echo "  1. Check if another dashboard is running"
echo "  2. If another dashboard exists:"
echo "     - Check if tmux has sessions"
echo "     - If sessions exist: attach to the most recent one"
echo "     - If no sessions: exit cleanly"
echo "  3. If no other dashboard:"
echo "     - Run normally with single instance enforcement"
echo ""

echo "=== Result ==="
echo ""
echo "Before: SSH sessions were blocked, causing frustration"
echo "After:  SSH sessions work normally, tmux sessions accessible"
echo ""

python3 -c "
import sys
sys.path.insert(0, 'src')
from tmux_dashboard.instance_lock import InstanceLock

lock = InstanceLock()
info = lock.get_lock_info()
print('Current lock status:')
print(f'  Locked: {info[\"locked\"]}')
print(f'  Lock file: {info[\"lock_file\"]}')
if info.get('locking_pid'):
    print(f'  Locking PID: {info[\"locking_pid\"]}')
"