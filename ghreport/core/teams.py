"""Team member detection for ghreport."""

import logging

from github import Github
from github.GithubException import GithubException


logger = logging.getLogger(__name__)


def get_members(owner: str, repo: str, token: str) -> set[str]:
    """
    Get the team members for a repo that have push or admin rights. This is not
    public, so if you are not in such a team (likely with admin rights)
    this will fail. I haven't found a good way to use the GraphQL API
    for this, so this still uses the REST API.
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
            except GithubException as exc:
                logger.debug(
                    "Skipping members for one team in %s/%s (%s)",
                    owner,
                    repo,
                    exc,
                )
    except GithubException as exc:
        if exc.status == 403:
            logger.info(
                "No permission to list teams for repo %s/%s (403). "
                "Continuing without GitHub team members.",
                owner,
                repo,
            )
        else:
            logger.warning(
                "Couldn't get teams for repo %s/%s: %s",
                owner,
                repo,
                exc,
            )
    return rtn


def get_team_members(
    org: str,
    repo: str,
    token: str,
    extra_members: str | None,
    verbose: bool,
) -> set[str]:
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
