"""Team member detection for ghreport."""

from github import Github


def get_members(owner: str, repo: str, token: str) -> set[str]:
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


def get_team_members(org: str, repo: str, token: str, extra_members: str | None, verbose: bool) -> set[str]:
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
