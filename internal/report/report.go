// Package report renders the versioned machine format and terminal-safe text.
package report

import (
	"encoding/json"
	"fmt"
	"io"
	"strconv"

	"github.com/agent-axiom/ignoreimpact/internal/policy"
	"github.com/agent-axiom/ignoreimpact/internal/scan"
)

func JSON(w io.Writer, v any) error {
	e := json.NewEncoder(w)
	e.SetIndent("", "  ")
	return e.Encode(v)
}

func Reason(d policy.Decision) string {
	if d.Rule == nil {
		return "included by default"
	}
	return fmt.Sprintf("%s by line %d %s", d.Rule.Action, d.Rule.Line, strconv.QuoteToASCII(d.Rule.Pattern))
}

func Human(w io.Writer, r *scan.Report, limit int) error {
	// Propagate output errors so callers never return a successful exit code.
	_, err := fmt.Fprintf(w, "IgnoreImpact | same tree, two policies\nBefore: %s\nAfter:  %s\n\nIncluded: %d -> %d entries | %d -> %d B (%+d B)\nAdded:    %d entries | %d B\nRemoved:  %d entries | %d B\n\n", source(r.BeforePolicy), source(r.AfterPolicy), r.Before.Entries, r.After.Entries, r.Before.Bytes, r.After.Bytes, r.DeltaBytes, r.Added.Entries, r.Added.Bytes, r.Removed.Entries, r.Removed.Bytes)
	if err != nil {
		return err
	}
	n := len(r.Changes)
	if limit >= 0 && n > limit {
		n = limit
	}
	for _, c := range r.Changes[:n] {
		sign := "-"
		if c.Change == "added" {
			sign = "+"
		}
		if _, err = fmt.Fprintf(w, "%s %s (%s, %d B)\n    before: %s\n    after:  %s\n", sign, strconv.QuoteToASCII(c.Path), c.Kind, c.Bytes, Reason(c.Before), Reason(c.After)); err != nil {
			return err
		}
	}
	if len(r.Changes) == 0 {
		_, err = fmt.Fprintln(w, "No files or symlinks changed inclusion.")
	} else if n < len(r.Changes) {
		_, err = fmt.Fprintf(w, "\nShowing %d of %d changes; use --limit=-1 or --json for all.\n", n, len(r.Changes))
	}
	if err != nil {
		return err
	}
	_, err = fmt.Fprintln(w, "\nBytes are logical regular-file sizes, not image or transfer size. Symlinks count as entries with 0 B.")
	return err
}
func source(s policy.Source) string {
	if s.Path == "" {
		return s.Kind
	}
	return fmt.Sprintf("%s (%s)", strconv.QuoteToASCII(s.Path), s.Kind)
}
