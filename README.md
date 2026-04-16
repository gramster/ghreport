# ghreport - Generate useful reports from GitHub repository issues

This utility generates reports that can be useful to identify issues in
your repository that may be stale, or that may need a response.

It can also generate a chart of open bug counts over time.

See CONTRIBUTING.md for build instructions, or install from PyPI with:

```
python -m pip install ghreport
```

Use `ghreport -h` for help.

For an example report, see https://github.com/gramster/ghreport/blob/main/example.md or you can see these in an automated form for my teams at **https://github.com/gramster/python-reports**

## Interactive Dashboard

ghreport includes an interactive web dashboard with multi-repo support, caching, and charts.

### Setup

Install the dashboard dependencies:

```
pip install ghreport[dashboard]
```

### Running

```
export GH_TOKEN=your_github_token
ghreport dashboard
```

On first run, a `config.toml` file is created automatically. Repos can be added from the web UI, or you can edit the config file directly:

```toml
[[repos]]
owner = "microsoft"
name = "debugpy"
bug_label = "bug"
```

The database is also seeded with default common team members (`dependabot`, `app/copilot-swe-agent`) which can be managed from the Team page.

The dashboard is available at `http://localhost:8000`. API docs are at `http://localhost:8000/docs`.

Options:
- `-p, --port` — Port (default: 8000)
- `-H, --host` — Host (default: 0.0.0.0)
- `-c, --config` — Path to TOML config file (created if missing)

### Features

- **Multi-repo support** — Track multiple repositories, add/remove from the UI
- **SQLite caching** — Reduces GitHub API calls with incremental sync
- **Background sync** — Periodic refresh via APScheduler
- **Reports** — Issue revisits, PR activity, closed issues (same as CLI)
- **Charts** — Open issue counts, time to merge/close/respond, label frequency, files/lines changed, top terms
- **Aggregate views** — Cross-repo summary and charts

### Frontend Development

The frontend is a Vue 3 + Vite SPA in `ghreport/dashboard/frontend/`:

```
cd ghreport/dashboard/frontend
npm install
npm run dev    # Dev server with API proxy to localhost:8000
npm run build  # Production build to dist/
```

## Development

This project uses `flit`. First install `flit`:

```
python -m pip install flit
```

Then to build:

```
flit build
```

To install locally:

```
flit install
```

To publish to PyPI:

```
flit publish
```

## Version History

0.1 Initial release

0.2 More control flags

0.3 Add -o option

0.4 Apply strftime to output file name

0.5 Added markdown support

0.6 Remove hardcoded owner from query

0.8 Better team option

0.9 Add proper markdown line rule

0.11 Fix 3rd party report; exclude issues created by team from other reports

0.12 Fix typo

0.14 Only fetch open issues

0.15 Fix non-async sleep.

0.16 Added ability to get LLM training data.

0.90 Swallow exception from matplotlib

0.91 More robust in the face of matplotlib plot failures

1.5 Current CLI version

2.0 Interactive web dashboard (FastAPI + Vue 3), core module extraction, multi-repo support, SQLite caching
