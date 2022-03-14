# ipython-kusto - Run Microsoft Kusto queries in IPython notebooks

This extension borrows extensively from Catherine Devlin's ipython-sql extension.
https://github.com/catherinedevlin/ipython-sql

It provides two magics:

- %kqlset - a line magic to set the default cluster and database
- %kql/%%kql - a line or cell magic to execute Kusto Query Language queries and return the results as a Pandas dataframe. The dataframe will be assigned to a variable 'kqlresult' (can be overridden with --set argument)

If you run either of these followed by a '?' you will get additional help.

When running a query, you may be redirected to a browser page to sign in if a token is needed.

See the example notebook in the examples/ directory for more details, or view it here with Binder:

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/gramster/ipython-kusto/master?filepath=examples%2FStorms.ipynb)

0.0.9 

Added missing dependencies to setup.py

0.0.8

Fix issue with parsing queries containing {}

0.0.7

Fix sample notebook issue.
Remove redundant dependencies.

0.0.6

Removed the NEWS.md file; it wasn't being bundled and caused install to not work. This is
a quick fix.

0.0.5

Added a flag to inhibit variable substitution in case that is problematic 
in some query.

0.0.4

Better error reporting. Use --error to get the old raw error.

0.0.3

Updated URL to point to Github repo.

0.0.2

A typo crept in to 0.0.1 release; that has been fixed.
Added a --quiet option to not display the dataframe.

0.01.
Initial release

