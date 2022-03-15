# ghreport - Generate useful reports from GitHub repository issues

This utility generates reports that can be useful to identify issues in
your repository that may be stale, or that may need a response.

It can also generate a chart of open bug counts over time.

See CONTRIBUTING.md for build instructions, or install from PyPI.

Use `ghreport -h` for help.

An abridged sample report is shown below:


>In lists below, * marks items that are new to report in past day
>
>FOR ISSUES THAT ARE NOT MARKED AS BUGS:
>
>Issues in debugpy that need a response from team:
>
>  https://github.com/microsoft/debugpy/issues/774 : needs an initial team response (134 days old)
>  
>  https://github.com/microsoft/debugpy/issues/864 : needs an initial team response (10 days old)
>  
>  https://github.com/microsoft/debugpy/issues/865 : needs an initial team response (5 days old)
>  
>  https://github.com/microsoft/debugpy/issues/869 : needs an initial team response (3 days old)
>  
>
>Issues in debugpy that have new comments from OP:
>
>
>  https://github.com/microsoft/debugpy/issues/814 : OP responded 66 days ago but team last responded 67 days ago
>  
>  https://github.com/microsoft/debugpy/issues/818 : OP responded 83 days ago but team last responded 84 days ago
>  
>  https://github.com/microsoft/debugpy/issues/832 : OP responded 14 days ago but team last responded 26 days ago
>  
>* https://github.com/microsoft/debugpy/issues/870 : OP responded 0 days ago but team last responded 0 days ago
>
>
>Issues in debugpy that have newer comments from 3rd party 3 days or more after last team response:
>
>  https://github.com/microsoft/debugpy/issues/801 : 3rd party responded 19 days ago but team last responded 28 days ago
>  
>  https://github.com/microsoft/debugpy/issues/814 : 3rd party responded 3 days ago but team last responded 67 days ago
>  
>  https://github.com/microsoft/debugpy/issues/832 : 3rd party responded 14 days ago but team last responded 26 days ago
>  
>  https://github.com/microsoft/debugpy/issues/861 : 3rd party responded 0 days ago but team last responded 6 days ago
>
>
>Issues in debugpy that have no external responses since team response in 30+ days:
>
>
>  https://github.com/microsoft/debugpy/issues/709 : team response was last response and no others in 195 days
>  
>  https://github.com/microsoft/debugpy/issues/769 : team response was last response and no others in 138 days
>  
>  https://github.com/microsoft/debugpy/issues/776 : team response was last response and no others in 57 days
>  
>  https://github.com/microsoft/debugpy/issues/807 : team response was last response and no others in 67 days
>  
>

## Version History

0.1
 Initial release
 
