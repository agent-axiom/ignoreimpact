package policy

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/moby/patternmatcher"
	"github.com/moby/patternmatcher/ignorefile"
)

func TestDockerRules(t *testing.T) {
	cases := []struct {
		name, policy, path string
		included           bool
		line               int
	}{
		{"empty", "", ".hidden", true, 0},
		{"root glob", "*.md\n", "sub/readme.md", true, 0},
		{"recursive glob", "**/*.md\n", "sub/readme.md", false, 1},
		{"zero directory glob", "**/*.md\n", "readme.md", false, 1},
		{"parent", "vendor\n", "vendor/deep/lib.go", false, 1},
		{"reinclude child", "vendor\n!vendor/keep.go\n", "vendor/keep.go", true, 2},
		{"reinclude parent", "vendor\n!vendor/keep\n", "vendor/keep/deep.go", true, 2},
		{"last wins", "*.md\n!README*.md\nREADME-secret.md\n", "README-secret.md", false, 3},
		{"last redundant rule", "*.md\nREADME.md\n", "README.md", false, 2},
		{"slashes", " /foo/bar/ \n", "foo/bar/baz", false, 1},
		{"dot ignored", ".\n", "sub/a", true, 0},
		{"BOM comment", "\ufeff# comment\r\n\r\nfoo\r\n", "foo", false, 3},
		{"spaces before comment", " #literal\n", "#literal", false, 1},
		{"negation whitespace", "*\n!   keep\n", "keep", true, 2},
		{"literal bang negation", "*\n!!keep\n", "!keep", true, 2},
		{"lone negation explanation", "!foo\n", "foo", true, 1},
		{"later BOM not stripped", "# first\n\ufefffoo\n", "foo", true, 0},
		{"character class", "file[0-9].txt\n", "file7.txt", false, 1},
	}
	if runtime.GOOS != "windows" {
		cases = append(cases, struct {
			name, policy, path string
			included           bool
			line               int
		}{"escaped bang", "\\!literal\n", "!literal", false, 1})
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			p, err := Parse(strings.NewReader(tc.policy), Source{})
			if err != nil {
				t.Fatal(err)
			}
			d, err := p.Explain(tc.path)
			if err != nil {
				t.Fatal(err)
			}
			line := 0
			if d.Rule != nil {
				line = d.Rule.Line
			}
			if d.Included != tc.included || line != tc.line {
				t.Fatalf("got included=%v line=%d; want %v/%d", d.Included, line, tc.included, tc.line)
			}
		})
	}
}
func TestRejectInvalid(t *testing.T) {
	for _, text := range []string{"!\n", "[abc\n", "bad\x00\n", string([]byte{255}), strings.Repeat("a", MaxBytes+1), strings.Repeat("x\n", MaxRules+1), strings.Repeat("a", 70000)} {
		if _, err := Parse(strings.NewReader(text), Source{}); err == nil {
			t.Errorf("accepted invalid policy length %d", len(text))
		}
	}
}
func TestResolution(t *testing.T) {
	dir := t.TempDir()
	os.Mkdir(filepath.Join(dir, "docker"), 0700)
	write := func(path, text string) {
		t.Helper()
		if err := os.WriteFile(filepath.Join(dir, path), []byte(text), 0600); err != nil {
			t.Fatal(err)
		}
	}
	write(".dockerignore", "root-only\n")
	write("docker/build.Dockerfile.dockerignore", "specific-only\n")
	root, err := os.OpenRoot(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer root.Close()
	p, err := Resolve(root, "docker/build.Dockerfile")
	if err != nil {
		t.Fatal(err)
	}
	if p.Source.Kind != "dockerfile-specific" {
		t.Fatal(p.Source)
	}
	if ok, _ := p.Included("root-only"); !ok {
		t.Fatal("policies were merged")
	}
	if ok, _ := p.Included("specific-only"); ok {
		t.Fatal("specific policy not applied")
	}
	p, err = Resolve(root, "Dockerfile")
	if err != nil || p.Source.Kind != "context-default" {
		t.Fatalf("%+v %v", p, err)
	}
	if _, err = Resolve(root, "../Dockerfile"); err == nil {
		t.Fatal("accepted traversal")
	}
	os.Remove(filepath.Join(dir, ".dockerignore"))
	p, err = Resolve(root, "Dockerfile")
	if err != nil || p.Source.Kind != "empty" {
		t.Fatalf("%+v %v", p, err)
	}
	write("Dockerfile.dockerignore", "")
	p, err = Resolve(root, "Dockerfile")
	if err != nil || p.Source.Kind != "dockerfile-specific" {
		t.Fatal("empty specific policy must take precedence")
	}
}
func TestDiscoveredPolicyCannotEscape(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("symlink permission varies")
	}
	dir := t.TempDir()
	outside := filepath.Join(t.TempDir(), "secret")
	os.WriteFile(outside, []byte("anything"), 0600)
	if err := os.Symlink(outside, filepath.Join(dir, ".dockerignore")); err != nil {
		t.Fatal(err)
	}
	root, err := os.OpenRoot(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer root.Close()
	if _, err := Resolve(root, "Dockerfile"); err == nil {
		t.Fatal("followed escaping policy symlink")
	}
}

// Fuzz the complete upstream parser/matcher contract, not a home-grown glob.
func FuzzMatchesOfficial(f *testing.F) {
	for _, v := range [][2]string{{"**\n!src/**\nsrc/private\n", "src/public/a.go"}, {"\ufeff# c\n*.md\n!README.md", "README.md"}, {"foo\n!foo/bar\n", "foo/bar/x"}} {
		f.Add(v[0], v[1])
	}
	f.Fuzz(func(t *testing.T, text, path string) {
		if len(text) > 50000 || len(path) > 1000 || path == "." || path == "" {
			return
		}
		p, err := Parse(strings.NewReader(text), Source{})
		if err != nil {
			return
		}
		patterns, err := ignorefile.ReadAll(strings.NewReader(text))
		if err != nil {
			t.Fatal(err)
		}
		official, err := patternmatcher.New(patterns)
		if err != nil {
			t.Fatal(err)
		}
		want, err := official.MatchesOrParentMatches(path)
		if err != nil {
			return
		}
		got, err := p.Explain(path)
		if err != nil {
			t.Fatal(err)
		}
		if got.Included == want {
			t.Fatalf("mismatch for %q in %q", path, text)
		}
		if got.Rule != nil && got.Included != (got.Rule.Action == "include") {
			t.Fatalf("explanation contradicts decision: %s", fmt.Sprint(got))
		}
	})
}
