// Package scan inventories one filesystem tree under two ignore policies.
package scan

import (
	"context"
	"fmt"
	"io/fs"
	"math"
	"os"
	"sort"
	"strings"
	"unicode/utf8"

	"github.com/agent-axiom/ignoreimpact/internal/policy"
)

const SchemaVersion = 1

type Totals struct {
	Entries  int64 `json:"entries"`
	Files    int64 `json:"regular_files"`
	Symlinks int64 `json:"symlinks"`
	Bytes    int64 `json:"bytes"`
}
type Change struct {
	Path   string          `json:"path"`
	Kind   string          `json:"kind"`
	Bytes  int64           `json:"bytes"`
	Change string          `json:"change"`
	Before policy.Decision `json:"before"`
	After  policy.Decision `json:"after"`
}
type Report struct {
	SchemaVersion  int           `json:"schema_version"`
	BeforePolicy   policy.Source `json:"before_policy"`
	AfterPolicy    policy.Source `json:"after_policy"`
	ScannedEntries int64         `json:"scanned_entries"`
	Before         Totals        `json:"before"`
	After          Totals        `json:"after"`
	Added          Totals        `json:"added"`
	Removed        Totals        `json:"removed"`
	DeltaBytes     int64         `json:"delta_bytes"`
	Changes        []Change      `json:"changes"`
}
type Options struct {
	MaxEntries int64
	MaxChanges int
	MaxDepth   int
}

func Defaults() Options { return Options{MaxEntries: 1000000, MaxChanges: 100000, MaxDepth: 256} }

// Compare does not read file bodies, follow symlinks, hash, invoke Docker, or
// contact a network service. It deliberately traverses excluded directories so
// later negations can re-include descendants. The caller owns root's lifetime.
func Compare(ctx context.Context, root *os.Root, before, after *policy.Policy, opts Options) (*Report, error) {
	if opts.MaxEntries <= 0 || opts.MaxChanges <= 0 || opts.MaxDepth <= 0 {
		return nil, fmt.Errorf("scan limits must be positive")
	}
	r := &Report{SchemaVersion: SchemaVersion, BeforePolicy: before.Source, AfterPolicy: after.Source, Changes: []Change{}}
	err := fs.WalkDir(root.FS(), ".", func(path string, d fs.DirEntry, walkErr error) error {
		if err := ctx.Err(); err != nil {
			return err
		}
		if walkErr != nil {
			return walkErr
		}
		if path == "." {
			return nil
		}
		if !utf8.ValidString(path) {
			return fmt.Errorf("path is not valid UTF-8: %q", path)
		}
		r.ScannedEntries++
		if r.ScannedEntries > opts.MaxEntries {
			return fmt.Errorf("scan exceeds --max-entries=%d", opts.MaxEntries)
		}
		if strings.Count(path, "/")+1 > opts.MaxDepth {
			return fmt.Errorf("path exceeds maximum depth %d: %q", opts.MaxDepth, path)
		}
		if d.IsDir() {
			return nil
		}
		was, err := before.Included(path)
		if err != nil {
			return fmt.Errorf("before policy for %q: %w", path, err)
		}
		now, err := after.Included(path)
		if err != nil {
			return fmt.Errorf("after policy for %q: %w", path, err)
		}
		if !was && !now {
			return nil
		}
		info, err := d.Info() // lstat semantics: never reads a symlink's target
		if err != nil {
			return err
		}
		kind := "file"
		size := info.Size()
		if info.Mode()&os.ModeSymlink != 0 {
			kind = "symlink"
			size = 0
		} else if !info.Mode().IsRegular() {
			return fmt.Errorf("unsupported included file type at %q (%s)", path, info.Mode().Type())
		}
		if size < 0 {
			return fmt.Errorf("negative file size for %q", path)
		}
		if was {
			if err := add(&r.Before, kind, size); err != nil {
				return err
			}
		}
		if now {
			if err := add(&r.After, kind, size); err != nil {
				return err
			}
		}
		if was == now {
			return nil
		}
		if len(r.Changes) >= opts.MaxChanges {
			return fmt.Errorf("comparison exceeds --max-changes=%d", opts.MaxChanges)
		}
		change := "removed"
		if now {
			change = "added"
			err = add(&r.Added, kind, size)
		} else {
			err = add(&r.Removed, kind, size)
		}
		if err != nil {
			return err
		}
		bd, err := before.Explain(path)
		if err != nil {
			return err
		}
		ad, err := after.Explain(path)
		if err != nil {
			return err
		}
		r.Changes = append(r.Changes, Change{Path: path, Kind: kind, Bytes: size, Change: change, Before: bd, After: ad})
		return nil
	})
	if err != nil {
		return nil, err
	} // Never report a partial inventory as success.
	sort.Slice(r.Changes, func(i, j int) bool { return r.Changes[i].Path < r.Changes[j].Path })
	r.DeltaBytes = r.After.Bytes - r.Before.Bytes
	return r, nil
}
func add(t *Totals, kind string, size int64) error {
	if size > math.MaxInt64-t.Bytes {
		return fmt.Errorf("total bytes exceed int64")
	}
	t.Entries++
	if kind == "file" {
		t.Files++
	} else {
		t.Symlinks++
	}
	t.Bytes += size
	return nil
}
