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
