# IgnoreImpact 0.1.0-rc.1

First binary release candidate for reviewing Docker ignore-policy changes.

- Compare two policies against the same local tree
- See newly included/excluded paths, logical bytes, and matching rules
- Use deterministic JSON, a versioned schema, and CI exit-code gates
- Select Dockerfile-specific ignore policies with Moby matching semantics

Archives target Linux, macOS, and Windows on x86-64 and ARM64. Each includes a
standalone binary, licenses, build metadata, and a small runnable example. No Go
installation or Docker daemon is needed to run the binary.

Download the matching archive and verify its hash using the accompanying
SHA256SUMS. Check release-manifest.json for the exact source commit and
VERIFICATION.json for native installation results. The bundled INSTALL.txt
contains a 20-second demo.

This is a prerelease. Binaries are not publisher-signed or notarized; provenance
metadata is unsigned. Do not automatically bypass OS security warnings. Logical
file sizes are not image sizes or actual BuildKit transfer sizes. The tool is not
a secret scanner, and scans require a stable filesystem.

Maintainer: fill in the reviewed commit, verified workflow link, and asset
checksums before publishing. Do not publish these notes with this reminder intact.
