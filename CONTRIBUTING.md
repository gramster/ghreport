## Releasing

To make a release,

  1) Update release date/version in README.md and setup.py
  2) Run 'python setup.py sdist'
  3) Test the generated source distribution in dist/
  4) Upload to PyPI: 'python -m twine upload --repository pypi dist/*'
  5) Increase version in setup.py (for next release)

