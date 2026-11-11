# Staffing Scheduler

Assign volunteers, publish a fixed schedule, and review change requests for a fictional science exhibition.

**Python 3.12+ · SQLite · JavaScript · No runtime dependencies**

[Full guide](docs/guide.md) · [Portfolio](https://github.com/dgoetz365) · [MIT license](LICENSE)

## Quick start

```sh
git clone https://github.com/dgoetz365/staffing-scheduler.git
cd staffing-scheduler
python app.py seed
python app.py serve
```

Open http://127.0.0.1:8766. The app is branded **Fieldwork** and starts with four of five places filled. Stop with Ctrl+C; restart with `serve` to keep working. `seed` refuses to overwrite an existing database.

On Windows, `py -3.12` can replace `python`. If you already cloned the repo, start with the Python commands from its root.

## Try it

Assign **Bea Flores** to **Build bench** and publish. Submit and approve a reassignment from **Mira Chen** to **Sam Reed**. The draft changes while published issue 1 stays fixed. Publish again to compare both schedules.

## Engineering highlights

- **Assignment rules:** eligibility, full-shift availability, capacity, and overlapping commitments are checked together.
- **Review at the right time:** approvals revalidate the current assignment and schedule.
- **Publication history:** immutable snapshots preserve each issued schedule; version checks reject stale edits.

[Application and storage](app.py) · [Tests](tests/) · [Engineering decisions](docs/decisions.md) · [Verification](docs/verification.md)

## Tests and scope

```sh
python -m unittest discover -s tests -v
```

A local, single-user demonstration with synthetic volunteers and seeded availability. It does not provide authentication, payroll, calendar integration, or schedule optimization. Browser rendering has not been verified.

Built by [Daniel Goetz](https://github.com/dgoetz365) as an independent portfolio example. Employer code and data are not included.
