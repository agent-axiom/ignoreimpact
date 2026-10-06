package scan

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/agent-axiom/ignoreimpact/internal/policy"
)

func parse(t *testing.T, text string) *policy.Policy {
	t.Helper()
	p, err := policy.Parse(strings.NewReader(text), policy.Source{})
	if err != nil {
		t.Fatal(err)
	}
	return p
}
func tree(t *testing.T) *os.Root {
	t.Helper()
	dir := t.TempDir()
	for path, text := range map[string]string{"src/app.go": "app", "vendor/keep.go": "keep", "vendor/no.go": "no", ".hidden": "hidden", "readme.md": "docs"} {
		full := filepath.Join(dir, filepath.FromSlash(path))
		if err := os.MkdirAll(filepath.Dir(full), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(full, []byte(text), 0600); err != nil {
			t.Fatal(err)
		}
	}
	r, err := os.OpenRoot(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { r.Close() })
	return r
}
func TestCompareNegationAndDeterminism(t *testing.T) {
	root := tree(t)
	before := parse(t, "vendor\n.hidden\n")
	after := parse(t, "vendor\n!vendor/keep.go\n*.md\n")
	r, err := Compare(context.Background(), root, before, after, Defaults())
	if err != nil {
		t.Fatal(err)
	}
	if r.Added.Entries != 2 || r.Added.Bytes != 10 || r.Removed.Entries != 1 || r.Removed.Bytes != 4 || r.DeltaBytes != 6 {
		t.Fatalf("bad totals: %+v", r)
	}
	if r.Before.Bytes != 7 || r.After.Bytes != 13 || r.ScannedEntries != 7 {
		t.Fatalf("bad inventory: %+v", r)
	}
	if r.Changes[0].Path != ".hidden" || r.Changes[1].Path != "readme.md" || r.Changes[2].Path != "vendor/keep.go" {
		t.Fatal(r.Changes)
	}
	one, _ := json.Marshal(r)
	r2, err := Compare(context.Background(), root, before, after, Defaults())
	if err != nil {
		t.Fatal(err)
	}
	two, _ := json.Marshal(r2)
	if string(one) != string(two) {
		t.Fatal("nondeterministic report")
	}
}
func TestLimitsAndCancellation(t *testing.T) {
	root := tree(t)
	for _, opts := range []Options{{1, 100, 256}, {100, 1, 256}, {100, 100, 1}, {0, 1, 1}} {
		if r, err := Compare(context.Background(), root, parse(t, "**"), policy.Empty(), opts); err == nil || r != nil {
			t.Fatalf("returned partial/success %+v %v", r, err)
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if r, err := Compare(ctx, root, policy.Empty(), policy.Empty(), Defaults()); err == nil || r != nil {
		t.Fatal("ignored cancellation")
	}
}
func TestSymlinksAndSparseFiles(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("symlink permission varies")
	}
	dir := t.TempDir()
	outside := t.TempDir()
	os.WriteFile(filepath.Join(outside, "secret"), []byte("not part of context"), 0600)
	for _, path := range []string{"link", "broken"} {
		target := outside
		if path == "broken" {
			target = filepath.Join(outside, "absent")
		}
		if err := os.Symlink(target, filepath.Join(dir, path)); err != nil {
			t.Fatal(err)
		}
	}
	f, err := os.Create(filepath.Join(dir, "large"))
	if err != nil {
		t.Fatal(err)
	}
	const size = int64(1) << 40
	if err = f.Truncate(size); err != nil {
		t.Fatal(err)
	}
	f.Close()
	root, err := os.OpenRoot(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer root.Close()
	r, err := Compare(context.Background(), root, parse(t, "**"), policy.Empty(), Defaults())
	if err != nil {
		t.Fatal(err)
	}
	if r.After.Bytes != size || r.After.Files != 1 || r.After.Symlinks != 2 || len(r.Changes) != 3 {
		t.Fatalf("unexpected symlink/sparse accounting: %+v", r)
	}
}
func TestNoChangeStillEmitsEmptyArray(t *testing.T) {
	r, err := Compare(context.Background(), tree(t), policy.Empty(), policy.Empty(), Defaults())
	if err != nil {
		t.Fatal(err)
	}
	data, _ := json.Marshal(r)
	if !strings.Contains(string(data), `"changes":[]`) {
		t.Fatal(string(data))
	}
}

func BenchmarkCompare(b *testing.B) {
	dir := b.TempDir()
	for i := 0; i < 1000; i++ {
		os.WriteFile(filepath.Join(dir, fmtName(i)), nil, 0600)
	}
	root, err := os.OpenRoot(dir)
	if err != nil {
		b.Fatal(err)
	}
	defer root.Close()
	p, _ := policy.Parse(strings.NewReader("*.tmp\n!keep.tmp\n"), policy.Source{})
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := Compare(context.Background(), root, p, p, Defaults()); err != nil {
			b.Fatal(err)
		}
	}
}
func fmtName(i int) string {
	const chars = "0123456789"
	return "file" + string(chars[(i/100)%10]) + string(chars[(i/10)%10]) + string(chars[i%10]) + ".tmp"
}
