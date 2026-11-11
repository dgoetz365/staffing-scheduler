# Verification record

Verified on November 11, 2026 with Python **3.12.14** and Node **22.23.3** on Windows.

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests -v` | 23 tests passed |
| `node --check static/app.js` | Passed |
| Fresh CLI seed and serve | Passed through subprocess test and real loopback HTTP request |
| Existing database protection | Repeated seed refused; database bytes unchanged |
| Concurrent writers | Exactly one accepted mutation and one stale-version rejection |
| Published schedules | Prior payload preserved after draft edits and name changes; SQL update/delete triggers reject modification |
| Approval-time conflict | Rejected approval leaves assignments, request status, version and events unchanged |
| HTTP boundary | Route allowlist, Host/Origin, duplicate headers/JSON keys, body size, malformed UTF-8, surrogate Unicode and field checks passed |

The tests use fresh temporary SQLite files, the actual application functions, and a real local HTTP server. They do not require external services. The CLI test starts the application as a separate process, requests the served page, then terminates only that process.

The Impeccable source detector ran once over the finished HTML, CSS and JavaScript. It reported one rounded-tab/accent-border warning. The tab radius was removed, preserving a square-corner selected underline. The detector was not rerun.

Browser use was explicitly excluded from this build. No browser, screenshot or rendered visual check was performed. Responsive rules, labels, keyboard tab behavior, focus styles and text-only DOM updates were inspected in source; visual appearance and interactive browser behavior remain unverified. The tests do not substitute for that manual review.
