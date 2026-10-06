// Package cli keeps command-line behavior testable without subprocesses.
package cli

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/agent-axiom/ignoreimpact/internal/policy"
	"github.com/agent-axiom/ignoreimpact/internal/report"
	"github.com/agent-axiom/ignoreimpact/internal/scan"
)

// Version and SourceCommit are injected by the release build.
var Version = "dev"
var SourceCommit = ""

const help = `IgnoreImpact: see what a Docker ignore-policy change includes or excludes.

Usage:
  ignoreimpact compare --before OLD [--after NEW] [options]
  ignoreimpact compare --before-empty [--after-dockerfile Dockerfile] [options]
  ignoreimpact explain [--policy FILE | --dockerfile FILE] [options] PATH...
  ignoreimpact version

Compare options:
  --context DIR              Local context directory (default .)
  --before FILE              Explicit baseline ignore file (relative to cwd)
  --before-dockerfile FILE   Resolve baseline Dockerfile-specific/root ignore file
  --before-empty             Baseline has no exclusions
  --after FILE               Explicit candidate ignore file (relative to cwd)
  --after-dockerfile FILE    Resolve candidate Dockerfile-specific/root ignore file
  --after-empty              Candidate has no exclusions
  --json                     Versioned JSON; no human text on stdout
  --fail-on MODE             none (default), change, added, or growth
  --max-added-bytes N        Fail if added regular-file bytes exceed N
  --limit N                  Human output limit (default 100, -1 for all)
  --max-entries N             Abort incomplete scans (default 1000000)
  --max-changes N             Bound retained changes (default 100000)

With no candidate selector, uses Dockerfile.dockerignore, then .dockerignore,
then an empty policy. Dockerfile selectors are relative to the context.
Exit codes: 0 success, 1 requested CI gate failed, 2 usage or operational error.
`

type selector struct {
	file, dockerfile string
	empty            bool
}

func (s selector) count() int {
	n := 0
	if s.file != "" {
		n++
	}
	if s.dockerfile != "" {
		n++
	}
	if s.empty {
		n++
	}
	return n
}
func (s selector) load(root *os.Root) (*policy.Policy, error) {
	if s.count() > 1 {
		return nil, errors.New("choose only one policy selector per side")
	}
	if s.empty {
		return policy.Empty(), nil
	}
	if s.file != "" {
		return policy.LoadExplicit(s.file)
	}
	d := s.dockerfile
	if d == "" {
		d = "Dockerfile"
	}
	return policy.Resolve(root, d)
}

func Run(ctx context.Context, args []string, out, errout io.Writer) int {
	if len(args) == 0 || args[0] == "help" || args[0] == "--help" || args[0] == "-h" {
		if _, err := io.WriteString(out, help); err != nil {
			return 2
		}
		return 0
	}
	if args[0] == "version" || args[0] == "--version" {
		if len(args) != 1 {
			return fail(errout, errors.New("version takes no arguments"))
		}
		if _, err := fmt.Fprintln(out, versionString()); err != nil {
			return 2
		}
		return 0
	}
	switch args[0] {
	case "compare":
		return compare(ctx, args[1:], out, errout)
	case "explain":
		return explain(args[1:], out, errout)
	default:
		return fail(errout, fmt.Errorf("unknown command %q; use --help", args[0]))
	}
}
func flags(name string) *flag.FlagSet {
	f := flag.NewFlagSet(name, flag.ContinueOnError)
	f.SetOutput(io.Discard)
	return f
}
func parse(f *flag.FlagSet, args []string, out, errout io.Writer) (bool, int) {
	if err := f.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			_, e := io.WriteString(out, help)
			if e != nil {
				return false, 2
			}
			return false, 0
		}
		return false, fail(errout, err)
	}
	return true, 0
}
func fail(w io.Writer, err error) int {
	fmt.Fprintf(w, "ignoreimpact: %s\n", strconv.QuoteToASCII(err.Error()))
	return 2
}

func compare(ctx context.Context, args []string, out, errout io.Writer) int {
	f := flags("compare")
	var before, after selector
	contextPath := f.String("context", ".", "")
	f.StringVar(&before.file, "before", "", "")
	f.StringVar(&before.dockerfile, "before-dockerfile", "", "")
	f.BoolVar(&before.empty, "before-empty", false, "")
	f.StringVar(&after.file, "after", "", "")
	f.StringVar(&after.dockerfile, "after-dockerfile", "", "")
	f.BoolVar(&after.empty, "after-empty", false, "")
	jsonOutput := f.Bool("json", false, "")
	failOn := f.String("fail-on", "none", "")
	maxAdded := f.Int64("max-added-bytes", -1, "")
	limit := f.Int("limit", 100, "")
	opts := scan.Defaults()
	f.Int64Var(&opts.MaxEntries, "max-entries", opts.MaxEntries, "")
	f.IntVar(&opts.MaxChanges, "max-changes", opts.MaxChanges, "")
	if ok, code := parse(f, args, out, errout); !ok {
		return code
	}
	if f.NArg() != 0 {
		return fail(errout, errors.New("unexpected positional arguments; flags must precede arguments"))
	}
	if before.count() != 1 {
		return fail(errout, errors.New("choose exactly one of --before, --before-dockerfile, or --before-empty"))
	}
	if after.count() > 1 {
		return fail(errout, errors.New("choose only one candidate selector"))
	}
	if *limit < -1 || *maxAdded < -1 || opts.MaxEntries <= 0 || opts.MaxChanges <= 0 {
		return fail(errout, errors.New("invalid numeric limit"))
	}
	switch *failOn {
	case "none", "change", "added", "growth":
	default:
		return fail(errout, errors.New("--fail-on must be none, change, added, or growth"))
	}
	root, err := os.OpenRoot(*contextPath)
	if err != nil {
		return fail(errout, err)
	}
	defer root.Close()
	bp, err := before.load(root)
	if err != nil {
		return fail(errout, fmt.Errorf("before: %w", err))
	}
	ap, err := after.load(root)
	if err != nil {
		return fail(errout, fmt.Errorf("after: %w", err))
	}
	r, err := scan.Compare(ctx, root, bp, ap, opts)
	if err != nil {
		return fail(errout, err)
	}
	if *jsonOutput {
		err = report.JSON(out, r)
	} else {
		err = report.Human(out, r, *limit)
	}
	if err != nil {
		return fail(errout, err)
	}
	gated := (*failOn == "change" && len(r.Changes) > 0) || (*failOn == "added" && r.Added.Entries > 0) || (*failOn == "growth" && r.DeltaBytes > 0) || (*maxAdded >= 0 && r.Added.Bytes > *maxAdded)
	if gated {
		return 1
	}
	return 0
}

func explain(args []string, out, errout io.Writer) int {
	f := flags("explain")
	contextPath := f.String("context", ".", "")
	s := selector{}
	f.StringVar(&s.file, "policy", "", "")
	f.StringVar(&s.dockerfile, "dockerfile", "", "")
	jsonOutput := f.Bool("json", false, "")
	if ok, code := parse(f, args, out, errout); !ok {
		return code
	}
	if s.count() > 1 {
		return fail(errout, errors.New("choose --policy or --dockerfile"))
	}
	if f.NArg() == 0 {
		return fail(errout, errors.New("explain requires at least one context-relative path"))
	}
	root, err := os.OpenRoot(*contextPath)
	if err != nil {
		return fail(errout, err)
	}
	defer root.Close()
	p, err := s.load(root)
	if err != nil {
		return fail(errout, err)
	}
	type item struct {
		Path string `json:"path"`
		policy.Decision
	}
	result := struct {
		SchemaVersion int           `json:"schema_version"`
		Policy        policy.Source `json:"policy"`
		Paths         []item        `json:"paths"`
	}{SchemaVersion: scan.SchemaVersion, Policy: p.Source, Paths: []item{}}
	for _, arg := range f.Args() {
		if !filepath.IsLocal(arg) || filepath.Clean(arg) == "." {
			return fail(errout, fmt.Errorf("path must be relative and inside context: %q", arg))
		}
		path := filepath.ToSlash(filepath.Clean(arg))
		d, err := p.Explain(path)
		if err != nil {
			return fail(errout, err)
		}
		result.Paths = append(result.Paths, item{path, d})
	}
	if *jsonOutput {
		err = report.JSON(out, result)
	} else {
		var b strings.Builder
		for _, item := range result.Paths {
			state := "excluded"
			if item.Included {
				state = "included"
			}
			fmt.Fprintf(&b, "%s: %s (%s)\n", strconv.QuoteToASCII(item.Path), state, report.Reason(item.Decision))
		}
		_, err = io.WriteString(out, b.String())
	}
	if err != nil {
		return fail(errout, err)
	}
	return 0
}

func versionString() string {
	text := "ignoreimpact " + Version
	if SourceCommit != "" {
		text += " (" + SourceCommit + ")"
	}
	return text
}
