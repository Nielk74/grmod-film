//go:build !windows

package update

import (
	"errors"
	"syscall"
	"time"
)

// WaitExit waits until process pid has ended, at most timeout. It reports
// whether the process is gone.
func WaitExit(pid int, timeout time.Duration) bool {
	if pid <= 0 {
		return true
	}
	deadline := time.Now().Add(timeout)
	for {
		err := syscall.Kill(pid, 0)
		if errors.Is(err, syscall.ESRCH) {
			return true
		}
		if time.Now().After(deadline) {
			return false
		}
		time.Sleep(100 * time.Millisecond)
	}
}
