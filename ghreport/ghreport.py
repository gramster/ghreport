"""ghreport - thin orchestrator importing from core modules.

This module re-exports the public API for backward compatibility and
contains create_report() and training-data functions.
"""

import asyncio
from datetime import datetime, timedelta
import os

import httpx
import gidgethub.httpx
import pandas as pd
import pytz

# Re-export core types and functions for backward compatibility
from .core.models import Event, Issue, PullRequest
from .core.fetcher import get_raw_issues, get_raw_pull_requests
from .core.parser import (
    utc_to_local, date_diff, get_who, parse_date, format_date,
    parse_raw_pull_request, get_active_labels, parse_raw_issue,
    get_pull_requests, get_issues, filter_issues, filter_prs_by_time,
    set_timezone, median,
)
from .core.teams import get_members, get_team_members
from .core.formatters import (
    FormatterABC, HTMLFormatter, TextFormatter, MarkdownFormatter,
    plot_data, plot_ranges,
    plot_open_issue_counts, plot_time_to_close_prs,
    plot_time_to_close_issues, plot_time_to_first_response,
    plot_files_changed_per_pr, plot_lines_changed_per_pr,
    plot_label_frequencies, find_top_terms, find_top_files,
    find_revisits, find_pr_activity, find_closed_issues,
)
from .core.analyzer import (
    get_subset, calculate_ranges, calculate_medians,
)


create_debug_log = False
debug_log = ''


def output_result(out: str | None, result: str, now: datetime):
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
                            verbose: bool = False, chunk: int = 25) -> list[int]:
    issues = get_issues(org, repo, token, members, state='closed',
                        chunk=chunk, verbose=verbose)
    candidates = []
    for issue in filter_issues(issues.values(), must_exclude_labels=exclude_labels,
                               must_not_be_created_by=members):
        try:
            if len([e for e in issue.events if e.actor in members]) != 1:
                continue
        except:
            continue
        candidates.append(issue.number)
    return candidates


async def get_issue_bodies_and_first_team_comments(issues: list[int], org: str, repo: str,
                                                   token: str, members: set[str]) -> list[tuple[str, str]]:
    results = []
    dropped = 0
    async with httpx.AsyncClient(timeout=60) as client:
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
                if issue['body'].find('![image]') >= 0:
                    dropped += 1
                    continue
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


def get_training_data(org: str, repo: str, token: str, out: str | None = None, verbose: bool = False,
                      extra_members: str | None = None,
                      exclude_labels: list[str] | tuple[str, ...] = ('bug', 'enhancement', 'needs-info'),
                      chunk: int = 25) -> None:
    """Get training data for an ML model to predict the first response by a team member to an issue."""
    members = get_team_members(org, repo, token, extra_members, verbose)
    candidates = get_training_candidates(org, repo, token, members, exclude_labels=list(exclude_labels),
                                         verbose=verbose, chunk=chunk)
    results = asyncio.run(get_issue_bodies_and_first_team_comments(candidates, org, repo, token, members))
    print(f'Created {len(results)} training examples')
    result = pd.DataFrame(results, columns=['prompt', 'response']).to_json(orient='records')
    now = utc_to_local(datetime.now())
    output_result(out, result, now)


def create_report(org: str, issues_repo: str, token: str,
                  out: str | None = None, as_table: bool = False, verbose: bool = False,
                  days: int = 1, stale: int = 30, extra_members: str | None = None,
                  bug_label: str = 'bug', xrange: int = 180, chunk: int = 25,
                  show_all: bool = False, pr_repo: str | None = None, hotspots: bool = False,
                  timezone: str = 'America/Los_Angeles') -> None:
    global create_debug_log
    create_debug_log = False
    # Set the timezone
    set_timezone(timezone)
    # Initialize all the outputs here; makes it easy to comment out stuff
    # below when debugging
    report = termranks = open_issue_counts_chart = pr_close_time_chart = \
        issue_close_time_chart = label_frequency_chart = \
        files_changed_per_pr_chart = lines_changed_per_pr_chart = \
        first_response_time_chart = topfiles = ''
    
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
    # We get open and closed issues separately, as we only fetch last year of closed issues,
    # but get all open issues.
    open_issues = list(get_issues(org, issues_repo, token, members, state='open', \
                        chunk=chunk, verbose=verbose).values())   
    now = utc_to_local(datetime.now())
    since = now - timedelta(days=365)    
    closed_issues = list(get_issues(org, issues_repo, token, members, state='closed',
                                    since=since, verbose=verbose).values())
    
    # Get both open and closed/merged pull requests
    open_pull_requests = get_pull_requests(org, pr_repo, token, state='open', 
                                           verbose=verbose)
    closed_pull_requests = get_pull_requests(org, pr_repo, token, state='closed', since=since,
                                             verbose=verbose)
    merged_pull_requests = get_pull_requests(org, pr_repo, token, state='merged', since=since,
                                             verbose=verbose)

    report = find_revisits(now, org, issues_repo, open_issues, members=members, bug_label=bug_label,
                           formatter=formatter, days=days, stale=stale, show_all=show_all)

    # Add PR activity report
    pr_report = find_pr_activity(now, org, pr_repo, open_pull_requests, 
                                 closed_pull_requests + merged_pull_requests,
                                 formatter, days=days, show_all=show_all)
    report += pr_report

    # Add closed issues report
    closed_issues_report = find_closed_issues(now, org, issues_repo, closed_issues,
                                              formatter, days=days)
    report += closed_issues_report

    if show_all:
        termranks = find_top_terms(open_issues, formatter, verbose=verbose)
        if hotspots:
          topfiles = find_top_files(merged_pull_requests, formatter)
        if fmt != '.txt':
            open_issue_counts_chart = plot_open_issue_counts(formatter, now-timedelta(days=xrange), now,
                                                               open_issues, issues_repo, [bug_label], interval=1)
            pr_close_time_chart = plot_time_to_close_prs(formatter, org, pr_repo, merged_pull_requests)
            files_changed_per_pr_chart = plot_files_changed_per_pr(formatter, org, pr_repo, merged_pull_requests)
            lines_changed_per_pr_chart = plot_lines_changed_per_pr(formatter, org, pr_repo, merged_pull_requests)
            issue_close_time_chart = plot_time_to_close_issues(formatter, org, issues_repo,
                                                               closed_issues, verbose)
            
            first_response_time_chart = plot_time_to_first_response(formatter, org, issues_repo,
                                                                    open_issues, closed_issues, since=since,
                                                                    verbose=verbose)
                        
            label_frequency_chart = plot_label_frequencies(formatter, open_issues)

    result = formatter.report(org, issues_repo, now, report, termranks, topfiles,
                              [open_issue_counts_chart, pr_close_time_chart,
                               issue_close_time_chart, first_response_time_chart,
                               label_frequency_chart, files_changed_per_pr_chart,
                               lines_changed_per_pr_chart], debug_log)
    output_result(out, result, now)

