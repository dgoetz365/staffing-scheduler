# Engineering decisions

## Draft and publication have different jobs

Assignments are current working state. A publication stores a complete JSON copy of the shifts, volunteers and assignments, alongside its source workspace version and publication time. The UI reads that copy, including historical names, instead of joining it to mutable tables. SQLite triggers disallow updates and deletion of published rows through ordinary SQL.

The publication captures the workspace version immediately before its own mutation. Publishing, like any accepted action, then increments the workspace version and appends an event. A later publication is a new issue. This intentionally retains history even if two issues contain the same assignment arrangement.

## Versions cover the whole workspace

Every write requires the version last read by the client. `BEGIN IMMEDIATE` serializes the version check, validation, mutation, version increment and event write. Two clients submitting version N cannot both succeed. A read also uses a transaction so its tables and version come from one coherent snapshot.

The version includes request submission and review, not just assignments. This can cause a harmless extra refresh but keeps the small app's concurrency contract clear. The app has no background autosave. A network failure after submission has an uncertain outcome; refresh the workspace before retrying. Version checks prevent a retried old mutation from being applied twice.

## Time and validation

The seed defines one local event day. Intervals are half-open: `[09:00,10:00)` and `[10:00,11:00)` do not overlap. One availability window must contain the entire shift; disconnected windows cannot be combined across a break. Eligibility, availability, existing duplicate assignments, capacity and overlap are checked before any assignment write. Publication independently verifies all constraints and complete coverage.

The default five-shift fixture includes a half-hour offset that creates a conflict even across different roles. Capacity is modeled explicitly and may exceed one, though the small fixture uses one volunteer per shift.

## Reassignments are proposals

A pending request refers to a specific shift and original volunteer. It validates the proposed replacement at submission but changes no assignment. Approval requires that the original assignment still exists and revalidates the replacement against the current draft. Only then are removal, replacement, request status, event and version committed together. A failed approval remains pending; declining it changes no assignments. Multiple pending requests for the same original assignment are refused.

## A deliberately small local boundary

Python's HTTP server is a development server. It binds to IPv4 loopback and accepts the exact printed Host. Mutating requests require a matching Origin and JSON Content-Type; browser fetch metadata also rejects cross-site requests. This reduces browser-driven local request risks, but does not authenticate an operator or block another local process.

Only three static assets and fixed API paths are served. The server never maps a requested filename directly to disk. Requests have a bounded body, exact fields, positive bounded integer IDs, duplicate JSON-key/header rejection, strict UTF-8, no surrogate characters and no non-finite JSON constants. The UI uses textContent and explicit DOM nodes for all data. A Content Security Policy disallows inline scripts and framing. No request bodies are logged.

Database paths are CLI inputs controlled by the local operator. Database files and local environment files are ignored by version control. Seed uses exclusive file creation and refuses even an empty existing file; it provides no destructive reset flag.

## Kept outside the demonstration

There is no authentication, multi-tenant authorization, durable background job, optimized roster generation or deployed service. The fixture itself supplies valid roles, windows and shift definitions; it has no editing API for those inputs. A production scheduler would need migrations, backups, access control, actual dates/time zones, operational monitoring and a production server. Those would obscure the assignment and publication boundaries this portfolio project is designed to demonstrate.
