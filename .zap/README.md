# ZAP DAST rule overrides

`rules.tsv` is consumed by `.github/workflows/ci.yml` → `zaproxy/action-full-scan`
(`rules_file_name: .zap/rules.tsv`).

Format (tab-separated):

```text
<pluginId>	<WARN|FAIL|IGNORE>	(optional comment)
```

## Why 90005 is IGNORE

ZAP alert **90005** (*Fetch Metadata Request Headers*) flags missing
`Sec-Fetch-Site` / `Sec-Fetch-Mode` / `Sec-Fetch-Dest` / `Sec-Fetch-User` on the
**HTTP request**. Modern browsers send these; ZAP’s spider/clients often do not.

They are **not** server response headers. Ignoring 90005 avoids opening
informational GitHub issues (e.g. #787) that cannot be “fixed” by middleware.

Do **not** IGNORE real response-header / XSS / injection alerts without a
written risk acceptance.
