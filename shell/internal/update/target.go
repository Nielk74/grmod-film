package update

import (
	"archive/zip"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"strings"
)

// writable reports whether files can be created and renamed in dir.
func writable(dir string) bool {
	f, err := os.CreateTemp(dir, ".grmod-write-test-*")
	if err != nil {
		return false
	}
	name := f.Name()
	f.Close()
	moved := name + "-moved"
	ok := os.Rename(name, moved) == nil
	os.Remove(name)
	os.Remove(moved)
	return ok
}

// startDetached starts a program and does not wait for it.
func startDetached(name string, args []string) error {
	cmd := exec.Command(name, args...)
	if err := cmd.Start(); err != nil {
		return err
	}
	return cmd.Process.Release()
}

// ------------------------------------------------------------------ file

// FileTarget is a program that is one executable file (Windows, and the
// Linux development build): GRMod.exe is replaced by the download.
//
// A running .exe cannot be overwritten or deleted on Windows, but it can be
// renamed. Swap therefore renames the running program to GRMod.exe.old and
// the download to GRMod.exe; the next start removes GRMod.exe.old.
type FileTarget struct {
	Exe string
	// Launch starts a program; nil starts it detached.
	Launch func(name string, args []string) error
}

func (t *FileTarget) newName() string { return t.Exe + ".new" }
func (t *FileTarget) oldName() string { return t.Exe + ".old" }

func (t *FileTarget) Check() string {
	if !writable(filepath.Dir(t.Exe)) {
		return ReasonReadOnly
	}
	return ""
}

func (t *FileTarget) StageDir() string { return filepath.Dir(t.Exe) }

func (t *FileTarget) Stage(download string) error {
	if err := os.Chmod(download, 0o755); err != nil {
		return err
	}
	os.Remove(t.newName())
	return os.Rename(download, t.newName())
}

func (t *FileTarget) Swap() error {
	if _, err := os.Stat(t.newName()); err != nil {
		return errors.New("no downloaded update to install")
	}
	os.Remove(t.oldName()) // left over, normally already gone
	if err := os.Rename(t.Exe, t.oldName()); err != nil {
		return fmt.Errorf("cannot move the running program aside: %w", err)
	}
	if err := os.Rename(t.newName(), t.Exe); err != nil {
		if e := os.Rename(t.oldName(), t.Exe); e != nil {
			return fmt.Errorf("cannot put the new program in place (%v) nor the old one back: %w", err, e)
		}
		return fmt.Errorf("cannot put the new program in place: %w", err)
	}
	return nil
}

func (t *FileTarget) Relaunch(args []string) error {
	if t.Launch != nil {
		return t.Launch(t.Exe, args)
	}
	return startDetached(t.Exe, args)
}

func (t *FileTarget) Cleanup() {
	os.Remove(t.oldName())
	os.Remove(t.newName())
	if m, _ := filepath.Glob(filepath.Join(filepath.Dir(t.Exe), ".download-*")); len(m) > 0 {
		for _, f := range m {
			os.Remove(f)
		}
	}
}

// ---------------------------------------------------------------- bundle

// BundleTarget is a macOS application bundle (GR Mod.app), replaced by the
// bundle inside the downloaded zip.
//
// A running app's bundle can be moved. Swap renames it to ".GR Mod.app.old"
// in the same folder and moves the unpacked new bundle into its place.
// Files written by the program itself carry no quarantine attribute, so
// Gatekeeper does not stop the new bundle.
type BundleTarget struct {
	// Bundle is the path of the .app folder.
	Bundle string
	// Launch starts a program; nil starts it detached.
	Launch func(name string, args []string) error
}

func (t *BundleTarget) parent() string { return filepath.Dir(t.Bundle) }
func (t *BundleTarget) stageDir() string {
	return filepath.Join(t.parent(), "."+filepath.Base(t.Bundle)+".update")
}
func (t *BundleTarget) staged() string { return filepath.Join(t.stageDir(), "new.app") }
func (t *BundleTarget) oldBundle() string {
	return filepath.Join(t.parent(), "."+filepath.Base(t.Bundle)+".old")
}

// BundleOf returns the .app folder that holds an executable in
// X.app/Contents/MacOS, or "".
func BundleOf(exe string) string {
	dir := filepath.Dir(exe)
	contents := filepath.Dir(dir)
	bundle := filepath.Dir(contents)
	if filepath.Base(dir) == "MacOS" && filepath.Base(contents) == "Contents" && strings.HasSuffix(bundle, ".app") {
		return bundle
	}
	return ""
}

func (t *BundleTarget) Check() string {
	// Gatekeeper runs a quarantined app that was never moved from a
	// randomised read-only copy ("App Translocation").
	if strings.Contains(t.Bundle, "/AppTranslocation/") {
		return ReasonTranslocated
	}
	if !writable(t.parent()) {
		return ReasonReadOnly
	}
	return ""
}

func (t *BundleTarget) StageDir() string { return t.stageDir() }

// Stage unpacks the zip: exactly one top-level X.app folder, regular files
// and folders only, nothing outside it.
func (t *BundleTarget) Stage(download string) error {
	zr, err := zip.OpenReader(download)
	if err != nil {
		return fmt.Errorf("unreadable package: %w", err)
	}
	defer zr.Close()
	dest := t.staged()
	os.RemoveAll(dest)
	if err := os.MkdirAll(dest, 0o755); err != nil {
		return err
	}
	top := ""
	for _, f := range zr.File {
		name := path.Clean(strings.TrimSuffix(f.Name, "/"))
		if name == "." || strings.HasPrefix(name, "/") || strings.HasPrefix(name, "../") || name == ".." || strings.Contains(name, "\\") {
			return fmt.Errorf("unusable entry %q in the package", f.Name)
		}
		first := strings.SplitN(name, "/", 2)[0]
		if top == "" {
			top = first
		}
		if first != top || !strings.HasSuffix(top, ".app") {
			return fmt.Errorf("the package must hold one .app folder")
		}
		rel := strings.TrimPrefix(strings.TrimPrefix(name, top), "/")
		target := filepath.Join(dest, filepath.FromSlash(rel))
		mode := f.Mode()
		switch {
		case mode.IsDir():
			if err := os.MkdirAll(target, 0o755); err != nil {
				return err
			}
		case mode.IsRegular():
			if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
				return err
			}
			perm := os.FileMode(0o644)
			if mode&0o111 != 0 {
				perm = 0o755
			}
			if err := extract(f, target, perm); err != nil {
				return err
			}
		default:
			return fmt.Errorf("unsupported entry %q in the package", f.Name)
		}
	}
	for _, p := range []string{"Contents/Info.plist", "Contents/MacOS"} {
		if _, err := os.Stat(filepath.Join(dest, p)); err != nil {
			return fmt.Errorf("the package is not an application (%s missing)", p)
		}
	}
	return nil
}

func extract(f *zip.File, target string, perm os.FileMode) error {
	rc, err := f.Open()
	if err != nil {
		return err
	}
	defer rc.Close()
	out, err := os.OpenFile(target, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, perm)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, io.LimitReader(rc, maxPackage)); err != nil {
		out.Close()
		return err
	}
	if err := out.Close(); err != nil {
		return err
	}
	return os.Chmod(target, perm)
}

func (t *BundleTarget) Swap() error {
	if _, err := os.Stat(filepath.Join(t.staged(), "Contents", "Info.plist")); err != nil {
		return errors.New("no downloaded update to install")
	}
	os.RemoveAll(t.oldBundle())
	if err := os.Rename(t.Bundle, t.oldBundle()); err != nil {
		return fmt.Errorf("cannot move the running app aside: %w", err)
	}
	if err := os.Rename(t.staged(), t.Bundle); err != nil {
		if e := os.Rename(t.oldBundle(), t.Bundle); e != nil {
			return fmt.Errorf("cannot put the new app in place (%v) nor the old one back: %w", err, e)
		}
		return fmt.Errorf("cannot put the new app in place: %w", err)
	}
	os.RemoveAll(t.stageDir())
	return nil
}

func (t *BundleTarget) Relaunch(args []string) error {
	if t.Launch != nil {
		return t.Launch(t.Bundle, args)
	}
	// -n: a new instance even though this one is still running.
	return startDetached("/usr/bin/open", append([]string{"-n", t.Bundle, "--args"}, args...))
}

func (t *BundleTarget) Cleanup() {
	os.RemoveAll(t.oldBundle())
	os.RemoveAll(t.stageDir())
}
