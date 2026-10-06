# Security

IgnoreImpact is a local metadata inspection tool, not a secret or vulnerability
scanner. Never treat passing a CI gate as proof that a context is safe to publish.

The scanner does not read regular-file bodies or follow symlinks. It does read
selected ignore files and directory metadata. Reports can reveal filenames and
policy contents; review where you upload or store them. Use a stable filesystem
while scanning; concurrent hostile mutation is not supported.

If you find a vulnerability, use GitHub's private vulnerability reporting feature
if it is enabled. Otherwise open an issue containing only a request for a private
reporting channel; do not publish sensitive details or real credentials.
