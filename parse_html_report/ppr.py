# Parse Performance Report tool.
# Run help (-h) for description.
# usage:
# ppr "C:\path\jobid_performance.html"

import re
import argparse
import os.path
from HTMLParser import HTMLParser


def init_options():
    arg_parser = argparse.ArgumentParser(
        description="Parse a BMO NG risk performance report file to "
                    "sum up compute times for tasks grouped by pricer.",
        conflict_handler='resolve',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    arg_parser.add_argument(
        "f",
        type=str,
        help="file - full path to the performance report html file OR " \
            "full path to a file list of performance report html files."
    )
    
    arg_parser.add_argument(
        "-d",
        help="debug - print debug trace.",
        action='store_true'
    )

    arg_parser.add_argument(
        "-s",
        help="seconds - print compute time in seconds.",
        action='store_true'
    )

    arg_parser.add_argument(
        "-tsc",
        type=int,
        default=0,
        help="tasks sorted by compute - print T tasks that took most grid compute."
    )

    arg_parser.add_argument(
        "-tsf",
        type=int,
        default=0,
        help="tasks sorted by finish - print T tasks that finished last."
    )

    arg_parser.add_argument(
        "-ttg",
        type=int,
        help="tasks of trade-group - print tasks that belong to the trade-group."
    )

    arg_parser.add_argument(
        "-gp",
        help="grouped by pricer - sum up task compute times grouped by" \
            " pricer and sort by grid compute time.",
        action='store_true',
        default=True
    )

    arg_parser.add_argument(
        "-gtg",
        type=int,
        default=0,
        help="grouped by trade group - sum up task compute times grouped by" \
            " trade group and show the G largest grid compute time ones."
    )

    arg_parser.add_argument(
        "-ftg",
        type=str,
        help="file trade groups - get trade groups from an alternate performance report file. " \
            "Sometimes trade groups are present only in RNIV_BASEPV runs."
    )

    arg_parser.add_argument(
        "-fc",
        type=str,
        help="file compare - compare to another performance report file. " \
            "View grid compute time improvement wrt another run of same job."
    )

    arg_parser.add_argument(
        "-fctg",
        type=str,
        help="file compare trade groups - trade groups alternate file for compare report file." 
    )
    
    return arg_parser.parse_args()

def get_absolute_path(rootfilepath, relativefilepath):
    up = 1;
    while relativefilepath[0:3] == '..\\':
        relativefilepath = relativefilepath[3:]
        up = up + 1

    while up > 0:
        rootfilepath = rootfilepath[0 : rootfilepath[0:-1].rfind('\\') + 1]
        up = up - 1

    return rootfilepath + relativefilepath

def get_filename_only(filepath):
    begin = filepath.rfind('\\') + 1
    end = filepath.rfind('.')
    return filepath[begin:end]


class duration_t(object):
    def __init__(self, days, hours, minutes, seconds):
        self.days = days
        self.hours = hours
        self.minutes = minutes
        self.seconds = seconds

    def make_readable(self):
        self.minutes += (self.seconds / 60)
        self.seconds %= 60
        self.hours += (self.minutes / 60)
        self.minutes %= 60
        self.days += (self.hours / 24)
        self.hours %= 24
        
    def __str__(self):
        self.make_readable()
        return '[{:>2}.{:0>2}:{:0>2}:{:0>2}]'.format(
                self.days,self.hours,self.minutes,self.seconds)

    def __add__(self, other):
        return duration_t(
            self.days + other.days,
            self.hours + other.hours,
            self.minutes + other.minutes,
            self.seconds + other.seconds
            )
    
    def to_seconds(self):
        return self.days*24*3600 + self.hours*3600 + self.minutes*60 + self.seconds


class task_t(object):
    def __init__(self, tradegroup_id, paths, status, compute_time):
        self.tradegroup_id = tradegroup_id
        self.paths = paths
        self.status = status
        self.compute_time = compute_time
        self.start = ''
        self.finish = ''


class trade_group_t(object):
    def __init__(self):
        self.id = None
        self.pricer = None
        self.num_positions = None
        self.cap_threads = None
        self.tasks = []


class parsed_results_t (object):
    def __init__(self):
        # this gets cleared across jobs
        self.tradegroups = {}
        
        # this stays across jobs
        self.pricers = {}

        self.mt_duration = duration_t(0,0,0,0)
        self.st_duration = duration_t(0,0,0,0)
        self.num_mt_tasks = 0
        self.num_st_tasks = 0


class pricer_result_t (object):
    def __init__(self, pricer, cap_threads):
        self.pricer = pricer
        self.cap_threads = cap_threads
        self.num_tradegroups = 0
        self.num_tasks = 0
        self.compute_time = duration_t(0,0,0,0)

    # to enable pricer results with same name but different cap_threads
    # to be added together
    def __add__(self, other):
        assert (self.pricer == other.pricer)
        
        pr_sum = pricer_result_t (self.pricer, 0)
        pr_sum.num_tradegroups = self.num_tradegroups + other.num_tradegroups
        pr_sum.num_tasks = self.num_tasks + other.num_tasks
        pr_sum.compute_time = self.compute_time + other.compute_time
        
        return pr_sum


class HTMLCallbackParser(HTMLParser):
    def __init__(self, subscriber):
        HTMLParser.__init__(self)
        self.subscriber = subscriber

    def handle_starttag(self, tag, attrs):
        self.subscriber.handle_starttag (tag, attrs)

    def handle_endtag(self, tag):
        self.subscriber.handle_endtag (tag)

    def handle_data(self, data):
        self.subscriber.handle_data (data)

    def handle_comment(self, comment):
        self.subscriber.handle_comment (comment)


#
# The html body is organised as an unordered-list <ul>
# where each item <li>
# contains a name marked by <a>Name ...</a>.
# followed by zero or more recursive unordered-lists.
# The current hierarchy is
# Job
#     <ul>
#         Job Details
#             <ul>
#             <ul>
#             <ul>
#             <ul>
#                TradeGroup
#     <ul>
#         Component [CnC]
#             <ul>
#                JobTask
#                Provisioning
#                ProcessResultsFile
#         Component [Grid]
#             <ul>
#                Task1
#                Task2
#                ...
#         Component [RWS]
#             <ul>
#                ProcessResultsFile
#                    <ul>
#                        file1
#                        file2
#
# We are interested in a few of those <li><a>name</a> with name hierarchy like
# Job -> Job Details -> TradeGroup
# Job -> Component [Grid]
#
# logic:
# When we see a Name we are interested in, we transition from CurrentState to
# new state called CurrentState->Name
# Then when we see the end tag </a> for that Name, we transition to
# new state called CurrentState->Name->
# It is in this state that we start processing actual data.
# This is because we want to skip similar looking data 
# a) outside the inner lists we are interested in
# b) in one case even inside the <a>Name...</a>
#
# We exit state CurrentState->Name-> back to CurrentState-> when we see the 
# end tag for the <li> enclosing <a>Name...</a> . 
# Detecting the matching </li> end tag for a state will require a li counter
# for every state.
# li counter of a newly entered state is assumed to be 0. 
# When we see a <li> we increment li counter of current state.
# When we see a </li> 
# 1. if the current state li counter is already 0 we 
#     a. exit the current state, goes to its outer state which makes it
#        the new current state
# 2. decrement the li counter of the current state.
#
class HTMLPerfReportParser(HTMLParser):
    def __init__(
            self, 
            num_tasks_to_print,     # exit after parsing specified tasks
            fn_print_task,          # function to be used to print the specified tasks
            in_seconds,             # show durations in seconds
            is_debug,               # print debug trace
            is_tradegroup_only,     # parse only html->body->job->jobdetails->tradegroup section
            alt_tradegroup_path,    # alternate perf report to use for trade groups 
                                    # if this report doesnt have tradegroup section
            results                 # out: results of parsing
        ):
        HTMLParser.__init__(self)
        self.num_tasks_to_parse = num_tasks_to_print
        self.fn_print_task = fn_print_task
        self.in_seconds = in_seconds
        self.is_debug = is_debug
        self.is_tradegroup_only = is_tradegroup_only
        self.alt_tradegroup_path = alt_tradegroup_path
        self.results = results

        self.state = 'html->'
        self.li_counters = {}
        self.last_task = None
        self.is_tgsection_present = False
        self.remaining_tasks_to_parse = self.num_tasks_to_parse
        self.jobid = '?'
        self.jobsummary = '?'
        self.task_signature = None
        self.omitted_signature = 'additional entries omitted'

        self.callback_parser = HTMLCallbackParser (self)
        self.num_tasks_omitted = 0

        # Job [4134826], Success,
        self.jobid_pattern = re.compile(
            r'Job\s\[(\d*)\],\s*([A-Za-z]+\s?[A-Za-z]*),'
        )

        # Duration = [00:00:03.159], Start = [00:13:54.897], End = [00:13:58.056], Computational = [2.11:34:03.159]
        self.computational_pattern = re.compile(
            r',\s*Start\s*=\s*\[((?:\d|:)*).(?:\d*)\]\s*'
            r',\s*End\s*=\s*\[((?:\d|:)*).(?:\d*)\]\s*'
            r',\s*Computational\s*=\s*\[(\d*).(\d*):(\d*):(\d*).(?:\d*)\]'
        )

        self.is_legacy_format = None
        self.tradegroup_pattern = None

        # 1#80012#TradeGroup#1089#2019-04-11 00:00:00#2019-05-23 19:07:16#8#100#8000#100#False#8
        # 1#80012#TradeGroup#109#2019-04-11 00:00:00#2019-05-23 19:07:16#100#100#8000#100#True#1
        # 0#0_FxPv01PositionSpecificData#TradeGroup#0#2019-06-12 00:00:00#2019-06-13 05:55:26#13#999#1000#1000#False#1
        self.tradegroup_new_pattern = re.compile(
            r'\d*#\d*_*\w*#TradeGroup#(\d*)#(?:\d|\-|\s|\:)*#(?:\d|\-|\s|\:)*#\d*#\d*#\d*#\d*#(?:True|False)#(\d*)'
        )

        # 1#80012#TradeGroup#1089#2019-04-11 00:00:00#2019-05-23 19:07:16#8#100#8000#100
        # 0#0_FxPv01PositionSpecificData#TradeGroup#0#2019-06-12 00:00:00#2019-06-13 05:55:26#13#999#1000#1000#False
        self.tradegroup_legacy_pattern = re.compile(
            r'\d*#\d*_*\w*#TradeGroup#(\d*)#(?:\d|\-|\s|\:)*#(?:\d|\-|\s|\:)*#\d*#\d*#\d*#\d*'
        )

        # No.Pos = 60 Pricing Credit.Cdx 
        self.pos_pricer_pattern = re.compile(
            # r'No\.Pos\s*=\s*(\d+)\s+Pricing\s+(^\s*)'
            r'No\.Pos\s*=\s*(\d+)\s+Pricing\s+(\S*)'
        )

        # 4900235#MFL1088#11:20, Success, 
        # 4900235#MFL1088#-1:-1, Success, 
        # 4134834#MFL22, Success,
        self.task_pattern_success = re.compile(
            r'\d*#MFL(\d*)#(-?\d*:-?\d*),\s*(Success),'
        )

        # 4900235#MFL1088#11:20, Success, 
        # 4900235#MFL1088#-1:-1, Success, 
        # 4127083#MFL204#20:29, Unhandled Exception,
        self.task_pattern = re.compile(
            r'\d*#MFL(\d*)#(-?\d*:-?\d*),\s*([A-Za-z]+\s?[A-Za-z]*),'
        )

        # 4134826#110e107a-6553-4362-b9d4-a09dd0b44913#0:0, Success,
        self.task_md_pattern_success = re.compile(
            r'\d*#(\w*-\w*-\w*-\w*-\w*)#(-?\d*:-?\d*),\s*(Success),'
        )
        
        # 4134826#110e107a-6553-4362-b9d4-a09dd0b44913#0:0, Unhandled Exception,
        self.task_md_pattern = re.compile(
            r'\d*#(\w*-\w*-\w*-\w*-\w*)#(-?\d*:-?\d*),\s*([A-Za-z]+\s?[A-Za-z]*),'
        )
        
        # 4134834#MFL22, Success,
        self.task_nopath_pattern_success = re.compile(
            r'\d*#MFL(\d*),\s*(Success),'
        )

        # 4134834#MFL22, Unhandled Exception,
        self.task_nopath_pattern = re.compile(
            r'\d*#MFL(\d*),\s*([A-Za-z]+\s?[A-Za-z]*),'
        )

        # 4006 additional entries omitted.
        self.omitted_pattern = re.compile(
            r'(\d+)\s+additional entries omitted'
        )

    #
    # call before parsing another performance report with the same instance of
    # this Parser class
    #
    def next(self):
        self.set_state ('html->')
        self.li_counters = {}
        self.last_task = None
        self.is_tgsection_present = False
        self.remaining_tasks_to_parse = self.num_tasks_to_parse
        self.task_signature = None     

    def set_state(self, state):
        if state is not self.state:
            self.state = state

            if self.is_debug:
                print self.state

    def parse_jobid (self, data):
        jobmatch = self.jobid_pattern.search(data)
        if jobmatch:
            # print jobmatch.group(1)
            return jobmatch.group(1)
        else:
            raise Exception("parse error: jobid  " + data)

    def parse_tradegroup (self, data, trade_group):
        if self.tradegroup_pattern == None:
            self.tradegroup_pattern = (
                self.tradegroup_new_pattern
                if self.tradegroup_new_pattern.search(data)
                else self.tradegroup_legacy_pattern
            )
            
            self.is_legacy_format = (
                self.tradegroup_pattern == self.tradegroup_legacy_pattern
            )
            
        tradegroup = self.tradegroup_pattern.search(data)
        if tradegroup:
            # print tradegroup.group(1)
            trade_group.id = tradegroup.group(1)
            trade_group.cap_threads = (
                1 if self.is_legacy_format else (int (tradegroup.group(2)))
            )
        else:
            raise Exception("parse error: TradeGroup " + data)

    def parse_regular_task (self, data):
        # first try to match a task success pattern
        task_match = self.task_pattern_success.search(data)
        
        # next try to match a task pattern of any failed status 
        if not task_match:
            task_match = self.task_pattern.search(data)
            if task_match:
                print "WARN: failed task ", data

        if task_match:
            # print task_match.group(1)
            return task_t(
                task_match.group(1), 
                task_match.group(2), 
                task_match.group(3),
                None
            )
        else:
            return None

    def parse_md_task (self, data):
        # first try to match a task success pattern
        task_match = self.task_md_pattern_success.search(data)
        
        # next try to match a task pattern of any failed status 
        if not task_match:
            task_match = self.task_md_pattern.search(data)
            if task_match:
                print "WARN: failed task ", data

        if task_match:
            # print task_match.group(1)
            return task_t(
                task_match.group(1), 
                task_match.group(2), 
                task_match.group(3),
                None
            )
        else:
            return None
        
    def parse_nopath_task (self, data):
        # first try to match a task success pattern
        task_match = self.task_nopath_pattern_success.search(data)
        
        # next try to match a task pattern of any failed status 
        if not task_match:
            task_match = self.task_nopath_pattern.search(data)
            if task_match:
                print "WARN: failed task ", data

        if task_match:
            # print task_match.group(1)
            return task_t(
                task_match.group(1), 
                "", 
                task_match.group(2),
                None
            )
        else:
            return None
        
    def parse_task (self, data):
        task = None
        
        # first try to match a regular task 
        if task is None:
            task = self.parse_regular_task (data)
        
        # if that failed, try to match a MD task
        if task is None:
            task = self.parse_md_task (data)
        
        # if that failed, try to match a no path task
        if task is None:
            task = self.parse_nopath_task (data)

        # if that also failed, throw exception
        if task is None:
            raise Exception("parse error: task " + data)
        else:
            return task

    def parse_pos_pricer (self, data, trade_group):
        pospricer = self.pos_pricer_pattern.search(data)
        if pospricer:
            # print pospricer.group(0)
            trade_group.num_positions = pospricer.group(1)
            trade_group.pricer = pospricer.group(2)
        else:
            raise Exception("parse error: positions and pricer")
        
    def handle_starttag(self, tag, attrs):
        #print "Encountered start tag:", tag
        if tag == 'body':
            if self.state == 'html->':
                self.set_state ('html->body->')
            else:
                raise Exception("state transition logic error")
        elif tag == 'li':
            if self.state in self.li_counters:
                self.li_counters[self.state] += 1
            else:
                self.li_counters[self.state] = 1

    def handle_endtag(self, tag):
        #print "Encountered end tag :", tag
        if tag == 'body':
            if self.state == 'html->body->':
                self.set_state ('html->')
            else:
                raise Exception("state transition logic error")
        elif tag == 'a':
            if self.state == 'html->body->job':
                self.set_state ('html->body->job->')
            elif self.state == 'html->body->job->jobdetails':
                self.set_state ('html->body->job->jobdetails->')
            elif self.state == 'html->body->job->jobdetails->tradegroup':
                self.set_state ('html->body->job->jobdetails->tradegroup->')
                self.is_tgsection_present = True
            elif self.state == 'html->body->job->grid':
                self.set_state ('html->body->job->grid->')

                # state transition special case 
                if self.is_tradegroup_only:
                    # no further parsing of this html is needed anymore
                    self.set_state ('html->body->')
                    self.result = None

                if not self.is_tgsection_present:
                    if self.alt_tradegroup_path is not None:
                        print "parsing for trade groups: {}".format (
                            get_filename_only (self.alt_tradegroup_path)
                        )
                        
                        with open(self.alt_tradegroup_path, 'r') as perfreport_file:
                            perfreport_html = perfreport_file.read().replace('\n', '')
                        
                            perfreport_parser = (
                                HTMLPerfReportParser (
                                    0, 
                                    None,
                                    self.in_seconds, 
                                    self.is_debug, 
                                    True, 
                                    None,  # third alternative can go here
                                    self.results
                                )
                            )
                            
                            perfreport_parser.feed(perfreport_html)
                    else:
                        print "WARN: Performance report does not have section " + \
                            "html->body->job->jobdetails->tradegroup"

        elif tag == 'li':
            if self.state not in self.li_counters:
                self.li_counters[self.state] = 0
                
            if self.state == 'html->body->job->':
                if self.li_counters[self.state] == 0:
                    self.set_state ('html->body->')
                self.li_counters[self.state] -= 1
            elif self.state == 'html->body->job->jobdetails->':
                if self.li_counters[self.state] == 0:
                    self.set_state ('html->body->job->')
                self.li_counters[self.state] -= 1
            elif self.state == 'html->body->job->jobdetails->tradegroup->':
                if self.li_counters[self.state] == 0:
                    self.set_state ('html->body->job->jobdetails->')
                self.li_counters[self.state] -= 1
            elif self.state == 'html->body->job->grid->':
                if self.li_counters[self.state] == 0:
                    self.set_state ('html->body->job->')
                self.li_counters[self.state] -= 1
                
            assert self.li_counters[self.state] >= 0

    def handle_data(self, data):
        #print "Encountered data  :", data
        if self.state == 'html->body->':
            if 'Job [' in data:
                self.set_state ('html->body->job')
                self.jobid = self.parse_jobid (data)
                self.task_signature = str(self.jobid) + "#"
        elif self.state == 'html->body->job':
            if 'Computational = [' in data:
                self.jobsummary = data
                print '---------- jobid:{} {} ----------'.format(
                    self.jobid, self.jobsummary
                )
        elif self.state == 'html->body->job->':
            if 'Job Details' == data:
                self.set_state ('html->body->job->jobdetails')
            elif 'Component [Grid],' == data:
                self.set_state ('html->body->job->grid')
        elif self.state == 'html->body->job->jobdetails->':
            if 'TradeGroup' == data:
                self.set_state ('html->body->job->jobdetails->tradegroup')
        elif self.state == 'html->body->job->jobdetails->tradegroup->':
            if '#TradeGroup#' in data:
                # print data
                tradegroup = trade_group_t()
                self.parse_tradegroup (data, tradegroup)
                self.parse_pos_pricer (data, tradegroup)
                self.results.tradegroups[tradegroup.id] = tradegroup
        elif self.state == 'html->body->job->grid->':
            
            if self.task_signature is None:
                raise Exception("Job id not found !")
            
            if self.task_signature in data:
                # print data
                # sanity check
                if self.last_task is not None:
                    raise Exception("report error: computational_duration not found for previous task")
                
                self.last_task = self.parse_task(data)
                
                if self.last_task.tradegroup_id not in self.results.tradegroups:
                    if self.is_tgsection_present:
                        raise Exception("report error: task's trade group not in Job Details")
                    else:
                        tradegroup = trade_group_t()
                        tradegroup.id = self.last_task.tradegroup_id
                        tradegroup.cap_threads = 0
                        tradegroup.num_positions = 0
                        tradegroup.pricer = 'Unknown Pricer'
                        self.results.tradegroups[tradegroup.id] = tradegroup

            elif 'Computational = [' in data:
                # print data
                computational_duration = self.computational_pattern.search(data)
                if computational_duration:
                    # print computational_duration.group(0)
                    start = computational_duration.group(1)
                    finish = computational_duration.group(2)
                    days = int (computational_duration.group(3))
                    hours = int (computational_duration.group(4))
                    minutes = int (computational_duration.group(5))
                    seconds = int (computational_duration.group(6))

                    if self.last_task is not None:
                        self.last_task.compute_time = duration_t(
                            days, hours, minutes, seconds
                        )
                        self.last_task.start = start
                        self.last_task.finish = finish
                        
                        tradegroup = self.results.tradegroups[
                            self.last_task.tradegroup_id
                        ]
                        tradegroup.tasks.append(self.last_task)
                        
                        if self.remaining_tasks_to_parse > 0:
                            self.fn_print_task (
                                self.last_task, 
                                tradegroup, 
                                self.in_seconds
                            )
                                
                            self.remaining_tasks_to_parse -= 1
                            
                            if self.remaining_tasks_to_parse == 0:
                                exit(0)
                                
                        self.last_task = None
                    else:
                        raise Exception("report error: task not found before this computational_duration: " + data)
                else:
                    raise Exception("parse error: computational_duration " + data)
                
            elif self.omitted_signature in data:
                # since <li>n additional entries omitted.</li> does not
                # follow the convention of other <li> containing <a>
                # 'html->body->job->grid->omitted' cannot be made yet another
                # self.state
                omitted_match = self.omitted_pattern.search(data)
                if omitted_match:
                    self.num_tasks_omitted = int (omitted_match.group (1))
                    print 'parsing', self.num_tasks_omitted, 'omitted tasks...'
                else:
                    print 'WARN: cannot parse omitted tasks pattern: ', data

    #
    # Tasks after a certain limit are commented out in performance report.
    # However we still need to parse those.
    #
    def handle_comment(self, comment):
        #print "Encountered comment  :", comment
        if self.state == 'html->body->job->grid->':
            if self.num_tasks_omitted > 0:
                # parse commented out grid entries
                # self.feed (comment) doesnt work. feed() doesnt seem to be recursive call capable.
                self.callback_parser.feed (comment)
                
                self.num_tasks_omitted -= 1
            else:
                print 'WARN: more omitted tasks than reported: ', comment
                pass

def get_perfreport_paths_in (filepath):
    perfreport_paths = []
    
    with open(filepath) as f:
        lines = f.readlines()
        
        for line in lines:
            # remove whitespace characters like `\n` at the end of each line
            # also remove any quotes surrounding file path
            perfreport_path = line.strip().strip('"')
    
            # sanity check performance report paths
            
            if not perfreport_path.endswith('html'):
                print "the specified performance report file does not have " \
                    "html extension: " , perfreport_path
                continue
            
            if not os.path.isfile(perfreport_path):
                print "the specified performance report file does not " \
                    "exist: " ,perfreport_path
                continue
                
            perfreport_paths.append (perfreport_path)
        
    return perfreport_paths

def parse_perfreport (
        projpath, 
        print_num_tasks, 
        in_seconds, 
        is_debug, 
        alt_tradegroup_path, 
        results
):

    print "parsing performance report: {}".format (get_filename_only (projpath))
    
    with open(projpath, 'r') as perfreport_file:
        perfreport_html = perfreport_file.read().replace('\n', '')
    
        perfreport_parser = (
            HTMLPerfReportParser (
                print_num_tasks, 
                print_task,
                in_seconds, 
                is_debug, 
                False, 
                alt_tradegroup_path, 
                results
            )
        )
        
        perfreport_parser.feed(perfreport_html)

def print_task (task, tradegroup, in_seconds):
    if in_seconds:
        print "{:<40}  {:>2} grid {:>7,}    group {:<4}  positions {:<4}  paths {:^7}  {:<7}  [ {} - {} ]".format (
            tradegroup.pricer,
            ("MT" if tradegroup.cap_threads > 1 else "ST"),
            task.compute_time.to_seconds(),
            tradegroup.id,
            tradegroup.num_positions,
            task.paths,
            task.status,
            task.start,
            task.finish
        )
    else:
        print "{:<40}  {:>2} grid {}    group {:<4}  positions {:<4}  paths {:^7}  {:<7}  [ {} - {} ]".format (
            tradegroup.pricer,
            ("MT" if tradegroup.cap_threads > 1 else "ST"),
            task.compute_time,
            tradegroup.id,
            tradegroup.num_positions,
            task.paths,
            task.status,
            task.start,
            task.finish
        )

def print_tradegroup (tradegroup, perfreport_path, in_seconds):
    # sort by grid compute time
    sorted_tasks = sorted (
        tradegroup.tasks,
        key=lambda task: task.compute_time.to_seconds(),
        reverse=True
    )

    print
    for task in sorted_tasks:
        print_task (task, tradegroup, in_seconds)

def process_tradegroup_results (
        results, 
        perfreport_path, 
        print_tradegroup_id, 
        in_seconds
):
    for tradegroup in results.tradegroups.values():
        # Some jobs are ST irrespective of pricer. 
        # That can create two entries for a pricer when aggregating reports.
        key = tradegroup.pricer + '_' + str(tradegroup.cap_threads)
        if key not in results.pricers:
            results.pricers[key] = (
                pricer_result_t (tradegroup.pricer, tradegroup.cap_threads)
            )
            
        results.pricers[key].num_tradegroups += 1
        
        for task in tradegroup.tasks:
            results.pricers[key].num_tasks += 1
            
            results.pricers[key].compute_time += task.compute_time
            
            if tradegroup.cap_threads > 1:
                results.num_mt_tasks += 1
                results.mt_duration += task.compute_time
            else:
                results.num_st_tasks += 1
                results.st_duration += task.compute_time

        if int(tradegroup.id) == print_tradegroup_id:
            print_tradegroup (tradegroup, perfreport_path, in_seconds)

def process_input_file (
        filepath, 
        print_num_tasks, 
        in_seconds, 
        is_debug, 
        alt_tradegroup_path,
        print_tradegroup_id
):
    filepath = str(filepath)
    filepath = filepath.replace('/', '\\')
    if not os.path.isfile(filepath):
        print "the specified input file does not exist: " , filepath
        exit(0)
        
    if alt_tradegroup_path is not None:
        alt_tradegroup_path = str(alt_tradegroup_path)
        alt_tradegroup_path = alt_tradegroup_path.replace('/', '\\')
        if not os.path.isfile(alt_tradegroup_path):
            print (
                "the specified alternate file for trade groups does not exist: "
                "{}".format(alt_tradegroup_path)
            )
            alt_tradegroup_path = None
    
    perfreport_paths = []
    
    if filepath.endswith('html'):
        perfreport_paths.append(filepath)
    else:
        perfreport_paths = get_perfreport_paths_in (filepath)
        
    results = parsed_results_t();
    
    for perfreport_path in perfreport_paths:
        parse_perfreport (
            perfreport_path, 
            print_num_tasks, 
            in_seconds, 
            is_debug, 
            alt_tradegroup_path,
            results
        )
        
        process_tradegroup_results (
            results, 
            perfreport_path, 
            print_tradegroup_id, 
            in_seconds
        )
        
        # clear only tradegroup results but not pricer results
        results.tradegroups.clear()
        
    return results

def print_results (input_file, results, in_seconds):
    # print tasks, groups and grid compute time by pricer
    
    sorted_results = sorted (
        results.pricers.items(),
        key=lambda item: item[1].compute_time.to_seconds(),
        reverse=True
    )
    
    max_pricer_name_len = 0
    for item in sorted_results:
        length = len(item[1].pricer)
        if length > max_pricer_name_len:
            max_pricer_name_len = length
    
    format_string = \
        "{{:<{}}}  {{:>2}} grid {{}}   groups {{:<4}}  tasks {{:<4}}". \
        format (max_pricer_name_len + 4)
    
    print
    for item in sorted_results:
        print format_string.format (
            item[1].pricer,
            ("MT" if item[1].cap_threads > 1 else "ST"),
            '{:>10,}'.format(item[1].compute_time.to_seconds()) if in_seconds
                else item[1].compute_time,
            item[1].num_tradegroups,
            item[1].num_tasks
        )
    
    # print total tasks and total grid compute time summary
    
    input_file_name = get_filename_only(input_file)

    print(
        "\nSummary: {} ".format(
            input_file_name
        )
    )

    print "Number of tasks ST:MT is  {} : {}".format (
        results.num_st_tasks,
        results.num_mt_tasks
    )

    if in_seconds:
        print "Compute time ST:MT is    {:>10,} : {:<10,}".format (
            results.st_duration.to_seconds(),
            results.mt_duration.to_seconds()
        )
    else:
        print "Compute time ST:MT is    {} : {}".format (
            results.st_duration,
            results.mt_duration
        )

#
# Compare compute time in results to results_prev.
# Print improvement as percentage compute time is reduced in results
#
def print_results_compare (input_file, results, input_file_prev, results_prev):
    # print compute time reduction by pricer
    print(
        "\nGrid Compute time reduction for {} compared to {}".format(
            get_filename_only (input_file),
            get_filename_only (input_file_prev)
        )
    )
    
    # since we might be comparing an MT run against an ST run
    # we cannot use the key of results.pricers which has _T appended, 
    # where T is cap threads.
    
    pricers = {}
    for value in results.pricers.values():
        if value.pricer in pricers:
            pricers[value.pricer] += value
        else:
            pricers[value.pricer] = value
    
    pricers_prev = {}
    for value in results_prev.pricers.values():
        if value.pricer in pricers_prev:
            pricers_prev[value.pricer] += value
        else:
            pricers_prev[value.pricer] = value
    
    sorted_results = sorted (
        pricers_prev.items(),
        key=lambda item: item[1].compute_time.to_seconds(),
        reverse=True
    )
    
    max_pricer_name_len = 0
    for item in sorted_results:
        length = len(item[1].pricer)
        if length > max_pricer_name_len:
            max_pricer_name_len = length
    
    format_string = \
        "{{:<{}}}  grid {{}} compared to {{}}   reduction {{:>3}}% {{}}". \
        format (max_pricer_name_len + 4)
    
    print
    for item in sorted_results:
        current = pricers[item[0]].compute_time
        previous = item[1].compute_time
        cur = current.to_seconds()
        prev = previous.to_seconds()
        
        comparable = (
            item[1].num_tradegroups == pricers[item[0]].num_tradegroups
            and
            item[1].num_tasks == pricers[item[0]].num_tasks
        )
        
        reduction = int (round ((prev - cur) * 100.0 / prev))
        
        print format_string.format (
            item[1].pricer,
            current,
            previous,
            reduction,
            "" if comparable else "ERROR: tasks in perf reports don't match."
        )
    
    # print total compute time reduction
    
    current = results.st_duration + results.mt_duration
    previous = results_prev.st_duration + results_prev.mt_duration
    cur = current.to_seconds()
    prev = previous.to_seconds()
    
    comparable = (
        (results.num_st_tasks + results.num_mt_tasks)
        ==
        (results_prev.num_st_tasks + results_prev.num_mt_tasks)
    )
    
    reduction = int (round ((prev - cur) * 100.0 / prev))
    
    print "-------------------------------------------------------------------"
    print format_string.format (
        "TOTAL: ",
        current,
        previous,
        reduction,
        "" if comparable else "ERROR: tasks in perf reports don't match."
    )
  

if __name__ == "__main__":

    args = init_options()

    results = process_input_file (args.f, args.tsc, args.s, args.d, args.ftg, args.ttg)
    
    if args.fc is not None:
        results_prev = process_input_file (args.fc, args.tsc, args.s, args.d, args.fctg, args.ttg)
        
        print_results_compare (args.f, results, args.fc, results_prev)
    else:
        print_results (args.f, results, args.s)
