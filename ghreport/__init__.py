"""
ghreport.

Usage:
  ghreport <owner> <repo> <token> [-w] [-v] [-d DAYS] [-a] [-s DAYS] [-u USERS] [-b LABEL] [-x DAYS] [-n NUM]
  ghreport -h | --help
  ghreport --version

Options:
  <owner>                 The Github repository owner.
  <repo>                  The Github repository name.
  <token>                 The Github API token used for authentication.
  -w --web                Generate HTML output (with inline bug count chart).
  -v --verbose            Show extra output like stats about GitHub API usage costs.
  -d DAYS --days=DAYS     Window size (days) for items in report as new (with '*'). [default: 7]
  -a --all                Show all relevant issues, not just those new in the window.
  -s DAYS --stale=DAYS    Window size (days) for marking issues with no 3rd party follow up as stale. [default: 30]
  -u USERS --users=USERS  Comma-separated list of extra users to consider as team members.
  -b LABEL --bug=LABEL    The label used to identify issues that are considered bugs. [default: bug]
  -x DAYS --xrange=DAYS   How many days to plot the chart for. [default: 180]
  -n NUM --num=NUM        How many issues to fetch per API request. [default: 25]
  -h --help               Show this screen.
  --version               Show version.

You normally should not need to use the num argument unless you are experiencing
timeouts from the GitHub API; in this case you may want to try a lower value.
"""

__version__ = '0.2'

from docopt import docopt
from .ghreport import report


def main():
    arguments = docopt(__doc__, version=__version__)
    owner = arguments['<owner>']
    repo = arguments['<repo>']
    token = arguments['<token>']
    web = arguments['--web']
    verbose = arguments['--verbose']
    all = int(arguments['--all'])
    days = int(arguments['--days'])
    stale = int(arguments['--stale'])
    extra_users = arguments['--users']
    bug_label = arguments['--bug']
    xrange = int(arguments['--xrange'])
    if xrange < 7:
        xrange = 7
    if days < 1:
        days = 1
    report(owner, repo, token, web, verbose, days=days, stale=stale, extra_users=extra_users, \
           bug_label=bug_label, xrange=xrange, show_all = all)
    
