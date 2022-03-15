# ghreport - Generate useful reports from GitHub repository issues

This utility generates reports that can be useful to identify issues in
your repository that may be stale, or that may need a response.

It can also generate a chart of open bug counts over time.

See CONTRIBUTING.md for build instructions, or install from PyPI.

Use `ghreport -h` for help.

A sample report is shown below:


> In lists below, * marks items that are new to report in past day
> 
> FOR ISSUES THAT ARE MARKED AS BUGS:
> 
> 
> Issues in debugpy that need a response from team:
>   https://github.com/microsoft/debugpy/issues/731 : needs an initial team response (172 days old)
> 
> Issues in debugpy that have newer comments from 3rd party 3 days or more after last team response:
>   https://github.com/microsoft/debugpy/issues/102 : 3rd party responded 153 days ago but team last responded 693 days ago
>   https://github.com/microsoft/debugpy/issues/524 : 3rd party responded 7 days ago but team last responded 157 days ago
> 
> Issues in debugpy that have no external responses since team response in 30+ days:
>   https://github.com/microsoft/debugpy/issues/171 : team response was last response and no others in 679 days
>   https://github.com/microsoft/debugpy/issues/286 : team response was last response and no others in 597 days
>   https://github.com/microsoft/debugpy/issues/431 : team response was last response and no others in 348 days
>   https://github.com/microsoft/debugpy/issues/447 : team response was last response and no others in 504 days
>   https://github.com/microsoft/debugpy/issues/705 : team response was last response and no others in 201 days
>   https://github.com/microsoft/debugpy/issues/745 : team response was last response and no others in 152 days
>   https://github.com/microsoft/debugpy/issues/781 : team response was last response and no others in 104 days
> 
> =================================================================
> 
> FOR ISSUES THAT ARE NOT MARKED AS BUGS:
> 
> 
> Issues in debugpy that need a response from team:
>   https://github.com/microsoft/debugpy/issues/101 : needs an initial team response (710 days old)
>   https://github.com/microsoft/debugpy/issues/207 : needs an initial team response (1026 days old)
>   https://github.com/microsoft/debugpy/issues/215 : needs an initial team response (1223 days old)
>   https://github.com/microsoft/debugpy/issues/297 : needs an initial team response (640 days old)
>   https://github.com/microsoft/debugpy/issues/504 : needs an initial team response (450 days old)
>   https://github.com/microsoft/debugpy/issues/510 : needs an initial team response (446 days old)
>   https://github.com/microsoft/debugpy/issues/564 : needs an initial team response (362 days old)
>   https://github.com/microsoft/debugpy/issues/654 : needs an initial team response (255 days old)
>   https://github.com/microsoft/debugpy/issues/723 : needs an initial team response (181 days old)
>   https://github.com/microsoft/debugpy/issues/772 : needs an initial team response (138 days old)
>   https://github.com/microsoft/debugpy/issues/774 : needs an initial team response (134 days old)
>   https://github.com/microsoft/debugpy/issues/864 : needs an initial team response (10 days old)
>   https://github.com/microsoft/debugpy/issues/865 : needs an initial team response (5 days old)
>   https://github.com/microsoft/debugpy/issues/869 : needs an initial team response (3 days old)
> 
> Issues in debugpy that have new comments from OP:
>   https://github.com/microsoft/debugpy/issues/480 : OP responded 475 days ago but team last responded 475 days ago
>   https://github.com/microsoft/debugpy/issues/561 : OP responded 367 days ago but team last responded 367 days ago
>   https://github.com/microsoft/debugpy/issues/581 : OP responded 283 days ago but team last responded 327 days ago
>   https://github.com/microsoft/debugpy/issues/623 : OP responded 283 days ago but team last responded 284 days ago
>   https://github.com/microsoft/debugpy/issues/743 : OP responded 90 days ago but team last responded 159 days ago
>   https://github.com/microsoft/debugpy/issues/750 : OP responded 154 days ago but team last responded 154 days ago
>   https://github.com/microsoft/debugpy/issues/764 : OP responded 16 days ago but team last responded 67 days ago
>   https://github.com/microsoft/debugpy/issues/783 : OP responded 97 days ago but team last responded 98 days ago
>   https://github.com/microsoft/debugpy/issues/814 : OP responded 66 days ago but team last responded 67 days ago
>   https://github.com/microsoft/debugpy/issues/818 : OP responded 83 days ago but team last responded 84 days ago
>   https://github.com/microsoft/debugpy/issues/832 : OP responded 14 days ago but team last responded 26 days ago
> * https://github.com/microsoft/debugpy/issues/870 : OP responded 0 days ago but team last responded 0 days ago
> 
> Issues in debugpy that have newer comments from 3rd party 3 days or more after last team response:
>   https://github.com/microsoft/debugpy/issues/214 : 3rd party responded 271 days ago but team last responded 817 days ago
>   https://github.com/microsoft/debugpy/issues/216 : 3rd party responded 50 days ago but team last responded 677 days ago
>   https://github.com/microsoft/debugpy/issues/532 : 3rd party responded 382 days ago but team last responded 398 days ago
>   https://github.com/microsoft/debugpy/issues/581 : 3rd party responded 283 days ago but team last responded 327 days ago
>   https://github.com/microsoft/debugpy/issues/743 : 3rd party responded 90 days ago but team last responded 159 days ago
>   https://github.com/microsoft/debugpy/issues/764 : 3rd party responded 16 days ago but team last responded 67 days
>  ago
>   https://github.com/microsoft/debugpy/issues/801 : 3rd party responded 19 days ago but team last responded 28 days ago
>   https://github.com/microsoft/debugpy/issues/814 : 3rd party responded 3 days ago but team last responded 67 days ago
>   https://github.com/microsoft/debugpy/issues/832 : 3rd party responded 14 days ago but team last responded 26 days ago
>   https://github.com/microsoft/debugpy/issues/861 : 3rd party responded 0 days ago but team last responded 6 days ago
> 
> Issues in debugpy that have no external responses since team response in 30+ days:
>   https://github.com/microsoft/debugpy/issues/17 : team response was last response and no others in 774 days
>   https://github.com/microsoft/debugpy/issues/82 : team response was last response and no others in 664 days
>   https://github.com/microsoft/debugpy/issues/114 : team response was last response and no others in 697 days
>   https://github.com/microsoft/debugpy/issues/141 : team response was last response and no others in 689 days
>   https://github.com/microsoft/debugpy/issues/161 : team response was last response and no others in 823 days
>   https://github.com/microsoft/debugpy/issues/175 : team response was last response and no others in 881 days
>   https://github.com/microsoft/debugpy/issues/179 : team response was last response and no others in 945 days
>   https://github.com/microsoft/debugpy/issues/246 : team response was last response and no others in 131 days
>   https://github.com/microsoft/debugpy/issues/317 : team response was last response and no others in 624 days
>   https://github.com/microsoft/debugpy/issues/460 : team response was last response and no others in 494 days
>   https://github.com/microsoft/debugpy/issues/549 : team response was last response and no others in 382 days
>   https://github.com/microsoft/debugpy/issues/562 : team response was last response and no others in 355 days
>   https://github.com/microsoft/debugpy/issues/577 : team response was last response and no others in 223 days
>   https://github.com/microsoft/debugpy/issues/686 : team response was last response and no others in 146 days
>   https://github.com/microsoft/debugpy/issues/709 : team response was last response and no others in 195 days
>   https://github.com/microsoft/debugpy/issues/769 : team response was last response and no others in 138 days
>   https://github.com/microsoft/debugpy/issues/776 : team response was last response and no others in 57 days
>   https://github.com/microsoft/debugpy/issues/807 : team response was last response and no others in 67 days
> 

## Version History

0.1
 Initial release
 
