"""
ghreport.

Usage:
  ghreport report <repo> <token> [-o FILE] [-v] [-d DAYS] [-a] [-s DAYS] [-t USERS] [-b LABEL] [-x DAYS] [-n NUM]
  ghreport training <repo> <token> [-o FILE] [-v] [-t USERS] [-b LABEL] [-f LABEL] [-i LABEL] [-n NUM]
  ghreport -h | --help
  ghreport --version

Options:
  <repo>                  The Github repository (e.g. gramster/ghreport).
  <token>                 The Github API token used for authentication.
  -o FILE --out=FILE      Write output to specified file.
  -v --verbose            Show extra output like stats about GitHub API usage costs.
  -d DAYS --days=DAYS     Window size (days) for items in report as new (with '*'). [default: 1]
  -a --all                Show all relevant issues, not just those new in the window.
  -s DAYS --stale=DAYS    Window size (days) for marking issues with no 3rd party follow up as stale. [default: 30]
  -t USERS --team=USERS   Comma-separated list of extra GitHub user logins to consider as team members.
  -b LABEL --bug=LABEL    The label used to identify issues that are considered bugs. [default: bug]
  -f LABEL --feat=LABEL   The label used to identify issues that are considered feature requests. [default: feature]
  -i LABEL --info=LABEL   The label used to identify issues that are marked as needing more info. [default: needs-info]
  -x DAYS --xrange=DAYS   How many days to plot the chart for. [default: 180]
  -n NUM --num=NUM        How many issues to fetch per API request. [default: 25]
  --training              Special report to generate training data for fine tuning an LLM responder.
  -h --help               Show this screen.
  --version               Show version.

For reports, output is plain text, unless -o is used and the file name ends in
.html, in which case HTML with an embedded bug count chart will be written to the
file, or if the file name ends in '.md', in which case Markdown will be used (no
chart). The file name specified with -o will be formatted using strftime so you can
add dynamic elements based on the current date.

If -t is used and the list of users starts with '+', then we retrieve the user
list from GitHub, and then add the specified users to that list. Getting the list
from GitHub requires admin read privileges for the token. Without '+', we use just
the users specified on the command line to define the team members.

For training, we find issues that are closed and are not tagged as bugs, feature-request
 or needs-info, where the team only responded once. The assumption is that
the teams response was the correct one, and we can use this question and response to train
an LLM responder to respond to similar questions. The output is a JSON file in this case
which should be hand-cleaned before being used to train the LLM responder.

You normally should not need to use the num argument unless you are experiencing
timeouts from the GitHub API; in this case you may want to try a lower value.
"""

__version__ = '0.16'

from docopt import docopt, DocoptExit
from .ghreport import get_training, get_training_details, report


def main():
    arguments = docopt(__doc__, version=__version__)
    components = arguments['<repo>'].split('/')
    if len(components) == 2:
        owner, repo = components
    else:
        raise DocoptExit()

    token = arguments['<token>']
    out = arguments['--out']
    verbose = arguments['--verbose']
    all = bool(arguments['--all'])
    days = int(arguments['--days'])
    stale = int(arguments['--stale'])
    extra_members = arguments['--team']
    bug_label = arguments['--bug']
    feat_label = arguments['--feat']
    info_label = arguments['--info']
    xrange = int(arguments['--xrange'])
    if xrange < 7:
        xrange = 7
    if days < 1:
        days = 1
    if arguments['report']:
        report(owner, repo, token, out, verbose, days=days, stale=stale, extra_members=extra_members, \
               bug_label=bug_label, xrange=xrange, show_all = all)
    else:
        get_training(owner, repo, token, out, verbose, extra_members=extra_members, \
               exclude_labels=[bug_label, feat_label, info_label])
    
