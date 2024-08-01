import abc
import base64
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import io
from json import dumps
import os
import time
import asyncio
from typing import Generator, Iterable, Sequence
from github import Github
import pytz
import httpx
import gidgethub.httpx
import matplotlib.pyplot as plt
#from bokeh.io import export_png
#from bokeh.plotting import figure, output_file, show, save
#from bokeh.embed import components
#from bokeh.models import HoverTool, Range1d, Title
#from bokeh.io import output_notebook
import pandas as pd
import seaborn as sns


#plt.style.use('bmh')


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
    closed_by: str|None
    created_at: datetime 
    closed_at: datetime | None
    first_team_response_at: datetime | None # first comment by team
    last_team_response_at: datetime | None # last comment by team   
    last_op_response_at: datetime | None # last comment by OP   
    last_response_at: datetime | None # last comment by anyone         
    events: list[Event]


def get_members(owner:str, repo:str, token:str) -> set[str]:
    """ 
    Get the team members for a repo that have push or admin rights. This is not
    public so if you are not in such a team (probably with admin rights) this will fail.
    I haven't found a good way to use the GraphQL API for this so still uses REST API.
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


# Arguments with ! are required.
issues_query = """
query ($owner: String!, $repo: String!, $state: IssueState!, $cursor: String, $chunk: Int) {
  rateLimit {
    remaining
    cost
    resetAt
  }
  repository(owner: $owner, name: $repo) {
    issues(states: [$state], first: $chunk, after: $cursor) {
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
        editor {
          login
        }
        timelineItems(
          first: 100
          itemTypes: [CLOSED_EVENT, LABELED_EVENT, UNLABELED_EVENT, ISSUE_COMMENT]
        ) {
          nodes {
            __typename
            ... on ClosedEvent {
              actor {
                login
              }
              createdAt
            }
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


def utc_to_local(utc_dt: datetime) -> datetime:
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)


def date_diff(d1: datetime, d2: datetime) -> timedelta:
    return utc_to_local(d1) - utc_to_local(d2)


def get_who(obj, prop: str, fallback: str|None = None) -> str:
    if prop in obj:
        v = obj[prop]
        if v:
            return v['login']
    if fallback:
        return fallback
    raise Exception(f'No {prop} in {obj}')


def parse_date(datestr: str) -> datetime:
    return utc_to_local(datetime.strptime(datestr, '%Y-%m-%dT%H:%M:%SZ'))


def format_date(d: datetime) -> str:
    return f'{d.year}-{d.month:02d}-{d.day:02d}'


def parse_raw_issue(issue: dict, members: set[str]) -> Issue | None:
    try:
        number = issue['number']
        title = issue['title']
        created_by: str = get_who(issue, 'author', 'UNKNOWN')
        closed_by: str | None = None
        created_at: datetime = parse_date(issue['createdAt'])
        closed_at: datetime | None = parse_date(issue['createdAt']) if issue['closedAt'] else None
        events = []

        # Treat the initial description as a response if by a team member    
        response_at = created_at if created_by in members else None
        first_team_response_at = response_at
        last_team_response_at = response_at
        last_op_response_at = response_at
        last_response_at = response_at

        for event in issue['timelineItems']['nodes']:
            typename = event['__typename']
            eventtime = parse_date(event['createdAt'])
            if typename == 'ClosedEvent':
                closed_by = get_who(event, 'actor', 'UNKNOWN')
                continue          
            elif typename == 'LabeledEvent':
                lbl = event['label']['name']
                who = get_who(event, 'actor', 'UNKNOWN')             
                e = Event(eventtime, who, 'labeled', lbl)
            elif typename == 'UnlabeledEvent':
                lbl = event['label']['name']
                who = get_who(event, 'actor', 'UNKNOWN')                    
                e = Event(eventtime, who, 'unlabeled', lbl)
            elif typename == 'AssignedEvent':
                who = get_who(event, 'assignee', 'UNKNOWN')                
                e = Event(eventtime, who, 'assigned', '')
            elif typename == 'UnassignedEvent':
                who = get_who(event, 'assignee', 'UNKNOWN')                
                e = Event(eventtime, who, 'unassigned', '') 
            elif typename == 'IssueComment':
                l = event['lastEditedAt']
                if l:
                    eventtime = parse_date(event['lastEditedAt'])
                who = get_who(event, 'author', 'UNKNOWN')               
                if who in members:
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
        return None
                                         
    return Issue(number, title, created_by, closed_by, created_at, closed_at,        
                 first_team_response_at, last_team_response_at,
                 last_op_response_at, last_response_at,
                 events)


async def get_raw_issues(query: str, owner:str, repo:str, token:str, state:str = 'OPEN', \
                         chunk:int = 25, verbose:bool = False) -> list[dict]:
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
            result = await gh.graphql(query, owner=owner, repo=repo, state=state, cursor=cursor, chunk=chunk)
            limit = result['rateLimit']                
            reset_at = parse_date(limit['resetAt'])                

            total_requests += 1
            data = result['repository']['issues']
            if 'nodes' in data:
                for issue in data['nodes']:
                    issues.append(issue)  # Maybe extend is possible; playing safe

            if data['pageInfo']['hasNextPage']:
                cursor = data['pageInfo']['endCursor']
            else:
                break
                
            total_cost += limit['cost']
            remaining = limit['remaining']
            
            if limit['cost'] * 3 > remaining:
                # Pre-emptively rate limit
                sleep_time = date_diff(reset_at, datetime.now()).seconds + 1
                print(f'Fetched {count} issues of {data["totalCount"]} but need to wait {sleep_time} seconds')
                await asyncio.sleep(sleep_time)               
 
    if verbose:
        print(f'GitHub API stats for {repo}:')
        print(f'  Total requests: {total_requests}')
        print(f'  Total cost: {total_cost}')     
        print(f'  Average cost per request: {total_cost / total_requests}')
        print(f'  Remaining: {remaining}')
    return issues


def get_issues(owner:str, repo:str, token:str, members:set[str], state: str='OPEN', \
               chunk:int = 25, raw_issues: list[dict[str,str]]|None=None, \
               verbose:bool = False) -> dict[str, Issue]:
    if raw_issues is None:
        # non-Jupyter case
        # Next line won't work in Jupyter; instead we have to get raw issues in 
        # one cell and then do this in another cell        
        raw_issues = asyncio.run(get_raw_issues(issues_query, owner, repo, token, state=state, chunk=chunk, verbose=verbose)) 
    issues = {}    
    for issue in raw_issues:
        parsed_issue = parse_raw_issue(issue, members)
        if parsed_issue:
            issues[issue['number']] = parsed_issue
    return issues


def filter_issues(issues: Iterable[Issue], must_include_labels:list[str]|None=None, must_exclude_labels:list[str]|None=None,
                  must_be_created_by: set[str]|None=None, must_not_be_created_by: set[str]|None = None,
                  when:datetime|None=None) -> Generator[Issue, None, None]:
    """
    Get issues that were open at the given time and have (or don't have) the given labels.
    """
    for i in issues:
        if must_be_created_by and i.created_by not in must_be_created_by:
            continue
        if must_not_be_created_by and i.created_by in must_not_be_created_by:
            continue
        if when:
            created_at = utc_to_local(i.created_at)
            if created_at > when:
                continue

            if i.closed_at is not None:
                closed_at = utc_to_local(i.closed_at)            
                if closed_at < when:
                    continue
                
        labels = set()
        for e in i.events:
            if when and e.when > when:
                break
            if e.event == 'labeled':
                labels.add(e.arg)
            elif e.event == 'unlabeled' and e.arg in labels:
                labels.remove(e.arg)
        match = True
        if must_include_labels:
            if not labels:
                match = False
            else:
                for l in must_include_labels:
                    if l not in labels:
                        match = False
                        break
        if must_exclude_labels and labels:
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
        
    # Set Seaborn style
    sns.set_theme(style="whitegrid")

    # Create the plot
    fig, ax = plt.subplots()

    # Set background color
    fig.set_facecolor('#efefef')
    ax.set_facecolor('#efefef')

    # Plot the line
    ax.plot(x, y, color="navy")

    # Customize grid lines
    ax.grid(True, which='both', linewidth=2)
    ax.xaxis.grid(False)  # Remove x-axis grid lines
    ax.yaxis.grid(True, color='white')  # Set y-axis grid lines to white

    # Set axis labels and title
    ax.set_title(title, fontsize=16, pad=20)
    ax.set_xlabel(x_title, fontsize=12, labelpad=15)
    ax.set_ylabel(y_title, fontsize=12, labelpad=15)

    # Set y-axis range
    ax.set_ylim(0, int(max_y * 1.2 + 1))

    # Adjust font size for x-axis labels
    ax.tick_params(axis='x', labelsize=12)    
    
    
def plot_open_bugs(start:datetime, end:datetime, issues:list[Issue], who:str,
                  must_include_labels:list[str], must_exclude_labels:list[str]|None=None, interval=7,
                  as_md: bool = False, outdir=None) -> str:
    counts = []
    dates = []
    counts = {}
    last = None
    while start < end:
        start_local = utc_to_local(start)
        l = filter_issues(issues, must_include_labels, must_exclude_labels, when=start_local)
        count = len(list(l))
        counts[start] = count
        start += timedelta(days=interval)
        last = count
    plot_line(counts, f"Open bug count for {who}", "Date", "Count", x_axis_type="datetime", width=7)
    if False:
        # Ideally we would follow this path and render the plot with inline
        # data, but this doesn't work in GitHub markdown preview.
        # Save the plot to an in-memory buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        # Encode the image to base64
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        return f"![](data:image/png;base64,{img_base64})" if as_md else \
                f'<img src="data:image/png;base64,{img_base64}">'
    else:
        # Instead we have to save the plot to file and link to it. But we don't want
        # lots of files lying around so we just use the same name and hope for the best.
        # If outdir is specified, create the file there, else just use the current directory.
        dest = 'bugcount.png' if outdir is None else os.path.join(outdir, 'bugcount.png')
        plt.savefig(dest)
        return '![](bugcount.png)' if as_md else f'<img src="bugcount.png">'
    return img_md


class FormatterABC(abc.ABC):
    def __init__(self, as_table: bool):
        self.as_table = as_table

    @abc.abstractmethod
    def url(self, repo_path: str, issue: Issue) -> str: ...
    @abc.abstractmethod
    def heading(self, level: int, msg: str) -> str: ...
    @abc.abstractmethod
    def info(self, msg: str) -> str: ...
    @abc.abstractmethod
    def line(self, star: bool, repo_path: str, issue: Issue, team=None, op=None, threep=None) -> str: ...
    @abc.abstractmethod
    def hline(self) -> str: ...
    @abc.abstractmethod
    def end_section(self) -> str: ...    
    @abc.abstractmethod
    def line_separator(self) -> str: ...

    def day_message(self, team=None, op=None, threep=None) -> str:
        rtn = '('
        if team is not None:
            rtn += f'TM:{team}, '
        if op is not None:
            rtn += f'OP:{op}, '
        if threep is not None:
            return f'3P:{threep}, '
        return rtn[:-2] + ')'

class HTMLFormatter(FormatterABC):
    def __init__(self, as_table: bool):
        super().__init__(as_table)

    def url(self, repo_path: str, issue: Issue) -> str:
        title = issue.title.replace('"', "&quot;")
        return f'<a title="{title}" href="{repo_path}/issues/{issue.number}">{issue.number}</a>'

    def info(self, msg: str) -> str:
        return f'<div>{msg}</div>\n'

    def heading(self, level: int, msg: str) -> str:
        rtn = f'<h{level}>{msg}</h{level}>\n'
        if level == 3 and self.as_table:
            rtn += '<table><tr><th>Days Ago</th><th>URL</th><th>Title</th></tr>\n'
        return rtn

    def line(self, star: bool, repo_path: str, issue: Issue, team=None, op=None, threep=None) -> str:
        days = self.day_message(team=team, op=op, threep=threep)
        if self.as_table:
            days = days[1:-1]  # remove ()
            return f'<tr><td>{"*" if star else " "}</td><td>{days}</td><td>{self.url(repo_path, issue)}</td><td>{issue.title}</td></tr>\n'
        else:
            return f'<div>{"*" if star else " "} {days} {self.url(repo_path, issue)}: {issue.title}</div>\n'

    def hline(self) -> str:
        return '\n<hr>\n'

    def end_section(self) -> str:
        return '</table>\n' if self.as_table else ''

    def line_separator(self) -> str:
        return '<br>\n'

class TextFormatter(FormatterABC):
    def __init__(self, as_table: bool):
        super().__init__(as_table)

    def url(self, repo_path: str, issue: Issue) -> str:
        return f'{repo_path}/issues/{issue.number}'

    def info(self, msg: str) -> str:
        return f'\n{msg}\n\n'

    def heading(self, level: int, msg: str) -> str:
        return f'\n{msg}\n\n'

    def line(self, star: bool, repo_path: str, issue: Issue, team=None, op=None, threep=None) -> str:
        days = self.day_message(team=team, op=op, threep=threep)        
        return f'{"*" if star else " "} {days} {self.url(repo_path, issue)}: {issue.title}\n'

    def hline(self) -> str:
        return '================================================================='

    def end_section(self) -> str:
        return ''

    def line_separator(self) -> str:
        return '\n'
    
class MarkdownFormatter(FormatterABC):
    def __init__(self, as_table: bool):
        super().__init__(as_table)

    def url(self, repo_path: str, issue: Issue) -> str:
        link = f'{repo_path}/issues/{issue.number}'
        title = issue.title.replace('"', '&quot;')
        return f'[{issue.number}]({link} "{title}")'

    def info(self, msg: str) -> str:
        return f'\n{msg}\n\n'

    def heading(self, level: int, msg: str) -> str:
        rtn = f'\n{"#"*level} {msg}\n\n'
        if level == 3 and self.as_table:
            rtn += '| Days Ago | Issue | Title |\n| --- | --- | --- |'
        return rtn

    def line(self, star: bool, repo_path: str, issue: Issue, team=None, op=None, threep=None) -> str:
        days = self.day_message(team=team, op=op, threep=threep)
        sep = ''
        term = '\n'
        if self.as_table:       
            sep = ' |'
            term = ''
            days = days[1:-1]  # remove ()

        if star:
            return f'\n{sep} \\* {days} {sep}{self.url(repo_path, issue)} {sep if sep else ":"}{issue.title}{sep}{term}'
        else:
            return f'\n{sep}  {days} {sep}{self.url(repo_path, issue)}{sep if sep else ":"} {issue.title}{sep}{term}'

    def hline(self) -> str:
        return '\n---\n'

    def end_section(self) -> str:
        return '\n'

    def line_separator(self) -> str:
        return '\n' if self.as_table else '\n\n'
            

def get_subset(issues:list[Issue], members: set[str], bug_flag: bool, bug_label: str = 'bug') -> Generator[Issue, None, None]:
    return filter_issues(issues, must_include_labels=[bug_label], must_not_be_created_by=members) if bug_flag \
            else filter_issues(issues, must_exclude_labels=[bug_label], must_not_be_created_by=members)


def find_revisits(now: datetime, owner:str, repo:str, issues:list[Issue], members:set[str], formatter: FormatterABC,
                  bug_label: str = 'bug', days: int=7, stale: int=30, show_all: bool=False):
    repo_path = f'https://github.com/{owner}/{repo}'
    
    report = formatter.heading(1, f'GITHUB ISSUES REPORT FOR {owner}/{repo}')
    report += formatter.info(f'Generated on {format_date(now)} using: stale={stale}, all={show_all}')
    if show_all:
        report += formatter.info(f'* marks items that are new to report in past {days} day(s)')
    else:
        report += formatter.info(f'Only showing items that are new to report in past {days} day(s)')

    shown = set()
    for bug_flag in [True, False]:
        top_title = formatter.heading(2, f'FOR ISSUES THAT ARE{"" if bug_flag else " NOT"} MARKED AS BUGS:')
        title_done = False
        now = datetime.now()
        for issue in get_subset(issues, members, bug_flag, bug_label):
            # has the OP responded after a team member?
            if not issue.closed_at and not issue.last_team_response_at:
                diff = date_diff(now, issue.created_at).days
                star = diff <= days
                if star or show_all:
                    if not title_done:
                        report += top_title
                        top_title = ''
                        report += formatter.heading(3, f'Issues in {repo} that need a response from team:')
                        title_done = True
                    shown.add(issue.number)
                    report += formatter.line(star, repo_path, issue, op=diff)
        if title_done:
            report += formatter.end_section()
            title_done = False

        for issue in get_subset(issues, members, bug_flag, bug_label):        
            # has the OP responded after a team member?
            if issue.closed_at or not issue.last_team_response_at or issue.number in shown:
                continue
            if issue.last_op_response_at and issue.last_op_response_at > issue.last_team_response_at:
                op_days = date_diff(now, issue.last_op_response_at).days 
                team_days = date_diff(now, issue.last_team_response_at).days            
                star = op_days <= days
                if star or show_all:
                    if not title_done:
                        report += top_title
                        top_title = ''
                        report += formatter.heading(3, f'Issues in {repo} that have comments from OP after last team response:')
                        title_done = True 
                    shown.add(issue.number)
                    report += formatter.line(star, repo_path, issue, op=op_days, team=team_days)

        if title_done:
            report += formatter.end_section()
            title_done = False

        # TODO: if we get this running daily, we should make it so it only shows new instances that
        # weren't reported before. For now we asterisk those.
        for issue in get_subset(issues, members, bug_flag, bug_label):
            if issue.closed_at or issue.number in shown:
                continue
            elif issue.last_response_at is not None and issue.last_team_response_at is not None and \
                issue.last_response_at > issue.last_team_response_at:
                if issue.last_response_at > issue.last_team_response_at:
                    other_days = date_diff(now, issue.last_response_at).days 
                    team_days = date_diff(now, issue.last_team_response_at).days 
                    diff = team_days - other_days
                    star = other_days <= days
                    if star or show_all:
                        if not title_done:
                            report += top_title
                            top_title = ''
                            report += formatter.heading(3, f'Issues in {repo} that have comments from 3rd party after last team response:')
                            title_done = True          
                        shown.add(issue.number)
                        report += formatter.line(star, repo_path, issue, threep=other_days, team=team_days)

        if title_done:
            report += formatter.end_section()
            title_done = False

        for issue in get_subset(issues, members, bug_flag, bug_label):
            if issue.closed_at or issue.number in shown:
                continue
            elif issue.last_team_response_at and issue.last_response_at == issue.last_team_response_at:
                diff = date_diff(now, issue.last_response_at).days # type: ignore
                if diff < stale:
                    continue
                star = diff < (stale+days)
                if star or show_all:
                    if not title_done:
                        report += top_title
                        top_title = ''
                        report += formatter.heading(3, f'Issues in {repo} that have no external responses since team response in {stale}+ days:')
                        title_done = True            
                    shown.add(issue.number)
                    report += formatter.line(star, repo_path, issue, team=diff)

        if title_done:
            report += formatter.end_section()
            title_done = False

        if bug_flag:
            report += formatter.hline()

    return report


def get_team_members(org: str, repo: str, token: str, extra_members: str|None, verbose: bool) -> set[str]:
    members = set()
    if extra_members:
        if extra_members.startswith('+'):
            members = get_members(org, repo, token)
            if verbose:
                print(f'Team Members (from GitHub): {",".join(list(members))}')
            extra_members = extra_members[1:]
        members.update(extra_members.split(','))
    else:
        members = get_members(org, repo, token)
        if verbose:
            print(f'Team Members (from GitHub): {",".join(list(members))}')
    return members


def output_result(out: str|None, result: str, now: datetime):
    if out is not None:
        out = now.strftime(out)
        with open(out, 'w') as f:
            f.write(result)
    else:
        print(result)


def make_issue_query(org: str, repo: str, issues: list[int]) -> str:
    query = f"""
{{
  repository(name: "{repo}", owner: "{org}") {{
"""
    for i, num in enumerate(issues):
        query += f"""
    issue{i}: issue(number: {num}) {{
        title
        body
        comments(
          first: 5
        ) {{
          nodes {{
            author {{
              login
            }}
            body         
          }}
        }}
    }}
"""
    query += """
    }
}
"""
    return query


def get_training_candidates(org: str, repo: str, token: str, members: set[str], exclude_labels: list[str],
                            verbose:bool = False, chunk: int=25) -> list[int]:
    # Get closed issues that are not marked as bugs or feature requests or needing info and were not
    # created by team members.
    issues = get_issues(org, repo, token, members, state='CLOSED', \
                        chunk=chunk, verbose=verbose)
    candidates = []
    for issue in filter_issues(issues.values(), must_exclude_labels=exclude_labels,
                               must_not_be_created_by=members):
        # Restrict further to issues which have only one response by team members.
        try:
            if len([e for e in issue.events if e.actor in members]) != 1:
                continue
        except:
            continue
        candidates.append(issue.number)
    return candidates


async def get_training_details(candidates: list[int], org: str, repo: str, 
                               token: str, members: set[str]) -> list[tuple[str,str]]:
    results = []
    dropped = 0
    async with httpx.AsyncClient() as client:
        gh = gidgethub.httpx.GitHubAPI(client, org, oauth_token=token)
        while candidates:
            group = candidates[:10]
            candidates = candidates[10:]
            query = make_issue_query(org, repo, group)
            raw_issues = await gh.graphql(query)                                  
            data = raw_issues['repository']
            for i in range(10):
                key = f'issue{i}'
                if key not in data:
                    break
                issue = data[key]
                if issue is None:
                    continue
                # If the issue body has embedded images, we can't use it as training data.
                if issue['body'].find('![image]') >= 0:
                    dropped += 1
                    continue
                # Find the first comment by a team member.
                team_comment = None
                for comment in issue['comments']['nodes']:
                    if comment['author']['login'] in members:
                        team_comment = comment['body']
                        break
                if team_comment is None:
                    continue

                results.append((f'{issue["title"]}\n\n{issue["body"]}', team_comment))

    print(f'Dropped {dropped} issues with embedded images')
    return results


def get_training(org: str, repo: str, token: str, out: str|None=None, verbose: bool = False, \
                extra_members: str|None = None, 
                exclude_labels: list[str]|tuple[str,...] = ('bug', 'enhancement', 'needs-info'), chunk: int=25) -> None:
    members = get_team_members(org, repo, token, extra_members, verbose)
    candidates = get_training_candidates(org, repo, token, members, exclude_labels=list(exclude_labels), 
                                         verbose=verbose, chunk=chunk)
    results = asyncio.run(get_training_details(candidates, org, repo, token, members))
    print(f'Created {len(results)} training examples')
    result = pd.DataFrame(results, columns=['prompt', 'response']).to_json(orient='records')
    now = datetime.now()
    output_result(out, result, now)


def find_top_terms(issues:list[Issue], formatter: FormatterABC, min_count:int=5):
    """
    Find the most common terms in the issue titles. First we remove common words and then
    count the remaining words. We then sort them by count.
    """
    stopwords = ['a', 'an', 'the', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from',
                  'as', 'is', 'are', 'be', 'it', 'this', 'that', 'these', 'those', 'there', 'here', 'where', 
                  'when', 'how', 'why', 'what', 'which', 'who', 'whom', 'whose', 'i', 'you', 'he', 'she', 
                  'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'mine', 'your', 'yours', 
                  'his', 'her', 'hers', 'its', 'our', 'ours', 'their', 'theirs', 'myself', 'yourself', 
                  'himself', 'herself', 'itself', 'ourselves', 'yourselves', 'themselves', 'all',
                  'cannot', 'without', 'name', 'vs', 'pylance', 'python', 'show', 'add', 'support',
                  'not', 'after', 'does', 'no', 'working', 'doesn\'t', 'can\'t', 'won\'t', 'shouldn\'t',
                  'unable', 'visual', 'studio', 'up', 'if', 'only', 'microsoft', 'using', '-',
                  'work', 'should', 'vscode', 'don\'t', 'offer', 'over', 'incorrect', 'inside',
                  'being', 'could', 'go', 'showing', 'have', 'shown', 'even', 'has', 'instead',
                  'recognized', 'issue', 'new', 'allow', 'fails', 'out', 'long', 'available', 
                  'problem', 'get', 'until', 'can', 'like', 'debugpy']
    issues_with_term = {}
    for issue in issues:
        title = issue.title.lower()
        for word in title.split():
            if word in stopwords:
                continue
            if word in issues_with_term:
                # Don't add issues  more than once
                if issue not in issues_with_term[word]:
                    issues_with_term[word].append(issue)
            else:
                issues_with_term[word] = [issue]                 

    # Sort issues_with_term by length of list descending
    sorted_terms = sorted(issues_with_term.items(), key=lambda x: len(x[1]), reverse=True)
    report_sections = []
    now = datetime.now()
    for term, issues in sorted_terms:
        if len(issues) < min_count:
            break

        report_sections.append(
            formatter.heading(3, f"Issues with term '{term}'") + \
            ''.join([(formatter.line(False, '', i, \
                    op=date_diff(now, i.created_at).days)) for i in issues]) + \
            formatter.line_separator()
        )

        issues_with_term[term] = len(issues)

    return (formatter.line_separator() * 3).join(report_sections)


def create_report(org: str, repo: str, token: str, out: str|None=None, 
           as_table:bool=False, verbose: bool=False, days: int=1, stale: int=30, \
           extra_members: str|None=None, bug_label: str ='bug', \
           xrange: int=180, chunk: int=25, show_all: bool=False) -> None:
    # Make sure the folder exists for the file specified by out
    outdir = None
    if out is not None:
        outdir = os.path.dirname(out)
        if outdir and not os.path.exists(outdir):
            os.makedirs(outdir)
    # We don't include label params for feature request/needs info because we don't use them
    # in the report right now, although they might be useful in the future.
    fmt = out[out.rfind('.'):] if out is not None else '.txt'
    formatter = HTMLFormatter(as_table) if fmt == '.html' else \
                (MarkdownFormatter(as_table) if fmt == '.md' else \
                 TextFormatter(as_table))
    members = get_team_members(org, repo, token, extra_members, verbose)
    issues = list(get_issues(org, repo, token, members, state='OPEN', \
                        chunk=chunk, verbose=verbose).values())   
    now = datetime.now()
    report = find_revisits(now, org, repo, issues, members=members, bug_label=bug_label,
                           formatter=formatter, days=days, stale=stale, show_all=show_all)
    
    termranks = find_top_terms(issues, formatter)
    if fmt == '.txt':
        result = report + '\n\n' + termranks
    else:
        if show_all:
            open_bugs_chart = plot_open_bugs(now-timedelta(days=xrange), now, issues,
                               repo, [bug_label], interval=1, as_md=(fmt=='.md'),
                               outdir=outdir)
        else:
            open_bugs_chart = ''
        if fmt == '.md':
            result = open_bugs_chart + '\n\n' + report + '\n\n' + termranks
        else:
            result = f"""<!DOCTYPE html>
<html lang="en">
    <head>
        <meta charset="utf-8">
        <title>Repo report for {org}/{repo} on {format_date(now)}</title>
    </head>
    <body>
    {open_bugs_chart}
    <br>
    <br>    
    {report}
    <br>
    <br>
    {termranks}
    </body>
</html>"""

    output_result(out, result, now)



     
