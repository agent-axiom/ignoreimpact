package report

import (
	"bytes"
	"errors"
	"strings"
	"testing"

	"github.com/agent-axiom/ignoreimpact/internal/scan"
)

type fails struct{}

func (fails) Write([]byte) (int, error) { return 0, errors.New("write failed") }
func TestRenderErrors(t *testing.T) {
	if err := JSON(fails{}, map[string]int{"x": 1}); err == nil {
		t.Fatal("ignored JSON write error")
	}
	if err := Human(fails{}, &scan.Report{}, 100); err == nil {
		t.Fatal("ignored text write error")
	}
}
func TestEmptyReport(t *testing.T) {
	var buf bytes.Buffer
	if err := Human(&buf, &scan.Report{}, 100); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(buf.String(), "No files or symlinks changed inclusion.") {
		t.Fatal(buf.String())
	}
}
