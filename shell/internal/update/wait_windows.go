//go:build windows

package update

import (
	"time"

	"golang.org/x/sys/windows"
)

// WaitExit waits until process pid has ended, at most timeout. It reports
// whether the process is gone.
func WaitExit(pid int, timeout time.Duration) bool {
	if pid <= 0 {
		return true
	}
	h, err := windows.OpenProcess(windows.SYNCHRONIZE, false, uint32(pid))
	if err != nil {
		return true // no such process (any more)
	}
	defer windows.CloseHandle(h)
	ev, err := windows.WaitForSingleObject(h, uint32(timeout/time.Millisecond))
	return err == nil && ev == windows.WAIT_OBJECT_0
}
