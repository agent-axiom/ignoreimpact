package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/agent-axiom/ignoreimpact/internal/scan"
)

func run(args ...string) (int, string, string) {
	var out, err bytes.Buffer
	code := Run(context.Background(), args, &out, &err)
	return code, out.String(), err.String()
}
func fixture(t *testing.T) (string, string) {
	t.Helper()
	root := t.TempDir()
	os.WriteFile(filepath.Join(root, "a.txt"), []byte("abc"), 0600)
	p := filepath.Join(t.TempDir(), "ignore")
	os.WriteFile(p, []byte("**\n"), 0600)
	return root, p
}
func TestExitCodes(t *testing.T) {
	root, p := fixture(t)
	base := []string{"compare", "--context", root, "--before", p, "--after-empty"}
	for _, tc := range []struct {
		args []string
		code int
	}{{nil, 0}, {[]string{"--fail-on", "change"}, 1}, {[]string{"--fail-on", "added"}, 1}, {[]string{"--fail-on", "growth"}, 1}, {[]string{"--max-added-bytes", "3"}, 0}, {[]string{"--max-added-bytes", "2"}, 1}, {[]string{"--fail-on", "nonsense"}, 2}, {[]string{"--max-entries", "0"}, 2}, {[]string{"--after", p}, 2}} {
		args := append(append([]string{}, base...), tc.args...)
		code, out, err := run(args...)
		if code != tc.code {
			t.Fatalf("%v: %d: %s %s", tc.args, code, out, err)
		}
		if code == 2 && out != "" {
			t.Fatal("partial report on error")
		}
	}
}
func TestJSONAndExplain(t *testing.T) {
	root, p := fixture(t)
	code, out, err := run("compare", "--context", root, "--before", p, "--after-empty", "--json", "--fail-on", "added")
	if code != 1 || err != "" {
		t.Fatalf("%d %s", code, err)
	}
	var r scan.Report
	if e := json.Unmarshal([]byte(out), &r); e != nil {
		t.Fatal(e)
	}
	if r.SchemaVersion != 1 || len(r.Changes) != 1 || r.Added.Bytes != 3 {
		t.Fatal(r)
	}
	code, out, err = run("explain", "--context", root, "--policy", p, "--json", "a.txt", "missing.txt")
	if code != 0 || !json.Valid([]byte(out)) || !strings.Contains(out, "missing.txt") {
		t.Fatalf("%d %s %s", code, out, err)
	}
	code, out, _ = run("explain", "--context", root, "../escape")
	if code != 2 || out != "" {
		t.Fatal("accepted escape path")
	}
}
func TestTerminalSafeOutput(t *testing.T) {
	if os.PathSeparator == '\\' {
		t.Skip("Windows disallows control filenames")
	}
	root := t.TempDir()
	os.WriteFile(filepath.Join(root, "evil\n\x1b[31m.txt"), nil, 0600)
	p := filepath.Join(t.TempDir(), "ignore")
	os.WriteFile(p, []byte("**"), 0600)
	code, out, err := run("compare", "--context", root, "--before", p, "--after-empty")
	if code != 0 {
		t.Fatal(err)
	}
	if strings.ContainsRune(out, '\x1b') || !strings.Contains(out, `evil\n\x1b[31m.txt`) {
		t.Fatalf("unsafe output: %q", out)
	}
}
func TestHelpAndUsage(t *testing.T) {
	for _, tc := range []struct {
		args []string
		code int
	}{{nil, 0}, {[]string{"--help"}, 0}, {[]string{"version"}, 0}, {[]string{"compare", "-h"}, 0}, {[]string{"what"}, 2}, {[]string{"compare"}, 2}, {[]string{"explain"}, 2}, {[]string{"version", "extra"}, 2}} {
		code, _, _ := run(tc.args...)
		if code != tc.code {
			t.Fatal(tc.args, code)
		}
	}
}

type brokenWriter struct{}

func (brokenWriter) Write([]byte) (int, error) { return 0, errors.New("broken pipe") }
func TestOutputErrorIsNotSuccess(t *testing.T) {
	root, p := fixture(t)
	for _, format := range []string{"--json", "--limit=0"} {
		code := Run(context.Background(), []string{"compare", "--context", root, "--before", p, "--after-empty", format}, brokenWriter{}, &bytes.Buffer{})
		if code != 2 {
			t.Fatal(code)
		}
	}
}
func TestTruncationDisclosed(t *testing.T) {
	root, p := fixture(t)
	code, out, _ := run("compare", "--context", root, "--before", p, "--after-empty", "--limit=0")
	if code != 0 || !strings.Contains(out, "Showing 0 of 1") {
		t.Fatal(out)
	}
}
