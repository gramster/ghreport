"""
ghreport.

Usage:
  ghreport <owner> <repo> <token> [-v|--verbose] [--users=USERS] [--bug=LABEL] [--chart=CHART] [--days=DAYS] [--num=NUM]
  ghreport -h | --help
  ghreport --version

Options:
  <owner>                 The Github repository owner.
  <repo>                  The Github repository name.
  <token>                 The Github API token used for authentication.
  -v --verbose            Show extra output like stats about GitHub API usage costs.
  -u USERS --users=USERS  Comma-separated list of extra users to consider as team members.
  -b LABEL --bug=LABEL    The label used to identify issues that are considered bugs [default: bug]
  -c CHART --chart=CHART  Filename to save a bug rate chart to.
  -d DAYS --days=DAYS     How many days to plot the chart for [default: 180]
  -n NUM --num=NUM        How many issues to fetch per API request [default: 25]
  -h --help               Show this screen.
  --version               Show version.

You normally should not need to use the num argument unless you are experiencing
timeouts from the GitHub API; in this case you may want to try a lower value.
"""

__version__ = '0.1'

from docopt import docopt
from .ghreport import report


def main():
    arguments = docopt(__doc__, version=__version__)
    owner = arguments['<owner>']
    repo = arguments['<repo>']
    token = arguments['<token>']
    verbose = arguments['--verbose']
    extra_users = arguments['--users']
    bug_label = arguments['--bug']
    chart = arguments['--chart']
    days = int(arguments['--days'])
    if days < 7:
        days = 7
    report(owner, repo, token, verbose, extra_users=extra_users, bug_label=bug_label, chart=chart, days=days)
    
