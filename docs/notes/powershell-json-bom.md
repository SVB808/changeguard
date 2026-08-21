# PowerShell JSON BOM compatibility

During local Windows validation of the V5.0 synthesis workflow, a manifest produced with:

```powershell
changeguard pr --repo SVB808/changeguard --pr 16 --verification-plan --json |
  Out-File -Encoding utf8 manifest.json
```

contained a leading UTF-8 byte-order mark (BOM). Pydantic's JSON parser rejected the decoded string because the first character was `\ufeff` rather than `{`.

ChangeGuard synthesis inputs are now read using Python's `utf-8-sig` codec. This accepts ordinary UTF-8 and strips a leading BOM when one is present. The same behavior applies to both `--manifest` and `--verification-result` files.

A CLI regression test writes an actual BOM-prefixed manifest and verifies that synthesis succeeds.
