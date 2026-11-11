# Fieldwork Scheduler

A runnable scheduling portfolio project for a fictional community science exhibition. Assign volunteers to stations, enforce availability and role constraints, publish immutable schedule issues, and review reassignments against the current draft.

**Python 3.12+ · SQLite · vanilla JavaScript · zero third-party dependencies**

All names, stations and scenarios are invented. This is an original local demonstration, not employer software or a production workforce system.

## Run locally

From this repository's root, with Python 3.12 or newer:

```sh
python app.py seed
python app.py serve
```

Open [http://127.0.0.1:8766](http://127.0.0.1:8766). On Windows, `py -3.12` may replace `python`. Stop with Ctrl+C; restart with the serve command to retain your changes. No install, build step or network service is required.

`seed` refuses to touch any existing database. To start a separate scenario, use `python app.py seed --db data/second.sqlite3` and serve that same path with `python app.py serve --db data/second.sqlite3`. The default database is `data/schedule.sqlite3`, relative to the application, not your terminal directory. Change the port with `--port 8767` if needed.

## Five-minute demonstration

1. **See a constraint reject a change.** Four of five places are filled. Under Build bench, select Sam Reed and assign. Sam is not a Maker; the assignment is rejected and nothing changes. Ellis Rowan is eligible but overlaps with the Water lab shift.
2. **Complete and publish.** Assign Bea Flores to Build bench. Publish the schedule, then open Published to inspect issue 1.
3. **Review a reassignment.** Open Change requests. Select Mira Chen's 09:00 Welcome desk assignment, choose Sam Reed, enter a reason and submit. Submission preserves the current assignment. Approve the change to replace Mira in the draft.
4. **Inspect the boundary.** The draft now lists Sam. Published issue 1 still lists Mira. Publish again and use the issue selector to compare both fixed schedules. History records each successful action.

To demonstrate review-time conflicts before approving step 3, remove Theo from the 09:00 Light lab and assign Sam there. Approval now fails because Sam overlaps. The request stays pending; decline it or resolve the conflict and try again.

To demonstrate concurrent edits, open two tabs. Change the draft in one, then attempt a change from the other. The older workspace version receives a conflict response and refreshes instead of overwriting newer work.

## What the code demonstrates

- Role eligibility, a full-shift availability window, capacity and half-open time interval overlap checks.
- A `BEGIN IMMEDIATE` transaction around each mutation, including its event and version increment. A rejected change writes nothing.
- Optimistic concurrency across assignments, requests, reviews and publication.
- Immutable, denormalized schedule snapshots. SQLite triggers also reject snapshot updates and deletes.
- Request-time and approval-time validation. A request cannot become an approval of a different original assignment.
- Exact HTTP route allowlists, 16 KiB JSON limits, duplicate-header/key rejection, Unicode checks, local Host/Origin validation and text-only DOM rendering.

See [engineering decisions](docs/decisions.md) for boundaries and tradeoffs, and [verification](docs/verification.md) for evidence and limitations.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests create temporary databases and bind a temporary loopback port. They cover persisted edits, safe reseeding, simultaneous stale writers, overlap boundaries, invalid assignments, immutable publication, review rollback and real HTTP requests. Optional JavaScript syntax check: `node --check static/app.js`.

## Scope

The roster, eligibility, availability and shifts are seeded scenario inputs. The UI edits assignments and reviews changes; it does not provide roster administration, optimization, authentication, notifications, time zones or payroll. One invented event day uses minutes since midnight. The server binds only to `127.0.0.1`; do not expose or deploy this development server. The local operator controls the database file and therefore is not an adversarial security boundary.

MIT License · Copyright 2026 Daniel Goetz.
