"""ghreport - Github report generator. """

__version__ = '0.22'
import click
from .ghreport import get_training, get_training_details, create_report


@click.group()
@click.version_option(version=__version__)
def cli():
    """ghreport."""
    pass


@cli.command()
@click.argument('repo')
@click.argument('token')
@click.option('-o', '--out', type=click.Path(), help='Write output to specified file.')
@click.option('-T', '--table', is_flag=True, help='Output report sections as formatted tables (HTML or Markdown).')
@click.option('-v', '--verbose', is_flag=True, help='Show extra output like stats about GitHub API usage costs.')
@click.option('-d', '--days', default=1, type=int, help='Window size (days) for items in report as new (with "*").')
@click.option('-a', '--all', is_flag=True, help='Show all relevant issues, not just those new in the window.')
@click.option('-s', '--stale', default=30, type=int, help='Window size (days) for marking issues with no 3rd party follow up as stale.')
@click.option('-t', '--team', help='Comma-separated list of extra GitHub user logins to consider as team members.')
@click.option('-b', '--bug', default='bug', help='The label used to identify issues that are considered bugs.')
@click.option('-x', '--xrange', default=180, type=int, help='How many days to plot the chart for.')
@click.option('-n', '--num', default=25, type=int, help='How many issues to fetch per API request.')
def report(repo, token, out, table, verbose, days, all, stale, team, bug, xrange, num):
    """Generate a report for the given repository.

    For reports, output is plain text, unless -o is used and the file name ends in
    .html, in which case HTML with an embedded bug count chart will be written to the
    file, or if the file name ends in '.md', in which case Markdown will be used (no
    chart). The file name specified with -o will be formatted using strftime so you can
    add dynamic elements based on the current date.
    
    If -t is used and the list of users starts with '+', then we retrieve the user
    list from GitHub, and then add the specified users to that list. Getting the list
    from GitHub requires admin read privileges for the token. Without '+', we use just
    the users specified on the command line to define the team members.
    """
    
    owner, repo_name = repo.split('/')
    if xrange < 7:
        xrange = 7
    if days < 1:
        days = 1
    create_report(owner, repo_name, token, out, as_table=table, verbose=verbose, days=days, \
                  stale=stale, extra_members=team, bug_label=bug, xrange=xrange, show_all=all)


@cli.command()
@click.argument('repo')
@click.argument('token')
@click.option('-o', '--out', type=click.Path(), help='Write output to specified file.')
@click.option('-v', '--verbose', is_flag=True, help='Show extra output like stats about GitHub API usage costs.')
@click.option('-t', '--team', help='Comma-separated list of extra GitHub user logins to consider as team members.')
@click.option('-b', '--bug', default='bug', help='The label used to identify issues that are considered bugs.')
@click.option('-f', '--feat', default='feature', help='The label used to identify issues that are considered feature requests.')
@click.option('-i', '--info', default='needs-info', help='The label used to identify issues that are marked as needing more info.')
@click.option('-n', '--num', default=25, type=int, help='How many issues to fetch per API request.')
def training(repo, token, out, verbose, team, bug, feat, info, num):
    """Generate training data for fine tuning an LLM responder.

    For training, we find issues that are closed and are not tagged as bugs, feature-request
     or needs-info, where the team only responded once. The assumption is that
    the teams response was the correct one, and we can use this question and response to train
    an LLM responder to respond to similar questions. The output is a JSON file in this case
    which should be hand-cleaned before being used to train the LLM responder.
    
    You normally should not need to use the num argument unless you are experiencing
    timeouts from the GitHub API; in this case you may want to try a lower value.
    """
    owner, repo_name = repo.split('/')
    get_training(owner, repo_name, token, out, verbose=verbose, extra_members=team, exclude_labels=[bug, feat, info])


def main():
    cli()


