"""Formatters and chart rendering for CLI output."""

import abc
import base64
from datetime import datetime, timedelta
import io
import os

import matplotlib.pyplot as plt
import seaborn as sns
import wordcloud

from .models import Event, Issue, PullRequest
from .parser import (
    date_diff, filter_issues, format_date, get_active_labels, utc_to_local,
)
from .analyzer import calculate_ranges, get_subset

# Set Seaborn style
sns.set_theme(style="whitegrid")


def plot_data(data, title: str, x_title: str, y_title: str, x_axis_type=None,
              width=0.9, chart_type: str = 'line', sort: bool = True):
    if sort:
        x = sorted([k for k in data.keys()])
    else:
        x = data.keys()
    y = [data[k] for k in x]
    max_y = max(y) if y else 0
    x_range = x
    if not x_axis_type:
        x_axis_type = "linear"
    if x_axis_type == "linear":
        x_range = [str(v) for v in x]

    if chart_type == "barh":
        fig, ax = plt.subplots(figsize=(8, len(x) * 0.25))
    else:
        fig, ax = plt.subplots()

    fig.set_facecolor('#efefef')
    ax.set_facecolor('#efefef')

    if chart_type == "line":
        ax.plot(x, y, color="navy")
    elif chart_type == "bar":
        ax.bar(x, y, color="navy", width=width)
    elif chart_type == "barh":
        ax.barh(x, y, color="navy", height=0.25)
    else:
        raise ValueError(f"Unknown chart type {chart_type}")

    ax.grid(True, which='both', linewidth=2)
    ax.xaxis.grid(False)
    ax.yaxis.grid(True, color='white')
    ax.set_title(title, fontsize=16, pad=20)
    if chart_type == "barh":
        ax.set_ylabel(x_title, fontsize=12, labelpad=15)
        ax.set_xlabel(y_title, fontsize=12, labelpad=15)
    else:
        ax.set_xlabel(x_title, fontsize=12, labelpad=15)
        ax.set_ylabel(y_title, fontsize=12, labelpad=15)
        ax.set_ylim(0, int(max_y * 1.2 + 1))

    ax.tick_params(axis='x', labelsize=8)
    try:
        fig.tight_layout()
    except:
        pass


def plot_ranges(data, title: str, x_title: str, y_title: str, width=0.9):
    x = sorted([k for k in data.keys()])
    y = [data[k] for k in x]

    fig, ax = plt.subplots()
    fig.set_facecolor('#efefef')
    ax.set_facecolor('#efefef')
    ax.boxplot(y, patch_artist=True, showmeans=False, showfliers=False)
    ax.grid(True, which='both', linewidth=2)
    ax.xaxis.grid(False)
    ax.yaxis.grid(True, color='white')
    ax.set_title(title, fontsize=16, pad=20)
    ax.set_xlabel(x_title, fontsize=12, labelpad=15)
    ax.set_ylabel(y_title, fontsize=12, labelpad=15)
    ax.tick_params(axis='x', labelsize=8)
    ax.set_xticks(range(1, 1 + len(data)), x)


class FormatterABC(abc.ABC):
    def __init__(self, as_table: bool, outdir: str | None):
        self.as_table = as_table
        self.outdir = outdir

    @abc.abstractmethod
    def issue_url(self, repo_path: str, issue: Issue) -> str: ...
    @abc.abstractmethod
    def pr_url(self, repo_path: str, pr: PullRequest) -> str: ...
    @abc.abstractmethod
    def issue_heading(self, level: int, msg: str) -> str: ...
    @abc.abstractmethod
    def pr_heading(self, level: int, msg: str) -> str: ...
    @abc.abstractmethod
    def info(self, msg: str) -> str: ...
    @abc.abstractmethod
    def issue_line(self, star: bool, repo_path: str, issue: Issue, team=None, op=None, threep=None) -> str: ...
    @abc.abstractmethod
    def pr_line(self, star: bool, repo_path: str, pr: PullRequest,
                closed_at: datetime | None = None, now: datetime | None = None) -> str: ...
    @abc.abstractmethod
    def hline(self) -> str: ...
    @abc.abstractmethod
    def end_section(self) -> str: ...
    @abc.abstractmethod
    def line_separator(self) -> str: ...
    @abc.abstractmethod
    def plot(self, name: str | None = None) -> str: ...
    @abc.abstractmethod
    def report(self, org: str, repo: str, now: datetime,
               report: str, termranks: str, topfiles: str,
               charts: list[str], debug_log: str = '') -> str: ...

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
    def __init__(self, as_table: bool, outdir: str | None):
        super().__init__(as_table, outdir)

    def issue_url(self, repo_path: str, issue: Issue) -> str:
        title = issue.title.replace('"', "&quot;")
        return f'<a title="{title}" href="{repo_path}/issues/{issue.number}">{issue.number}</a>'

    def pr_url(self, repo_path: str, pr: PullRequest) -> str:
        return f'<a href="{repo_path}/pull/{pr.number}">#{pr.number}</a>'

    def info(self, msg: str) -> str:
        return f'<div>{msg}</div>\n'

    def issue_heading(self, level: int, msg: str) -> str:
        rtn = f'<h{level}>{msg}</h{level}>\n'
        if level == 3 and self.as_table:
            rtn += '<table><tr><th>Days Ago</th><th>URL</th><th>Title</th></tr>\n'
        return rtn

    def pr_heading(self, level: int, msg: str) -> str:
        rtn = f'<h{level}>{msg}</h{level}>\n'
        if level == 3 and self.as_table:
            rtn += '<table><tr><th></th><th>PR</th><th>Created By</th><th>Created</th><th>Days Open</th><th>Closed/Merged</th><th>Closed/Merged By</th><th>Title</th></tr>\n'
        return rtn

    def issue_line(self, star: bool, repo_path: str, issue: Issue, team=None, op=None, threep=None) -> str:
        days = self.day_message(team=team, op=op, threep=threep)
        if self.as_table:
            days = days[1:-1]
            return f'<tr><td>{"*" if star else " "}</td><td>{days}</td><td>{self.issue_url(repo_path, issue)}</td><td>{issue.title}</td></tr>\n'
        else:
            return f'<div>{"*" if star else " "} {days} {self.issue_url(repo_path, issue)}: {issue.title}</div>\n'

    def pr_line(self, star: bool, repo_path: str, pr: PullRequest,
                closed_at: datetime | None = None, now: datetime | None = None) -> str:
        created_str = format_date(pr.created_at)
        actual_closed_at = closed_at if closed_at else (pr.merged_at or pr.closed_at)
        closed_str = format_date(actual_closed_at) if actual_closed_at else '-'
        closed_by_str = pr.closed_by if pr.closed_by else '-'

        if actual_closed_at:
            days_open = date_diff(actual_closed_at, pr.created_at).days
        elif now:
            days_open = date_diff(now, pr.created_at).days
        else:
            days_open = None
        days_open_str = str(days_open) if days_open is not None else '-'

        if self.as_table:
            return f'<tr><td>{"*" if star else " "}</td><td>{self.pr_url(repo_path, pr)}</td><td>{pr.created_by}</td><td>{created_str}</td><td>{days_open_str}</td><td>{closed_str}</td><td>{closed_by_str}</td><td>{pr.title}</td></tr>\n'
        else:
            days_msg = f' (open {days_open} days)' if days_open is not None and not actual_closed_at else (f' (was open {days_open} days)' if days_open is not None else '')
            return f'<div>{"*" if star else " "} {self.pr_url(repo_path, pr)}:{pr.title} by {pr.created_by} on {created_str}{days_msg}' + \
                   (f', closed/merged by {closed_by_str} on {closed_str}' if actual_closed_at else '') + '</div>\n'

    def hline(self) -> str:
        return '\n<hr>\n'

    def end_section(self) -> str:
        return '</table>\n' if self.as_table else ''

    def line_separator(self) -> str:
        return '<br>\n'

    def plot(self, name: str | None = None) -> str:
        try:
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            img_base64 = base64.b64encode(buf.read()).decode('utf-8')
            return f'<img src="data:image/png;base64,{img_base64}">'
        except:
            return ''

    def report(self, org: str, repo: str, now: datetime, report: str,
               termranks: str, topfiles: str, charts: list[str], debug_log: str = '') -> str:
        sections = [report, debug_log, topfiles]
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
    def __init__(self, as_table: bool, outdir: str | None):
        super().__init__(as_table, outdir)

    def issue_url(self, repo_path: str, issue: Issue) -> str:
        return f'{repo_path}/issues/{issue.number}'

    def pr_url(self, repo_path: str, pr: PullRequest) -> str:
        return f'{repo_path}/pull/{pr.number}'

    def info(self, msg: str) -> str:
        return f'\n{msg}\n\n'

    def issue_heading(self, level: int, msg: str) -> str:
        return f'\n{msg}\n\n'

    def pr_heading(self, level: int, msg: str) -> str:
        return f'\n{msg}\n\n'

    def issue_line(self, star: bool, repo_path: str, issue: Issue, team=None, op=None, threep=None) -> str:
        days = self.day_message(team=team, op=op, threep=threep)
        return f'{"*" if star else " "} {days} {self.issue_url(repo_path, issue)}: {issue.title}\n'

    def pr_line(self, star: bool, repo_path: str, pr: PullRequest,
                closed_at: datetime | None = None, now: datetime | None = None) -> str:
        created_str = format_date(pr.created_at)
        actual_closed_at = closed_at if closed_at else (pr.merged_at or pr.closed_at)
        closed_str = format_date(actual_closed_at) if actual_closed_at else '-'
        closed_by_str = pr.closed_by if pr.closed_by else '-'

        if actual_closed_at:
            days_open = date_diff(actual_closed_at, pr.created_at).days
        elif now:
            days_open = date_diff(now, pr.created_at).days
        else:
            days_open = None
        days_msg = f' (open {days_open} days)' if days_open is not None and not actual_closed_at else (f' (was open {days_open} days)' if days_open is not None else '')

        return f'{"*" if star else " "} {self.pr_url(repo_path, pr)}:{pr.title} by {pr.created_by} on {created_str}{days_msg}' + \
               (f', closed/merged by {closed_by_str} on {closed_str}' if actual_closed_at else '') + '\n'

    def hline(self) -> str:
        return '================================================================='

    def end_section(self) -> str:
        return ''

    def line_separator(self) -> str:
        return '\n'

    def plot(self, name: str | None = None) -> str:
        return ''

    def report(self, org: str, repo: str, now: datetime, report: str,
               termranks: str, topfiles: str, charts: list[str], debug_log: str = '') -> str:
        return '\n\n'.join([report, topfiles, termranks, debug_log])


class MarkdownFormatter(FormatterABC):
    def __init__(self, as_table: bool, outdir: str | None):
        super().__init__(as_table, outdir)

    def issue_url(self, repo_path: str, issue: Issue) -> str:
        link = f'{repo_path}/issues/{issue.number}'
        title = issue.title.replace('"', '&quot;')
        return f'[{issue.number}]({link} "{title}")'

    def pr_url(self, repo_path: str, pr: PullRequest) -> str:
        link = f'{repo_path}/pull/{pr.number}'
        return f'[#{pr.number}]({link})'

    def info(self, msg: str) -> str:
        return f'\n{msg}\n\n'

    def issue_heading(self, level: int, msg: str) -> str:
        rtn = f'\n{"#" * level} {msg}\n\n'
        if level == 3 and self.as_table:
            rtn += '| Days Ago | Issue | Title |\n| --- | --- | --- |'
        return rtn

    def pr_heading(self, level: int, msg: str) -> str:
        rtn = f'\n{"#" * level} {msg}\n\n'
        if level == 3 and self.as_table:
            rtn += '| | PR | Created By | Created | Days Open | Closed/Merged | Closed/Merged By | Title |\n| --- | --- | --- | --- | --- | --- | --- | --- |'
        return rtn

    def issue_line(self, star: bool, repo_path: str, issue: Issue, team=None, op=None, threep=None) -> str:
        days = self.day_message(team=team, op=op, threep=threep)
        sep = ''
        term = '\n'
        if self.as_table:
            sep = ' |'
            term = ''
            days = days[1:-1]

        if star:
            return f'\n{sep} \\* {days} {sep}{self.issue_url(repo_path, issue)} {sep if sep else ":"}{issue.title}{sep}{term}'
        else:
            return f'\n{sep}  {days} {sep}{self.issue_url(repo_path, issue)}{sep if sep else ":"} {issue.title}{sep}{term}'

    def pr_line(self, star: bool, repo_path: str, pr: PullRequest,
                closed_at: datetime | None = None, now: datetime | None = None) -> str:
        created_str = format_date(pr.created_at)
        actual_closed_at = closed_at if closed_at else (pr.merged_at or pr.closed_at)
        closed_str = format_date(actual_closed_at) if actual_closed_at else '-'
        closed_by_str = pr.closed_by if pr.closed_by else '-'

        if actual_closed_at:
            days_open = date_diff(actual_closed_at, pr.created_at).days
        elif now:
            days_open = date_diff(now, pr.created_at).days
        else:
            days_open = None
        days_open_str = str(days_open) if days_open is not None else '-'

        if self.as_table:
            star_str = '\\*' if star else ' '
            return f'\n| {star_str} | {self.pr_url(repo_path, pr)} | {pr.created_by} | {created_str} | {days_open_str} | {closed_str} | {closed_by_str} | {pr.title} |'
        else:
            days_msg = f' (open {days_open} days)' if days_open is not None and not actual_closed_at else (f' (was open {days_open} days)' if days_open is not None else '')
            return f'\n{"*" if star else " "} {self.pr_url(repo_path, pr)}:{pr.title} by {pr.created_by} on {created_str}{days_msg}' + \
                   (f', closed/merged by {closed_by_str} on {closed_str}' if actual_closed_at else '')

    def hline(self) -> str:
        return '\n---\n'

    def end_section(self) -> str:
        return '\n'

    def line_separator(self) -> str:
        return '\n' if self.as_table else '\n\n'

    def plot(self, name: str | None = None) -> str:
        if name is None:
            return ''
        fname = name + '.png'
        dest = os.path.join(self.outdir, fname) if self.outdir is not None else fname
        try:
            plt.savefig(dest)
            return f'![]({fname})'
        except:
            return ''

    def report(self, org: str, repo: str, now: datetime, report: str,
               termranks: str, topfiles: str, charts: list[str], debug_log: str = '') -> str:
        sections = [report, debug_log, topfiles]
        sections.extend(charts)
        sections.append(termranks)
        return '\n\n'.join(sections)


# ---------------------------------------------------------------------------
# Chart rendering functions (matplotlib, for CLI output)
# ---------------------------------------------------------------------------

def plot_open_issue_counts(formatter: FormatterABC, start: datetime, end: datetime,
                           issues: list[Issue], who: str,
                           bug_labels: list[str], interval=7) -> str:
    bug_counts = {}
    issue_counts = {}
    t = start
    while t < end:
        t_local = utc_to_local(t)
        bugs = filter_issues(issues, must_include_labels=bug_labels, must_be_open_at=t_local)
        all_issues = filter_issues(issues, must_be_open_at=t_local)
        bug_counts[t] = len(list(bugs))
        issue_counts[t] = len(list(all_issues))
        t += timedelta(days=interval)

    dates = sorted(issue_counts.keys())
    issue_y = [issue_counts[d] for d in dates]
    bug_y = [bug_counts[d] for d in dates]
    max_y = max(issue_y) if issue_y else 0

    fig, ax = plt.subplots()
    fig.set_facecolor('#efefef')
    ax.set_facecolor('#efefef')
    ax.plot(dates, issue_y, color='navy', label='All issues')
    ax.plot(dates, bug_y, color='crimson', label='Bugs')
    ax.legend()
    ax.grid(True, which='both', linewidth=2)
    ax.xaxis.grid(False)
    ax.yaxis.grid(True, color='white')
    ax.set_title(f'Open issue counts for {who}', fontsize=16, pad=20)
    ax.set_xlabel('Date', fontsize=12, labelpad=15)
    ax.set_ylabel('Count', fontsize=12, labelpad=15)
    ax.set_ylim(0, int(max_y * 1.2 + 1))
    ax.tick_params(axis='x', labelsize=8)
    try:
        fig.tight_layout()
    except:
        pass
    return formatter.plot('issuecounts')


def plot_time_to_close_prs(formatter: FormatterABC, org: str, repo: str,
                           pull_requests: list[PullRequest]) -> str:
    ranges = calculate_ranges(pull_requests, lambda x: x.created_at,
                              lambda x: date_diff(x.merged_at, x.created_at).days)
    plot_ranges(ranges, f"Time to merge PRs for {org}/{repo}", "Month", "Days", width=0.9)
    return formatter.plot('time_to_merge_prs')


def plot_time_to_close_issues(formatter: FormatterABC,
                              org: str, repo: str, issues: list[Issue], verbose: bool = False) -> str:
    ranges = calculate_ranges(issues, lambda x: x.created_at,
                              lambda x: date_diff(x.closed_at, x.created_at).days)
    plot_ranges(ranges, f"Time to close issues for {org}/{repo}", "Month", "Days", width=0.9)
    return formatter.plot('time_to_close_issues')


def plot_time_to_first_response(formatter: FormatterABC, org: str, issues_repo: str,
                                open_issues: list[Issue], closed_issues: list[Issue],
                                since: datetime, verbose: bool = False):
    issues = []
    issues.extend(open_issues)
    issues.extend(closed_issues)
    ranges = calculate_ranges(issues, lambda x: x.created_at,
                              lambda x: date_diff(x.first_team_response_at, x.created_at).days,
                              since=since)
    plot_ranges(ranges, f"Time to first team response for {org}/{issues_repo}", "Month", "Days", width=0.9)
    return formatter.plot('time_to_first_response')


def plot_files_changed_per_pr(formatter: FormatterABC,
                              org: str, repo: str, prs: list[PullRequest]) -> str:
    ranges = calculate_ranges(prs, lambda x: x.created_at, lambda x: x.files_changed)
    plot_ranges(ranges, f"Files changed per PR for {org}/{repo}", "Month", "Files", width=0.9)
    return formatter.plot('files_changed_per_pr')


def plot_lines_changed_per_pr(formatter: FormatterABC,
                              org: str, repo: str, prs: list[PullRequest]) -> str:
    ranges = calculate_ranges(prs, lambda x: x.created_at, lambda x: x.lines_changed)
    plot_ranges(ranges, f"Lines changed per PR for {org}/{repo}", "Month", "Lines", width=0.9)
    return formatter.plot('lines_changed_per_pr')


def plot_label_frequencies(formatter: FormatterABC, issues: list[Issue]):
    labelcounts = {}
    now = utc_to_local(datetime.now())
    for issue in issues:
        labels = get_active_labels(issue.events, at=now)
        for label in labels:
            if label in labelcounts:
                labelcounts[label] += 1
            else:
                labelcounts[label] = 1
    labelcounts = {k: v for k, v in sorted(labelcounts.items(), key=lambda item: item[1], reverse=True)}
    plot_data(labelcounts, "Label Frequencies", "Label", "Count", chart_type='barh', sort=False)
    return formatter.plot('label_frequencies')


def find_top_terms(issues: list[Issue], formatter: FormatterABC, min_count: int = 5, verbose: bool = False):
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
                if issue not in issues_with_term[word]:
                    issues_with_term[word].append(issue)
            else:
                issues_with_term[word] = [issue]

    sorted_terms = sorted(issues_with_term.items(), key=lambda x: len(x[1]), reverse=True)

    if not sorted_terms:
        return ''

    cloud = wordcloud.WordCloud(width=800, height=600, max_words=50,
                                background_color='white').generate_from_frequencies({k: len(v) for k, v in sorted_terms})

    plt.imshow(cloud, interpolation='bilinear')
    plt.axis('off')
    cloud_text = formatter.plot('termcloud')

    report_sections = [cloud_text]

    if verbose:
        now = utc_to_local(datetime.now())
        for term, issues_list in sorted_terms:
            if len(issues_list) < min_count:
                break

            report_sections.append(
                formatter.issue_heading(3, f"Issues with term '{term}'") +
                ''.join([(formatter.issue_line(False, '', i,
                                              op=date_diff(now, i.created_at).days)) for i in issues_list]) +
                formatter.line_separator()
            )

    return (formatter.line_separator() * 3).join(report_sections)


def find_top_files(pull_requests: list[PullRequest], formatter: FormatterABC, min_count: int = 5):
    files = {}
    for pr in pull_requests:
        for file in pr.files:
            if file in files:
                files[file] += 1
            else:
                files[file] = 1

    if not files:
        return ''

    sorted_files = sorted(files.items(), key=lambda x: x[1], reverse=True)
    sorted_files = [(k, v) for k, v in sorted_files if v >= min_count]

    title = formatter.issue_heading(2, 'MOST FREQUENTLY CHANGED FILES (by # of PRs):')
    as_table = formatter.as_table
    formatter.as_table = False
    result = title + formatter.line_separator().join([f'{v:3d}: {k}\n' for k, v in sorted_files])
    formatter.as_table = as_table
    return result


# ---------------------------------------------------------------------------
# Formatted report wrappers (used by CLI, call core logic directly)
# ---------------------------------------------------------------------------

def find_revisits(now: datetime, owner: str, repo: str, issues: list[Issue],
                  members: set[str], formatter: FormatterABC,
                  bug_label: str = 'bug', days: int = 7, stale: int = 30, show_all: bool = False):
    repo_path = f'https://github.com/{owner}/{repo}'

    report = formatter.issue_heading(1, f'GITHUB ISSUES REPORT FOR {owner}/{repo}')
    report += formatter.info(f'Generated on {format_date(now)} using: stale={stale}, all={show_all}')
    if show_all:
        report += formatter.info(f'* marks items that are new to report in past {days} day(s)')
    else:
        report += formatter.info(f'Only showing items that are new to report in past {days} day(s)')

    shown = set()
    for bug_flag in [True, False]:
        top_title = formatter.issue_heading(2, f'FOR ISSUES THAT ARE{"" if bug_flag else " NOT"} MARKED AS BUGS:')
        title_done = False
        now = utc_to_local(datetime.now())
        for issue in get_subset(issues, members, bug_flag, bug_label):
            if not issue.closed_at and not issue.last_team_response_at:
                diff = date_diff(now, issue.created_at).days
                star = diff <= days
                if star or show_all:
                    if not title_done:
                        report += top_title
                        top_title = ''
                        report += formatter.issue_heading(3, f'Issues in {repo} that need a response from team:')
                        title_done = True
                    shown.add(issue.number)
                    report += formatter.issue_line(star, repo_path, issue, op=diff)
        if title_done:
            report += formatter.end_section()
            title_done = False

        for issue in get_subset(issues, members, bug_flag, bug_label):
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
                        report += formatter.issue_heading(3, f'Issues in {repo} that have comments from OP after last team response:')
                        title_done = True
                    shown.add(issue.number)
                    report += formatter.issue_line(star, repo_path, issue, op=op_days, team=team_days)

        if title_done:
            report += formatter.end_section()
            title_done = False

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
                            report += formatter.issue_heading(3, f'Issues in {repo} that have comments from 3rd party after last team response:')
                            title_done = True
                        shown.add(issue.number)
                        report += formatter.issue_line(star, repo_path, issue, threep=other_days, team=team_days)

        if title_done:
            report += formatter.end_section()
            title_done = False

        for issue in get_subset(issues, members, bug_flag, bug_label):
            if issue.closed_at or issue.number in shown:
                continue
            elif issue.last_team_response_at and issue.last_response_at == issue.last_team_response_at:
                diff = date_diff(now, issue.last_response_at).days  # type: ignore
                if diff < stale:
                    continue
                star = diff < (stale + days)
                if star or show_all:
                    if not title_done:
                        report += top_title
                        top_title = ''
                        report += formatter.issue_heading(3, f'Issues in {repo} that have no external responses since team response in {stale}+ days:')
                        title_done = True
                    shown.add(issue.number)
                    report += formatter.issue_line(star, repo_path, issue, team=diff)

        if title_done:
            report += formatter.end_section()
            title_done = False

        if bug_flag:
            report += formatter.hline()

    return report


def find_pr_activity(now: datetime, owner: str, repo: str,
                     open_prs: list[PullRequest], closed_prs: list[PullRequest],
                     formatter: FormatterABC, days: int = 1, show_all: bool = False) -> str:
    repo_path = f'https://github.com/{owner}/{repo}'

    cutoff = now - timedelta(days=days)
    week_ago = now - timedelta(days=7)

    newly_opened = filter_prs_by_time(open_prs + closed_prs, created_after=cutoff)
    newly_merged = filter_prs_by_time(closed_prs, closed_after=cutoff, must_be_merged=True)
    newly_closed = [pr for pr in filter_prs_by_time(closed_prs, closed_after=cutoff, must_be_closed=True)
                    if pr.merged_at is None]
    stale_open = filter_prs_by_time(open_prs, created_before=week_ago, must_be_open=True) \
        if days >= 7 else []

    if not (newly_opened or newly_merged or newly_closed or stale_open):
        return ''

    report = formatter.issue_heading(2, 'PULL REQUEST ACTIVITY')

    if newly_opened:
        report += formatter.pr_heading(3, f'Pull Requests opened in the past {days} day(s):')
        for pr in sorted(newly_opened, key=lambda x: x.created_at, reverse=True):
            star = True
            report += formatter.pr_line(star, repo_path, pr, now=now)
        report += formatter.end_section()

    if newly_merged:
        report += formatter.pr_heading(3, f'Pull Requests merged in the past {days} day(s):')
        for pr in sorted(newly_merged, key=lambda x: x.merged_at or x.closed_at, reverse=True):
            star = True
            report += formatter.pr_line(star, repo_path, pr, pr.merged_at)
        report += formatter.end_section()

    if newly_closed:
        report += formatter.pr_heading(3, f'Pull Requests closed (not merged) in the past {days} day(s):')
        for pr in sorted(newly_closed, key=lambda x: x.closed_at, reverse=True):
            star = True
            report += formatter.pr_line(star, repo_path, pr, pr.closed_at)
        report += formatter.end_section()

    if stale_open:
        report += formatter.pr_heading(3, f'Pull Requests still open that were opened more than 7 days ago:')
        for pr in sorted(stale_open, key=lambda x: x.created_at):
            days_old = date_diff(now, pr.created_at).days
            star = days_old > 14
            report += formatter.pr_line(star, repo_path, pr, now=now)
        report += formatter.end_section()

    return report


def find_closed_issues(now: datetime, owner: str, repo: str,
                       closed_issues: list[Issue],
                       formatter: FormatterABC, days: int = 1) -> str:
    repo_path = f'https://github.com/{owner}/{repo}'

    cutoff = now - timedelta(days=days)

    recently_closed = []
    for issue in closed_issues:
        if issue.closed_at and issue.closed_at >= cutoff:
            recently_closed.append(issue)

    if recently_closed:
        report = formatter.issue_heading(2, 'RECENTLY CLOSED ISSUES')
        report += formatter.issue_heading(3, f'Issues closed in the past {days} day(s):')
        for issue in sorted(recently_closed, key=lambda x: x.closed_at or x.created_at, reverse=True):
            star = True
            days_open = date_diff(issue.closed_at, issue.created_at).days if issue.closed_at else 0
            report += formatter.issue_line(star, repo_path, issue, team=days_open)
        report += formatter.end_section()
    else:
        report = ''

    return report
