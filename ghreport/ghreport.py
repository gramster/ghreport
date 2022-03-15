from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import time
from typing import List, Optional
import asyncio
from github import Github
import pytz
import httpx
import gidgethub.httpx
import matplotlib.pyplot as plt
from bokeh.plotting import figure, output_file, show, save
from bokeh.embed import components
from bokeh.models import HoverTool, Range1d, Title
from bokeh.io import output_notebook


plt.style.use('seaborn-whitegrid')


@dataclass
class Event:
    when: datetime
    actor: str
    event: str
    arg: str
        

@dataclass
class Issue:
    number: int
    title: str
    created_by: str
    created_at: datetime 
    closed_at: datetime
    first_team_response_at: datetime # first comment by team
    last_team_response_at: datetime # last comment by team   
    last_op_response_at: datetime # last comment by OP   
    last_response_at: datetime # last comment by anyone         
    events: List[Event]
    is_bug: bool


def get_users_for_repo(owner:str, repo:str, token:str):
    """ 
    Get the team members for a repo that have push or admin rights. This is not
    public so if you are not in such a team (probably with admin rights) this will fail.
    """
    g = Github(token)
    ghrepo = g.get_repo(f'{owner}/{repo}')    
    rtn = set()
    try:
        for team in ghrepo.get_teams():
            if team.permission not in ["push", "admin"]:
                continue
            try:
                for member in team.get_members():
                    rtn.add(member.login)
            except Exception:
                pass
    except Exception:
        print(f"Couldn't get teams for repo {owner}/{repo}") 
    return rtn


issues_query = """
query ($repo: String!, $cursor: String, $chunk: Int) {
  rateLimit {
    remaining
    cost
    resetAt
  }
  repository(owner: "microsoft", name: $repo) {
    issues(first: $chunk, after: $cursor) {
      totalCount
      pageInfo {
        endCursor
        hasNextPage
      }
      nodes {
        number
        title
        createdAt
        closedAt        
        author {
          login
        }
        timelineItems(
          first: 100
          itemTypes: [LABELED_EVENT, UNLABELED_EVENT, ISSUE_COMMENT]
        ) {
          nodes {
            __typename
            ... on LabeledEvent {
              label {
                name
              }
              actor {
                login
              }
              createdAt
            }
            ... on UnlabeledEvent {
              label {
                name
              }
              actor {
                login
              }
              createdAt
            }
            ... on IssueComment {
              author {
                login
              }
              createdAt
              lastEditedAt
            }
            ... on AssignedEvent {
              assignee {
                ... on User {
                  login
                }
              }
              createdAt              
            }
            ... on UnassignedEvent {
              assignee {
                ... on User {
                  login
                }
              }
              createdAt               
            }
          }
        }
      }
    }
  }
}
"""

utc=pytz.UTC


def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)


def date_diff(d1, d2):
    return utc_to_local(d1) - utc_to_local(d2)


def get_who(obj, prop):
    if prop in obj:
        v = obj[prop]
        if v:
            return v['login']
    return None


def parse_date(datestr):
    return utc_to_local(datetime.strptime(datestr, '%Y-%m-%dT%H:%M:%SZ'))


def parse_raw_issue(issue, users, bug_label = 'bug'):
    try:
        number = issue['number']
        title = issue['title']
        created_by = get_who(issue, 'author')
        created_at = parse_date(issue['createdAt'])
        closed_at = None
        if issue['closedAt']:
            closed_at = parse_date(issue['createdAt'])        

        events = []
        is_bug = False

        # Treat the initial description as a response if by a team member    
        response_at = created_at if created_by in users else None
        first_team_response_at = response_at
        last_team_response_at = response_at
        last_op_response_at = response_at
        last_response_at = response_at

        for event in issue['timelineItems']['nodes']:
            typename = event['__typename']
            eventtime = parse_date(event['createdAt'])
            if typename == 'LabeledEvent':
                lbl = event['label']['name']
                if lbl == bug_label:
                    is_bug = True
                who = get_who(event, 'actor')                    
                e = Event(eventtime, who, 'labeled', lbl)
            elif typename == 'UnlabeledEvent':
                lbl = event['label']['name']
                if lbl == bug_label:
                    is_bug = False   
                who = get_who(event, 'actor')                    
                e = Event(eventtime, who, 'unlabeled', lbl)
            elif typename == 'AssignedEvent':
                who = get_who(event, 'assignee')                
                e = Event(eventtime, who, 'assigned', '')
            elif typename == 'UnassignedEvent':
                who = get_who(event, 'assignee')                
                e = Event(eventtime, who, 'unassigned', '') 
            elif typename == 'IssueComment':
                l = event['lastEditedAt']
                if l:
                    eventtime = parse_date(event['lastEditedAt'])
                who = get_who(event, 'author')               
                if who in users:
                    last_team_response_at = eventtime
                    if first_team_response_at is None:
                        first_team_response_at = eventtime
                if who == created_by:
                    last_op_response_at = eventtime
                last_response_at = eventtime
                e = Event(eventtime, who, 'comment', '')
            else:
                # Should never happen
                print(f'Unknown event type {typename}')
                continue
            events.append(e)
    except Exception as e:
        print(f'Failed to parse issue\n{issue}: {e}')
                                         
    return Issue(number, title, created_by, created_at, closed_at,        
                 first_team_response_at, last_team_response_at,
                 last_op_response_at, last_response_at,
                 events, is_bug)   


async def get_raw_issues(owner:str, repo:str, token:str, chunk:int = 25, verbose:bool = False):
    cursor = None
    issues = []
    count = 0
    total_cost = 0
    total_requests = 0
    remaining = 0

    async with httpx.AsyncClient() as client:
        gh = gidgethub.httpx.GitHubAPI(client, owner,
                                       oauth_token=token)
        reset_at = None
        while True:
            result = await gh.graphql(issues_query, repo=repo, cursor=cursor, chunk=chunk)
            limit = result['rateLimit']                
            reset_at = parse_date(limit['resetAt'])                

            total_requests += 1
            data = result['repository']['issues']
            if 'nodes' in data:
                for issue in data['nodes']:
                    issues.append(issue)  # Maybe extend is possible; playing safe

            if data['pageInfo']['hasNextPage']:
                cursor = has_more = data['pageInfo']['endCursor']
            else:
                break
                
            total_cost += limit['cost']
            remaining = limit['remaining']
            
            if limit['cost'] * 3 > remaining:
                # Pre-emptively rate limit
                sleep_time = date_diff(reset_at, datetime.now()).seconds + 1
                print(f'Fetched {count} issues of {data["totalCount"]} but need to wait {sleep_time} seconds')
                time.sleep(sleep_time)               
 
    if verbose:
        print(f'GitHub API stats for {repo}:')
        print(f'  Total requests: {total_requests}')
        print(f'  Total cost: {total_cost}')     
        print(f'  Average cost per request: {total_cost / total_requests}')
        print(f'  Remaining: {remaining}')
    return issues


def get_issues(owner:str, repo:str, token:str, users:set, chunk:int = 25, raw_issues=None,
               bug_label:str = 'bug', verbose:bool = False):
    if raw_issues is None:
        # non-Jupyter case
        # Next line won't work in Jupyter; instead we have to get raw issues in 
        # one cell and then do this in another cell        
        raw_issues = asyncio.run(get_raw_issues(owner, repo, token, chunk=chunk, verbose=verbose)) 
    issues = {}    
    for issue in raw_issues:
        issues[issue['number']] = parse_raw_issue(issue, users, bug_label=bug_label)
    return issues


def filter_issues(issues:List[Issue], when:datetime,
                  must_include_labels:List[str], must_exclude_labels:Optional[List[str]]=None):
    for i in issues:
        created_at = utc_to_local(i.created_at)
        if created_at > when:
            continue

        if i.closed_at is not None:
            closed_at = utc_to_local(i.closed_at)            
            if closed_at < when:
                continue
                
        labels = set()
        for e in i.events:
            if e.when > when:
                break
            if e.event == 'labeled':
                labels.add(e.arg)
            elif e.event == 'unlabeled' and e.arg in labels:
                labels.remove(e.arg)
        match = True
        for l in must_include_labels:
            if l not in labels:
                match = False
                break
        if must_exclude_labels:
            for l in must_exclude_labels:
                if l in labels:
                    match = False
                    break
        if not match:
            continue
        yield i

        
def plot_line(data, title:str, x_title:str, y_title:str, x_axis_type=None, width=0.9):  
    x = sorted([k for k in data.keys()])
    y = [data[k] for k in x]
    max_y = max(y)
    # Need vbar x param as list of strings else bars aren't centered  
    x_range = x
    if not x_axis_type:
        x_axis_type="linear"
    if x_axis_type == "linear":
        x_range = [str(v) for v in x]
        
    p = figure(tools="save", background_fill_color="#efefef", #x_range=x_range, 
               x_axis_type=x_axis_type, toolbar_location="below")
    p.line(x=x, y=y, color="navy")
    p.xgrid.grid_line_color = None
    p.ygrid.grid_line_color = "white"
    p.grid.grid_line_width = 2
    p.xaxis.major_label_text_font_size="12pt"
    p.add_layout(Title(text=title, align="center"), "above")
    p.add_layout(Title(text=x_title, align="center"), "below")
    p.add_layout(Title(text=y_title, align="center"), "left")   
    p.y_range = Range1d(0, int(max_y * 1.2 + 1))
    return p
    
    
def plot_bug_rate(start:datetime, end:datetime, issues:List[Issue], who:str,
                  must_include_labels:List[str], must_exclude_labels:Optional[List[str]]=None, interval=7,
                  web:bool=False):
    counts = []
    dates = []
    counts = {}
    last = None
    while start < end:
        start_local = utc_to_local(start)
        l = filter_issues(issues, start_local, must_include_labels, must_exclude_labels)
        count = len(list(l))
        counts[start] = count
        start += timedelta(days=interval)
        last = count
    plot = plot_line(counts, f"Open bug count for {who}", "Date", "Count", x_axis_type="datetime", width=7)
    if web:
        return components(plot)
    else:
        save(plot)
        return None, None


def txtissue(repo_path: str, issue: Issue):
    return f'{repo_path}/issues/{issue.number}'


def htmlissue(repo_path: str, issue: Issue):
    title = issue.title.replace('"', "&quot;")
    return f'<a title="{title}" href="{repo_path}/issues/{issue.number}">{issue.number}</a>'


def txt(line: str, tag: str = None):
    return f'{line}\n'


def html(line: str, tag: str = None):
    if tag is None:
        tag = 'div'
    return f'<{tag}>{line}</{tag}>\n'


def find_revisits(owner:str, repo:str, issues:List[Issue], users:set, web: bool=False):
    repo_path = f'https://github.com/{owner}/{repo}'
    
    output = html if web else txt
    urler = htmlissue if web else txtissue

    report = output('In lists below, * marks items that are new to report in past day\n')

    for bug_flag in [True, False]:
        report += output(f'FOR ISSUES THAT ARE{"" if bug_flag else " NOT"} MARKED AS BUGS:\n', 'h2')
        title_done = False
        now = datetime.now()
        for issue in issues:
            if issue.is_bug != bug_flag:
                continue
            # has the OP responded after a team member?
            if not issue.closed_at and not issue.last_team_response_at:
                if not title_done:
                    report += output(f'\nIssues in {repo} that need a response from team:', 'h3')
                    title_done = True
                days = date_diff(now, issue.created_at).days
                report += output(f'{"*" if days <= 1 else " "} {urler(repo_path, issue)} : needs an initial team response ({days} days old)')

        title_done = False
        for issue in issues:
            if issue.is_bug != bug_flag:
                continue            
            # has the OP responded after a team member?
            if issue.closed_at or not issue.last_team_response_at:
                continue
            if issue.last_op_response_at and issue.last_op_response_at > issue.last_team_response_at:
                if not title_done:
                    report += output(f'\nIssues in {repo} that have new comments from OP:', 'h3')
                    title_done = True 
                op_days = date_diff(now, issue.last_op_response_at).days 
                team_days = date_diff(now, issue.last_team_response_at).days            
                report += output(f'{"*" if op_days <= 1 else " "} {urler(repo_path, issue)} : OP responded {op_days} days ago but team last responded {team_days} days ago')

        title_done = False
        # TODO: if we get this running daily, we should make it so it only shows new instances that
        # weren't reported before. For now we asterisk those.
        for issue in issues:
            if issue.is_bug != bug_flag:
                continue            
            if issue.closed_at:
                continue
            elif issue.last_team_response_at and issue.last_response_at > issue.last_team_response_at:
                other_days = date_diff(now, issue.last_response_at).days 
                team_days = date_diff(now, issue.last_team_response_at).days 
                diff = team_days - other_days
                if diff >= 3:
                    if not title_done:
                        report += output(f'\nIssues in {repo} that have newer comments from 3rd party 3 days or more after last team response:', 'h3')
                        title_done = True          
                    report += output(f'{"*" if diff == 3 else " "} {urler(repo_path, issue)} : 3rd party responded {other_days} days ago but team last responded {team_days} days ago')


        title_done = False
        for issue in issues:
            if issue.is_bug != bug_flag:
                continue            
            if issue.closed_at:
                continue
            elif issue.created_by in users:
                continue
            elif issue.last_team_response_at and issue.last_response_at == issue.last_team_response_at:
                days = date_diff(now, issue.last_response_at).days
                if days < 30:
                    continue
                if not title_done:
                    report += output(f'\nIssues in {repo} that have no external responses since team response in 30+ days:', 'h3')
                    title_done = True            
                report += output(f'{"*" if days == 30 else " "} {urler(repo_path, issue)} : team response was last response and no others in {days} days')
        if bug_flag:
            report += output('\n=================================================================\n')

    return report



def report(owner, repo, token, web=False, verbose=False, extra_users=None, bug_label='bug', chart=None, days=180, chunk=25):
    # Get the users in the team
    users = get_users_for_repo(owner, repo, token)
    if extra_users:
        for u in extra_users.split(','):
            if u:
                users.add(u)

    issues = get_issues(owner, repo, token, users, chunk=chunk, bug_label=bug_label, verbose=verbose)
    now = datetime.now()

    if web or chart:
        if chart:
            output_file(chart)
        script, div = plot_bug_rate(now-timedelta(days=days), now, issues.values(), repo, [bug_label], interval=1, web=web)
    else:
        script, div = '', ''

    report = find_revisits(owner, repo, issues.values(), users, web)

    if web:
        print(f"""
<!DOCTYPE html>
<html lang="en">
    <head>
        <meta charset="utf-8">
        <title>Repo report for {owner}/{repo} at {now}</title>
        <script src="https://cdn.bokeh.org/bokeh/release/bokeh-2.4.2.min.js"></script>
        {script}
    </head>
    <body>
    {div}
    {report}
    </body>
</html>""")
    else:
        print(report)


