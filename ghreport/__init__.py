"""
ghreport.

Usage:
  ghreport <repo> <token>
  ghreport -h | --help
  ghreport --version

Options:
  --verbose     Print examples of full stacks.
  -h --help     Show this screen.
  --version     Show version.
"""

__version__ = '0.1'

from docopt import docopt
from .ghreport import report


def main():
    arguments = docopt(__doc__, version=__version__)
    repo = arguments['repo']
    token = arguments['token']
    report(repo, token)
    



