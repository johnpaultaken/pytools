# pytools

# 1. parse_html_report
# a. peds
Performance Daily Summary. 
Parses the performance reports of all jobs from a nightly batch and draws a summary graph.
See samples of such graph in parse_html_report/sample_output/. 
Dotted line ... represents a wait in some queue, depressed line ___ represents input data provisioning, double line === represents computation on the grid, single line --- represents result writing to database.
# b. ppr
Parse Performance Report.
Parses the performance report of a single job and allows viewing of data from different viewpoints, like the most expensive tasks, the most expensive pricers, the most expensive trade groups etc. This allows quick identification of problems in an environment where data changes on a daily basis.
# 2. visual_studio
# a. repo_ops
Tools for cleaning up unused files in large visual studio repositories with many solutions and projects.
# b. ref_ops
Tools for updating assembly or dll references in all visual studio projects referenced by a visual studio solution.
