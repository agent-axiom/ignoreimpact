// Package policy delegates Docker ignore syntax and matching to Moby.
package policy

import (
	"bufio"
	"bytes"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"unicode/utf8"

	"github.com/moby/patternmatcher"
	"github.com/moby/patternmatcher/ignorefile"
)

const MaxBytes = 1 << 20
const MaxRules = 10000

type Source struct {
	Kind string `json:"kind"`
	Path string `json:"path,omitempty"`
}
type Rule struct {
	Line    int    `json:"line"`
	Text    string `json:"text"`
	Pattern string `json:"pattern"`
	Action  string `json:"action"`
	matcher *patternmatcher.PatternMatcher
}
type Decision struct {
	Included bool  `json:"included"`
	Rule     *Rule `json:"rule"` // null means included by default
}
type Policy struct {
	Source  Source
	rules   []Rule
	matcher *patternmatcher.PatternMatcher
}

// Parse preserves source line numbers while letting the upstream reader perform
// all normalization. Policy instances are not safe for concurrent evaluation.
func Parse(r io.Reader, source Source) (*Policy, error) {
	data, err := io.ReadAll(io.LimitReader(r, MaxBytes+1))
	if err != nil {
		return nil, fmt.Errorf("read policy: %w", err)
	}
	if len(data) > MaxBytes {
		return nil, fmt.Errorf("policy exceeds %d bytes", MaxBytes)
	}
	if !utf8.Valid(data) {
		return nil, errors.New("policy is not valid UTF-8")
	}
	if bytes.IndexByte(data, 0) >= 0 {
		return nil, errors.New("policy contains NUL")
	}
	patterns, err := ignorefile.ReadAll(bytes.NewReader(data))
	if err != nil {
		return nil, fmt.Errorf("parse policy: %w", err)
	}
	if len(patterns) > MaxRules {
		return nil, fmt.Errorf("policy exceeds %d rules", MaxRules)
	}
	matcher, err := patternmatcher.New(patterns)
	if err != nil {
		return nil, fmt.Errorf("invalid policy: %w", err)
	}
	p := &Policy{Source: source, matcher: matcher}
	scanner := bufio.NewScanner(bytes.NewReader(data))
	line := 0
	for scanner.Scan() {
		line++
		raw := scanner.Text()
		input := raw
		// A BOM is meaningful only on the first physical line.
		if line > 1 {
			input = "\n" + input
		}
		parsed, err := ignorefile.ReadAll(strings.NewReader(input))
		if err != nil {
			return nil, err
		}
		if len(parsed) == 0 {
			continue
		}
		pat := parsed[0]
		action := "exclude"
		one := []string{pat}
		if strings.HasPrefix(pat, "!") {
			action = "include"
			one = []string{"**", pat}
		}
		m, err := patternmatcher.New(one)
		if err != nil {
			return nil, fmt.Errorf("line %d: %w", line, err)
		}
		// Compile eagerly, including expressions lazily validated by Moby.
		if _, err = m.MatchesOrParentMatches("__ignoreimpact_validate__"); err != nil {
			return nil, fmt.Errorf("line %d: %w", line, err)
		}
		p.rules = append(p.rules, Rule{Line: line, Text: raw, Pattern: pat, Action: action, matcher: m})
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	return p, nil
}

func Empty() *Policy {
	p, _ := Parse(strings.NewReader(""), Source{Kind: "empty"})
	return p
}

func (p *Policy) Included(path string) (bool, error) {
	excluded, err := p.matcher.MatchesOrParentMatches(path)
	return !excluded, err
}

// Explain names the last matching rule, including matches inherited from an
// ancestor directory. Matching is still performed by Moby, not a second globber.
func (p *Policy) Explain(path string) (Decision, error) {
	included, err := p.Included(path)
	if err != nil {
		return Decision{}, err
	}
	d := Decision{Included: included}
	for i := len(p.rules) - 1; i >= 0; i-- {
		rule := &p.rules[i]
		hit, err := rule.matcher.MatchesOrParentMatches(path)
		if err != nil {
			return Decision{}, err
		}
		if rule.Action == "include" {
			hit = !hit
		}
		if hit {
			d.Rule = rule
			break
		}
	}
	return d, nil
}

// LoadExplicit accepts an intentionally selected policy outside the context.
// Policies must be regular files; directories, devices and FIFOs are rejected.
func LoadExplicit(path string) (*Policy, error) {
	info, err := os.Stat(path)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, errors.New("policy must be a regular file")
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return readFile(f, Source{Kind: "explicit", Path: filepath.ToSlash(path)})
}

func readFile(f *os.File, source Source) (*Policy, error) {
	info, err := f.Stat()
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, errors.New("policy must be a regular file")
	}
	if info.Size() > MaxBytes {
		return nil, fmt.Errorf("policy exceeds %d bytes", MaxBytes)
	}
	return Parse(f, source)
}

// Resolve chooses <Dockerfile>.dockerignore before the context .dockerignore.
// os.Root prevents discovered ignore files from escaping through symlinks.
func Resolve(root *os.Root, dockerfile string) (*Policy, error) {
	if !filepath.IsLocal(dockerfile) {
		return nil, errors.New("Dockerfile must be a relative path inside the context")
	}
	choices := []Source{{Kind: "dockerfile-specific", Path: filepath.ToSlash(dockerfile) + ".dockerignore"}, {Kind: "context-default", Path: ".dockerignore"}}
	for _, source := range choices {
		info, err := root.Stat(filepath.FromSlash(source.Path))
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			return nil, fmt.Errorf("%s: %w", source.Path, err)
		}
		if !info.Mode().IsRegular() {
			return nil, fmt.Errorf("%s: policy must be a regular file", source.Path)
		}
		f, err := root.Open(filepath.FromSlash(source.Path))
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			return nil, fmt.Errorf("%s: %w", source.Path, err)
		}
		p, err := readFile(f, source)
		f.Close()
		if err != nil {
			return nil, fmt.Errorf("%s: %w", source.Path, err)
		}
		return p, nil
	}
	return Empty(), nil
}
