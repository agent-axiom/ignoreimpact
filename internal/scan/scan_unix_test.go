//go:build !windows

package scan

import (
	"context"
	"os"
	"path/filepath"
	"syscall"
	"testing"

	"github.com/agent-axiom/ignoreimpact/internal/policy"
)

func TestSpecialFileRejectedUnlessExcluded(t *testing.T) {
	dir := t.TempDir()
	if err := syscall.Mkfifo(filepath.Join(dir, "pipe"), 0600); err != nil {
		t.Fatal(err)
	}
	root, err := os.OpenRoot(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer root.Close()
	if _, err = Compare(context.Background(), root, policy.Empty(), policy.Empty(), Defaults()); err == nil {
		t.Fatal("accepted included FIFO")
	}
	if _, err = Compare(context.Background(), root, parse(t, "pipe"), parse(t, "pipe"), Defaults()); err != nil {
		t.Fatal(err)
	}
	if _, err = policy.LoadExplicit(filepath.Join(dir, "pipe")); err == nil {
		t.Fatal("accepted FIFO policy")
	}
}

func TestHardLinksCountPerPath(t *testing.T) {
	dir := t.TempDir()
	first := filepath.Join(dir, "a")
	if err := os.WriteFile(first, []byte("abc"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Link(first, filepath.Join(dir, "b")); err != nil {
		t.Fatal(err)
	}
	root, err := os.OpenRoot(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer root.Close()
	r, err := Compare(context.Background(), root, policy.Empty(), policy.Empty(), Defaults())
	if err != nil {
		t.Fatal(err)
	}
	if r.After.Bytes != 6 || r.After.Files != 2 {
		t.Fatalf("incorrect hard-link accounting: %+v", r.After)
	}
}

func TestUnreadableExcludedDirectoryFailsClosed(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root can read chmod-000 directories")
	}
	dir := t.TempDir()
	denied := filepath.Join(dir, "denied")
	if err := os.Mkdir(denied, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(denied, 0); err != nil {
		t.Fatal(err)
	}
	defer os.Chmod(denied, 0700)
	root, err := os.OpenRoot(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer root.Close()
	p := parse(t, "denied")
	if r, err := Compare(context.Background(), root, p, p, Defaults()); err == nil || r != nil {
		t.Fatal("silently accepted an unreadable subtree")
	}
}
