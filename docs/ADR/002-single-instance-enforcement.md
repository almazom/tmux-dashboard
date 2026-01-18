# ADR 002: Single Instance Enforcement Pattern

**Date**: 2026-01-16
**Status**: Proposed
**Deciders**: Tmux Dashboard Team
**Participants**: System Architects, DevOps Engineers

## Context

### Problem Statement
The tmux-dashboard application currently lacks process coordination mechanisms, leading to several critical race conditions when multiple instances run simultaneously:

1. **Auto-Create Race Condition**: Multiple instances can simultaneously detect "no sessions exist" and create conflicting sessions
2. **Session Management Conflicts**: Concurrent delete/rename operations can lead to inconsistent state
3. **Configuration Conflicts**: Multiple instances reading/writing config files simultaneously
4. **Logger Race Conditions**: Multiple instances writing to the same log file
5. **Project Name Caching Issues**: Inconsistent project name detection across instances

### Current State Analysis
- No explicit singleton patterns or process coordination
- TmuxManager instances created per application run without coordination
- Configuration changes not synchronized across instances
- No protection against concurrent session management operations
- Project name detection relies on stale cache across instances

### Impact Assessment
- **High**: Auto-create race condition can create duplicate sessions
- **Medium**: Configuration conflicts could corrupt user preferences
- **Medium**: Logger race conditions could corrupt log files
- **Low**: Project name caching inconsistencies (minor user experience impact)

### Constraints
- Must maintain backward compatibility with existing installations
- Should not significantly impact startup time (< 100ms overhead)
- Must work across different operating systems (Linux, macOS, Windows)
- Should handle edge cases like process crashes and SIGKILL termination
- Must not require additional system dependencies

## Decision

Implement a **File-Based Locking Mechanism** with the following characteristics:

### Primary Pattern: File Locking with fcntl
- Use `fcntl.LOCK_EX | fcntl.LOCK_NB` for exclusive, non-blocking file locks
- Primary lock file: `~/.local/state/tmux-dashboard/lock`
- Automatic cleanup when process terminates normally

### Fallback Pattern: PID File Management
- Create PID file with process ID when fcntl unavailable
- Validate PID points to actual tmux-dashboard process
- Clean up stale PID files from crashed instances

### Implementation Strategy
```python
# High-level API
with ensure_single_instance():
    # tmux-dashboard main execution
    run_dashboard()

# Low-level API
lock = InstanceLock()
if lock.acquire():
    try:
        run_dashboard()
    finally:
        lock.release()
```

### Key Components
1. **InstanceLock Class**: Core locking mechanism with thread safety
2. **ensure_single_instance()**: High-level convenience function
3. **Dual-lock approach**: fcntl + PID file for maximum compatibility
4. **Comprehensive error handling**: Graceful degradation and user feedback

## Rationale

### Why File-Based Locking?
1. **Simplicity**: File locks are simple to understand and debug
2. **Reliability**: fcntl locks are automatically released on process termination
3. **Cross-platform**: Works on all Unix-like systems with fallback for Windows
4. **No external dependencies**: Uses standard library only
5. **Atomic operations**: File system provides atomic locking primitives

### Why Not Alternative Approaches?

#### Process Name Checking
- ❌ **Rejected**: Race conditions between process check and startup
- ❌ **Rejected**: Process names can be spoofed or changed
- ❌ **Rejected**: No atomic guarantee against concurrent startup

#### Port-based Locking
- ❌ **Rejected**: Requires network stack, overkill for single-machine use case
- ❌ **Rejected**: Port conflicts with other applications possible
- ❌ **Rejected**: Adds unnecessary complexity and dependencies

#### Database-based Locking
- ❌ **Rejected**: Requires external database dependency
- ❌ **Rejected**: Overkill for single-machine file-based application
- ❌ **Rejected**: Adds complexity and potential failure points

#### Memory-based Locking
- ❌ **Rejected**: Not persistent across process restarts
- ❌ **Rejected**: Cannot detect crashed instances
- ❌ **Rejected**: No coordination between separate Python processes

### Why Dual Approach (fcntl + PID)?
1. **Maximum Compatibility**: Works on systems with and without fcntl
2. **Graceful Degradation**: Falls back to PID file when fcntl unavailable
3. **Robustness**: Multiple layers of protection against different failure modes
4. **Debugging**: PID files provide human-readable debugging information

## Alternatives Considered

### Alternative 1: Process Name Enforcement
**Description**: Check if tmux-dashboard process is already running by name
**Rejected Because**:
- Race condition between check and startup
- Process names can be spoofed
- No atomic guarantee
- Complex process enumeration across platforms

### Alternative 2: Port-based Locking
**Description**: Use TCP port binding to enforce single instance
**Rejected Because**:
- Overkill for local file-based application
- Requires network stack
- Port conflicts with other applications
- Adds unnecessary complexity

### Alternative 3: Database-based Coordination
**Description**: Use SQLite or other database for process coordination
**Rejected Because**:
- External dependency
- Overkill for single-machine use case
- Adds potential failure points
- Performance overhead

### Alternative 4: Signal-based Coordination
**Description**: Use Unix signals to coordinate between instances
**Rejected Because**:
- Complex signal handling
- Race conditions in signal delivery
- Platform-specific implementations
- Difficult to debug

## Consequences

### Positive Consequences

#### ✅ **Race Condition Prevention**
- Eliminates auto-create race condition
- Prevents concurrent session management conflicts
- Ensures configuration consistency
- Protects log file integrity

#### ✅ **Improved Reliability**
- Automatic cleanup on process termination
- Graceful handling of crashed instances
- Comprehensive error reporting and debugging
- Robust fallback mechanisms

#### ✅ **User Experience**
- Clear error messages when another instance is running
- Guidance for killing existing instances
- Fast startup (< 5ms lock acquisition)
- No impact on normal operation

#### ✅ **Operational Benefits**
- Easy debugging with lock file inspection
- Automatic cleanup of stale locks
- Health check capabilities
- Monitoring and metrics integration

### Negative Consequences

#### ⚠️ **Additional Complexity**
- New module to maintain and test
- Additional error conditions to handle
- More complex startup sequence
- Need for cleanup utilities

#### ⚠️ **File System Dependencies**
- Requires writable directory for lock files
- File system permissions must be correct
- NFS and network filesystems may have limitations
- Potential issues with disk space or I/O errors

#### ⚠️ **Platform-Specific Behavior**
- fcntl behavior varies across Unix systems
- Windows requires PID file fallback
- Different file locking semantics on different file systems
- Need for comprehensive testing across platforms

### Mitigation Strategies

#### **Complexity Management**
- Comprehensive unit and integration tests
- Clear API with high-level convenience functions
- Detailed documentation and examples
- Gradual rollout with feature flags

#### **File System Reliability**
- Multiple fallback mechanisms
- Automatic cleanup of stale locks
- Graceful error handling and user guidance
- Disk space and permission checks

#### **Platform Compatibility**
- Dual-lock approach for maximum compatibility
- Platform-specific testing
- Clear documentation of limitations
- Graceful degradation when features unavailable

## Implementation Plan

### Phase 1: Core Implementation (Priority: P1)
1. Create `instance_lock.py` module with core locking functionality
2. Implement `InstanceLock` class with thread safety
3. Add `ensure_single_instance()` convenience function
4. Create comprehensive unit tests

### Phase 2: Integration (Priority: P1)
1. Integrate single instance check into `app.py` main function
2. Update error handling and user feedback
3. Add configuration options for lock file locations
4. Create integration tests for race conditions

### Phase 3: Monitoring and Debugging (Priority: P2)
1. Add lock status API for monitoring
2. Create cleanup utilities for stale locks
3. Enhance logging for lock operations
4. Add health check capabilities

### Phase 4: Documentation and Testing (Priority: P2)
1. Comprehensive documentation (this ADR)
2. User-facing documentation updates
3. Testing documentation and scripts
4. Troubleshooting guide

### Rollout Strategy
1. **Development**: Implement and test in development environment
2. **Staging**: Deploy to staging with monitoring
3. **Production**: Gradual rollout with rollback capability
4. **Monitoring**: Monitor for issues and performance impact

## Success Criteria

### Functional Requirements
- [ ] Only one tmux-dashboard instance can run simultaneously
- [ ] Lock acquisition completes in < 10ms on typical systems
- [ ] Automatic cleanup on process termination
- [ ] Graceful handling of crashed instances
- [ ] Clear error messages for users
- [ ] Cross-platform compatibility (Linux, macOS, Windows)

### Non-Functional Requirements
- [ ] Startup time impact < 100ms
- [ ] Memory overhead < 1KB per instance
- [ ] No additional system dependencies
- [ ] Thread-safe implementation
- [ ] Comprehensive error handling
- [ ] Full backward compatibility

### Testing Requirements
- [ ] Unit tests for all locking scenarios
- [ ] Integration tests for race conditions
- [ ] Cross-platform testing
- [ ] Performance testing for lock acquisition
- [ ] Error condition testing
- [ ] Cleanup and recovery testing

## Review and Approval

### Reviewers
- [ ] System Architect
- [ ] DevOps Engineer
- [ ] Senior Developer
- [ ] QA Engineer

### Approval Criteria
- [ ] All functional requirements met
- [ ] Performance impact acceptable
- [ ] Testing coverage > 90%
- [ ] Documentation complete
- [ ] Rollback plan defined

### Next Review Date
2026-02-16 (1 month after implementation)

## References

- [Single Instance Pattern](https://en.wikipedia.org/wiki/Singleton_pattern)
- [File Locking in Python](https://docs.python.org/3/library/fcntl.html)
- [Process Management Best Practices](https://www.tldp.org/LDP/lpg/node55.html)
- [tmux Dashboard Race Condition Analysis](./docs/single-instance-enforcement.md)