import abc
import base64
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import io
from json import dumps
import os
import time
import asyncio
from typing import Any, Callable, Generator, Iterable, Sequence
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
import wordcloud


def median(numbers: list[int]) -> int:
    # Strictly speaking if there are an even number of elelemts in the 
    # list the median is the mean of the two middle elements. But we'll
    # just return the lower of the two middle elements. That avoids
    # turning ints into floats and is good enough for our purposes.
    sorted_numbers = sorted(numbers)
    n = len(sorted_numbers)
    return sorted_numbers[n // 2]
    

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


@dataclass
class PullRequest:
    created_at: datetime 
    merged_at: datetime | None


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


issues_with_comments_query = """
query ($cursor: String, $chunk: Int) {{
  search(query: "repo:{owner}/{repo} type:issue state:{state} created:>={since}", type:ISSUE, first: $chunk, after: $cursor) {{
    issueCount
    pageInfo {{
      endCursor
      hasNextPage
    }}    
    edges {{
      node {{
        ... on Issue {{
          number
          title
          createdAt
          closedAt        
          author {{
            login
          }}
          editor {{
            login
          }}
          timelineItems(
            first: 100
            itemTypes: [CLOSED_EVENT, LABELED_EVENT, UNLABELED_EVENT, ISSUE_COMMENT]
          ) {{
            nodes {{
              __typename
              ... on ClosedEvent {{
                actor {{
                  login
                }}
                createdAt
              }}
              ... on LabeledEvent {{
                label {{
                  name
                }}
                actor {{
                  login
                }}
                createdAt
              }}
              ... on UnlabeledEvent {{
                label {{
                  name
                }}
                actor {{
                  login
                }}
                createdAt
              }}
              ... on IssueComment {{
                author {{
                  login
                }}
                createdAt
                lastEditedAt
              }}
              ... on AssignedEvent {{
                assignee {{
                  ... on User {{
                    login
                  }}
                }}
                createdAt              
              }}
              ... on UnassignedEvent {{
                assignee {{
                  ... on User {{
                    login
                  }}
                }}
                createdAt               
              }}
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""
# Arguments with ! are required.
issues_with_comments_query_old = """
query ($owner: String!, $repo: String!, $state: IssueState!, $since: DateTime!, $cursor: String, $chunk: Int) {
  rateLimit {
    remaining
    cost
    resetAt
  }
  repository(owner: $owner, name: $repo) {
    issues(states: [$state], first: $chunk, after: $cursor, filterBy: { since: $since }) {
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

issues_without_comments_query = """
query ($cursor: String, $chunk: Int) {{
  search(query: "repo:{owner}/{repo} type:issue state:{state} created:>={since}", type:ISSUE first: $chunk, after: $cursor) {{
    issueCount
    pageInfo {{
      endCursor
      hasNextPage
    }}    
    edges {{
      node {{
        ... on Issue {{
          number
          title
          createdAt
          closedAt        
          author {{
            login
          }}
          editor {{
            login
          }}
          timelineItems(
            first: 100
            itemTypes: [CLOSED_EVENT, LABELED_EVENT, UNLABELED_EVENT]
          ) {{
            nodes {{
              __typename
              ... on ClosedEvent {{
                actor {{
                  login
                }}
                createdAt
              }}
              ... on LabeledEvent {{
                label {{
                  name
                }}
                actor {{
                  login
                }}
                createdAt
              }}
              ... on UnlabeledEvent {{
                label {{
                  name
                }}
                actor {{
                  login
                }}
                createdAt
              }}
              ... on AssignedEvent {{
                assignee {{
                  ... on User {{
                    login
                  }}
                }}
                createdAt              
              }}
              ... on UnassignedEvent {{
                assignee {{
                  ... on User {{
                    login
                  }}
                }}
                createdAt               
              }}
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""

# A variant of the above that skips comments and can limit to recent issues.
issues_without_comments_query_old = """
query ($owner: String!, $repo: String!, $state: IssueState!, $since: DateTime!, $cursor: String, $chunk: Int) {
  rateLimit {
    remaining
    cost
    resetAt
  }
  repository(owner: $owner, name: $repo) {
    issues(states: [$state], first: $chunk, after: $cursor, filterBy: { since: $since }) {
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
          itemTypes: [CLOSED_EVENT, LABELED_EVENT, UNLABELED_EVENT]
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

# These query gets pull requests, so we can calculate the time to merge.
# We actually seem to need two, as state:merged doesn't seem to work.
# So one query will get state:STATE PRs, and another will ignore state
# but look at merged:<DATE.

pull_requests_query = """
query ($cursor: String, $chunk: Int) {{
  search(query: "repo:{owner}/{repo} is:pr state:{state} created:>={since}", type:ISSUE, first: $chunk, after: $cursor) {{
    issueCount
    pageInfo {{
      endCursor
      hasNextPage
    }}    
    edges {{
      node {{
        ... on PullRequest {{
          createdAt
          mergedAt        
        }}
      }}
    }}
  }}
}}
"""

merged_pull_requests_query = """
query ($cursor: String, $chunk: Int) {{
  search(query: "repo:{owner}/{repo} is:pr created:>={since} merged:<={until}", type:ISSUE, first: $chunk, after: $cursor) {{
    issueCount
    pageInfo {{
      endCursor
      hasNextPage
    }}    
    edges {{
      node {{
        ... on PullRequest {{
          createdAt
          mergedAt        
        }}
      }}
    }}
  }}
}}
"""

# Arguments with ! are required.
pull_requests_query_old = """
query ($owner: String!, $repo: String!, $state: PullRequestState!, $cursor: String, $chunk: Int) {
    rateLimit {
        remaining
        cost
        resetAt
    }
    repository(owner: $owner, name: $repo) {
        pullRequests(states: [$state], first: $chunk, after: $cursor) {
            totalCount
            pageInfo {
                endCursor
                hasNextPage
            }
            nodes {
                createdAt
                mergedAt        
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


def parse_raw_pull_request(pull_request: dict) -> PullRequest | None:
    try:
        created_at: datetime = parse_date(pull_request['createdAt'])
        merged_at: datetime | None = parse_date(pull_request['mergedAt']) if pull_request['mergedAt'] else None
    except Exception as e:
        print(f'Failed to parse pull_request\n{pull_request}: {e}')
        return None
                                         
    return PullRequest(created_at, merged_at)


def get_active_labels(events: list[Event], at:datetime|None=None) -> set[str]:
    labels = set()
    for e in events:
        if at and e.when > at:
            break
        if e.event == 'labeled':
            labels.add(e.arg)
        elif e.event == 'unlabeled' and e.arg in labels:
            labels.remove(e.arg)

    return labels
    

def parse_raw_issue(issue: dict, members: set[str]) -> Issue | None:
    try:
        number = issue['number']
        title = issue['title']
        created_by: str = get_who(issue, 'author', 'UNKNOWN')
        closed_by: str | None = None
        created_at: datetime = parse_date(issue['createdAt'])
        closed_at: datetime | None = parse_date(issue['closedAt']) if issue['closedAt'] else None
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
                 last_op_response_at, last_response_at, events)


async def get_raw_pull_requests(owner:str, repo:str, token:str, state:str = 'open', \
                                chunk:int = 500, since: datetime|None=None,
                                verbose:bool = False) -> list[dict]:
    cursor = None
    pull_requests = []
    count = 0
    total_cost = 0
    total_requests = 0
    remaining = 0

    if since is None:
        since = datetime.now() - timedelta(days=365*10)

    # Format the date as required by the GitHub API
    since_str = since.astimezone(pytz.utc).strftime('%Y-%m-%d')
    until_str = datetime.now().astimezone(pytz.utc).strftime('%Y-%m-%d')

    async with httpx.AsyncClient() as client:
        gh = gidgethub.httpx.GitHubAPI(client, owner,
                                       oauth_token=token)
        if state == 'merged':
            query = merged_pull_requests_query.format(owner=owner, repo=repo,
                                                      since=since_str, until=until_str)
        else:
            query = pull_requests_query.format(owner=owner, repo=repo, state=state,
                                                    since=since_str)
        
        while True:
            result = await gh.graphql(query, cursor=cursor, chunk=chunk)
              
            total_requests += 1
            data = result['search']
            if 'edges' in data:
                for pull_request in data['edges']:
                    pull_requests.append(pull_request['node'])

            if data['pageInfo']['hasNextPage']:
                cursor = data['pageInfo']['endCursor']
            else:
                break
                              

    if verbose:
        print(f'GitHub API stats for {repo}:')
        print(f'  Total requests: {total_requests}')
        print(f'  Total cost: {total_cost}')     
        print(f'  Average cost per request: {total_cost / total_requests}')
        print(f'  Remaining: {remaining}')
    return pull_requests


async def get_raw_issues(owner:str, repo:str, token:str, state:str = 'open', \
                         chunk:int = 100, include_comments: bool = True, 
                         since: datetime|None=None, verbose:bool = False) -> list[dict]:
    cursor = None
    issues = []
    count = 0
    total_cost = 0
    total_requests = 0
    remaining = 0

    if since is None:
        since = datetime.now() - timedelta(days=365*10)

    # Format the date as required by the GitHub API
    since_str = since.astimezone(pytz.utc).strftime('%Y-%m-%d')

    async with httpx.AsyncClient() as client:
        gh = gidgethub.httpx.GitHubAPI(client, owner,
                                       oauth_token=token)
        reset_at = None

        if include_comments:
            query = issues_with_comments_query.format(owner=owner, repo=repo, state=state, since=since_str)
        else:
            query = issues_without_comments_query.format(owner=owner, repo=repo, state=state, since=since_str)

        while True:
            result = await gh.graphql(query, cursor=cursor, chunk=chunk)                
              
            total_requests += 1
            data = result['search']
            if 'edges' in data:
                for issue in data['edges']:
                    issues.append(issue['node'])  # Maybe extend is possible; playing safe

            if data['pageInfo']['hasNextPage']:
                cursor = data['pageInfo']['endCursor']
            else:
                break
                 
    if verbose:
        print(f'GitHub API stats for {repo}:')
        print(f'  Total requests: {total_requests}')
        print(f'  Total cost: {total_cost}')     
        print(f'  Average cost per request: {total_cost / total_requests}')
        print(f'  Remaining: {remaining}')
    return issues


def get_pull_requests(owner:str, repo:str, token:str, state: str='open', \
               chunk:int = 100, raw_pull_requests: list[dict[str,str]]|None=None, \
               since: datetime|None=None, verbose:bool = False) -> list[PullRequest]:
    if raw_pull_requests is None:
        # non-Jupyter case
        # Next line won't work in Jupyter; instead we have to get raw issues in 
        # one cell and then do this in another cell        
        raw_pull_requests = asyncio.run(get_raw_pull_requests(owner, repo, token, 
                                                state=state, chunk=chunk, 
                                                since=since,
                                                verbose=verbose)) 
    pull_requests = []    
    for issue in raw_pull_requests:
        parsed_pull_request = parse_raw_pull_request(issue)
        if parsed_pull_request:
            pull_requests.append(parsed_pull_request)
    return pull_requests


def get_issues(owner:str, repo:str, token:str, members:set[str], state: str='open', \
               chunk:int = 25, raw_issues: list[dict[str,str]]|None=None, \
               include_comments: bool = True, since: datetime|None=None,
               verbose:bool = False) -> dict[str, Issue]:
    if raw_issues is None:
        # non-Jupyter case
        # Next line won't work in Jupyter; instead we have to get raw issues in 
        # one cell and then do this in another cell        
        raw_issues = asyncio.run(get_raw_issues(owner, repo, token, 
                                                state=state, chunk=chunk, 
                                                include_comments=include_comments, 
                                                since=since,
                                                verbose=verbose)) 
    issues = {}    
    for issue in raw_issues:
        parsed_issue = parse_raw_issue(issue, members)
        if parsed_issue:
            issues[issue['number']] = parsed_issue
    return issues


def filter_issues(issues: Iterable[Issue], 
                       must_include_labels:list[str]|None=None, 
                       must_exclude_labels:list[str]|None=None,
                       must_be_created_by: set[str]|None=None, 
                       must_not_be_created_by: set[str]|None = None,
                       must_be_open_at:datetime|None=None) -> Generator[Issue, None, None]:
    """
    Get issues that were open at the given time and have (or don't have) the given labels.
    """
    for i in issues:
        if must_be_created_by and i.created_by not in must_be_created_by:
            continue
        if must_not_be_created_by and i.created_by in must_not_be_created_by:
            continue
        if must_be_open_at:
            created_at = utc_to_local(i.created_at)
            if created_at > must_be_open_at:
                continue

            if i.closed_at is not None:
                closed_at = utc_to_local(i.closed_at)            
                if closed_at < must_be_open_at:
                    continue
                
        if must_include_labels or must_exclude_labels:
          labels = get_active_labels(i.events, at=must_be_open_at)
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

        
def plot_data(data, title:str, x_title:str, y_title:str, x_axis_type=None, 
              width=0.9, chart_type:str='line'):
    x = data.keys()  #sorted([k for k in data.keys()])
    y = [data[k] for k in x]
    max_y = max(y) if y else 0
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

    # Plot the line or bar
    if chart_type == "line":
        ax.plot(x, y, color="navy")
    elif chart_type == "bar":
        ax.bar(x, y, color="navy", width=width)
    elif chart_type == "barh":
        ax.barh(x, y, color="navy", height=0.5)
    else:
        raise ValueError(f"Unknown chart type {chart_type}")

    # Customize grid lines
    ax.grid(True, which='both', linewidth=2)
    ax.xaxis.grid(False)  # Remove x-axis grid lines
    ax.yaxis.grid(True, color='white')  # Set y-axis grid lines to white

    # Set axis labels and title
    ax.set_title(title, fontsize=16, pad=20)
    if chart_type == "barh":
        ax.set_ylabel(x_title, fontsize=12, labelpad=15)
        ax.set_xlabel(y_title, fontsize=12, labelpad=15)
    else:
        ax.set_xlabel(x_title, fontsize=12, labelpad=15)
        ax.set_ylabel(y_title, fontsize=12, labelpad=15)
        # Set y-axis range
        ax.set_ylim(0, int(max_y * 1.2 + 1))

    # Adjust font size for x-axis labels
    ax.tick_params(axis='x', labelsize=8)    
    fig.tight_layout()
    

class FormatterABC(abc.ABC):
    def __init__(self, as_table: bool, outdir: str|None):
        self.as_table = as_table
        self.outdir = outdir

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
    @abc.abstractmethod
    def plot(self, name:str|None=None) -> str: ...    
    @abc.abstractmethod
    def report(self, org: str, repo: str, now: datetime, 
               report: str, termranks: str, 
               charts: list[str]) -> str: ...


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
    def __init__(self, as_table: bool, outdir: str|None):
        super().__init__(as_table, outdir)

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
    
    def plot(self, name:str|None=None) -> str:
        # Save the plot to an in-memory buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        # Encode the image to base64
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        return f'<img src="data:image/png;base64,{img_base64}">'
    
    def report(self, org: str, repo: str, now: datetime, report: str,
               termranks: str, charts: list[str]) -> str:
        sections = [report]
        sections.extend(charts)
        sections.append(termranks)        
        section_sep = '<br>\n<br>\n'
        return f"""<!DOCTYPE html>
<html lang="en">
    <head>
        <meta charset="utf-8">
        <title>Repo report for {org}/{repo} on {format_date(now)}</title>
    </head>
    <body>
    {section_sep.join(sections)}
    </body>
</html>"""
    

class TextFormatter(FormatterABC):
    def __init__(self, as_table: bool, outdir: str|None):
        super().__init__(as_table, outdir)

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
    
    def plot(self, name:str|None=None) -> str:
        return ''
         
    def report(self, org: str, repo: str, now: datetime, report: str,
               termranks: str, charts: list[str]) -> str:
        return report + '\n\n' + termranks
             

class MarkdownFormatter(FormatterABC):
    def __init__(self, as_table: bool, outdir: str|None):
        super().__init__(as_table, outdir)

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

    def plot(self, name:str|None=None) -> str:
        # Ideally we would render the plot with inline data, but this doesn't work
        # in GitHub markdown preview.
        # Instead we have to save the plot to file and link to it. But we don't want
        # lots of files lying around so we just use the same name and hope for the best.
        # If outdir is specified, create the file there, else just use the current directory.
        if name is None:
            return ''
        fname = name + '.png'
        dest = os.path.join(self.outdir, fname) if self.outdir is not None else fname
        plt.savefig(dest)
        return f'![]({fname})'                    

    def report(self, org: str, repo: str, now: datetime, report: str,
               termranks: str, charts: list[str]) -> str:
        sections = [report]
        sections.extend(charts)
        sections.append(termranks)
        return '\n\n'.join(sections)
    

def plot_open_bugs(formatter: FormatterABC, start:datetime, end:datetime, issues:list[Issue], who:str, 
                  must_include_labels:list[str], must_exclude_labels:list[str]|None=None, interval=7) -> str:
    counts = []
    dates = []
    counts = {}
    last = None
    while start < end:
        start_local = utc_to_local(start)
        l = filter_issues(issues, must_include_labels, must_exclude_labels, must_be_open_at=start_local)
        count = len(list(l))
        counts[start] = count
        start += timedelta(days=interval)
        last = count
    plot_data(counts, f"Open bug count for {who}", "Date", "Count", x_axis_type="datetime", width=7)
    return formatter.plot('bugcount')


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
        # TODO: see if the above TODO is still relevant :-)
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
    issues = get_issues(org, repo, token, members, state='closed', \
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


# Yes, I know its a code smell to have 'and' in a function name, but it seems silly to 
# have to do separate GraphQL queries for these two things.

async def get_issue_bodies_and_first_team_comments(issues: list[int], org: str, repo: str, 
                             token: str, members: set[str]) -> list[tuple[str,str]]:
    results = []
    dropped = 0
    async with httpx.AsyncClient() as client:
        gh = gidgethub.httpx.GitHubAPI(client, org, oauth_token=token)
        while issues:
            group = issues[:10]
            issues = issues[10:]
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


def get_training_data(org: str, repo: str, token: str, out: str|None=None, verbose: bool = False, \
                extra_members: str|None = None, 
                exclude_labels: list[str]|tuple[str,...] = ('bug', 'enhancement', 'needs-info'), chunk: int=25) -> None:
    """
    Get training data for an ML model to predict the first response by a team member to an issue.
    """
    members = get_team_members(org, repo, token, extra_members, verbose)
    candidates = get_training_candidates(org, repo, token, members, exclude_labels=list(exclude_labels), 
                                         verbose=verbose, chunk=chunk)
    results = asyncio.run(get_issue_bodies_and_first_team_comments(candidates, org, repo, token, members))
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

    cloud = wordcloud.WordCloud(width=800, height=600, max_words=50,
                                background_color='white').generate_from_frequencies({k: len(v) for k, v in sorted_terms})
    
    plt.imshow(cloud, interpolation='bilinear')
    plt.axis('off')
    cloud_text = formatter.plot('termcloud')

    report_sections = [cloud_text]
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


def calculate_medians(data: list[PullRequest]|list[Issue], 
                      get_start_date: Callable[[Any], datetime],
                      get_end_date: Callable[[Any], datetime]) -> dict[str, int]:
    # Gather the time range for each item and bucket by month
    months = {}
    for item in data:
        start = get_start_date(item)        
        end = get_end_date(item)
        if start is None or end is None:
            continue
        month = f'{start.year}-{start.month:02}'
        if month not in months:
            months[month] = []
        months[month].append(date_diff(end, start).days)

    # Calculate the medians
    medians = {}
    for month, times in months.items():
        medians[month[2:]] = median(times)    
    return medians


def plot_median_time_to_close_prs(formatter: FormatterABC, 
                                 org: str, repo: str, token: str, verbose: bool=False) -> str:
    """
    Get all closed PRs from the past year, then calculate the median time to close for each month,
    and return a chart of the results.  
    """
    now = datetime.now()
    since = now - timedelta(days=365)
    pull_requests = get_pull_requests(org, repo, token, state='merged', since=since, verbose=verbose)

    medians = calculate_medians(pull_requests, lambda x: x.created_at, lambda x: x.merged_at)

    # Plot the results  
    plot_data(medians, f"Median time to merge PRs for {org}/{repo}", "Month", "Days", width=0.9,
             chart_type='bar')
    return formatter.plot('median_time_to_merge_prs')


def plot_median_time_to_close_issues(formatter: FormatterABC,        
                                    org: str, repo: str, token: str, verbose: bool=False) -> str:
    """
    Get all closed issues from the past year, then calculate the median time to close for each month,
    and return a chart of the results.  
    """
    now = datetime.now()
    since = now - timedelta(days=365)
    issues = get_issues(org, repo, token, set(), state='closed', since=since, include_comments=False, verbose=verbose)

    medians = calculate_medians(list(issues.values()), lambda x: x.created_at, lambda x: x.closed_at)

    # Plot the results  
    plot_data(medians, f"Median time to close issues for {org}/{repo}", "Month", "Days", width=0.9,
             chart_type='bar')
    return formatter.plot('median_time_to_close_issues')


def plot_label_frequencies(formatter: FormatterABC, issues: list[Issue]):
    """ Get the current label frequencies and plot them. """
    labelcounts = {}
    now = utc_to_local(datetime.now())
    for issue in issues:
        labels = get_active_labels(issue.events, at=now)
        for label in labels:
            if label in labelcounts:
                labelcounts[label] += 1
            else:
                labelcounts[label] = 1

    # Sort the labels by count
    labelcounts = {k: v for k, v in sorted(labelcounts.items(), key=lambda item: item[1], reverse=True)}
    plot_data(labelcounts, "Label Frequencies", "Label", "Count", chart_type='barh')
    return formatter.plot('label_frequencies')
                       
                  
def create_report(org: str, issues_repo: str, token: str,
                  out: str|None=None, as_table:bool=False, verbose: bool=False, 
                  days: int=1, stale: int=30, extra_members: str|None=None,
                  bug_label: str ='bug', xrange: int=180, chunk: int=25, 
                  show_all: bool=False, pr_repo: str|None=None) -> None:
    # Initialize all the outputs here; makes it easy to comment out stuff
    # below when debugging
    report = termranks = open_bugs_chart = pr_close_time_chart = \
        issue_close_time_chart = label_frequency_chart = ''
    
    pr_repo = issues_repo if pr_repo is None else pr_repo
    # Make sure the folder exists for the file specified by out
    outdir = None
    if out is not None:
        outdir = os.path.dirname(out)
        if outdir and not os.path.exists(outdir):
            os.makedirs(outdir)
    # We don't include label params for feature request/needs info because we don't use them
    # in the report right now, although they might be useful in the future.
    fmt = out[out.rfind('.'):] if out is not None else '.txt'
    formatter = HTMLFormatter(as_table, outdir) if fmt == '.html' else \
                (MarkdownFormatter(as_table, outdir) if fmt == '.md' else \
                 TextFormatter(as_table, outdir))
    members = get_team_members(org, issues_repo, token, extra_members, verbose)
    issues = list(get_issues(org, issues_repo, token, members, state='open', \
                        chunk=chunk, verbose=verbose).values())   
    now = datetime.now()
    report = find_revisits(now, org, issues_repo, issues, members=members, bug_label=bug_label,
                           formatter=formatter, days=days, stale=stale, show_all=show_all)

    if show_all:
        termranks = find_top_terms(issues, formatter)
        if fmt != '.txt':
            open_bugs_chart = plot_open_bugs(formatter, now-timedelta(days=xrange), now,
                                             issues, issues_repo, [bug_label], interval=1)
            pr_close_time_chart = plot_median_time_to_close_prs(formatter, org, pr_repo, token, verbose)

            issue_close_time_chart = plot_median_time_to_close_issues(formatter, org, issues_repo,
                                                                      token, verbose)
            
            label_frequency_chart = plot_label_frequencies(formatter, issues)

    result = formatter.report(org, issues_repo, now, report, termranks, 
                              [open_bugs_chart, pr_close_time_chart, issue_close_time_chart,
                               label_frequency_chart])
    output_result(out, result, now)

