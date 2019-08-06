# usage:
# ppr "C:\path\jobid_performance.html"

import re
import argparse
import os.path
from HTMLParser import HTMLParser


def init_options():
    arg_parser = argparse.ArgumentParser(
        description="Parse a BMO NG risk performance report file to "
                    "sum up compute times for MT tasks and ST tasks separately.",
        conflict_handler='resolve',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    arg_parser.add_argument(
        "f",
        type=str,
        help="full path to the performance report html file OR " \
            "full path to a file list of performance report html files."
    )
    
    arg_parser.add_argument(
        "-d",
        help="print debug trace.",
        action='store_true'
    )

    arg_parser.add_argument(
        "-t",
        type=int,
        default=0,
        help="print compute times of first n tasks only and exit."
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

    def __str__(self):
        return "grid {}    paths {:^7}  {:<7}".format(
            self.compute_time,
            self.paths,
            self.status
        )


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


class pricer_result_t (object):
    def __init__(self, pricer, cap_threads):
        self.pricer = pricer
        self.cap_threads = cap_threads
        self.num_tradegroups = 0
        self.num_tasks = 0
        self.compute_time = duration_t(0,0,0,0)

#
# The html body is organised as an unordered-list <ul>
# where each item <li>
# is a name marked by <a>Name ...</a>.
# followed by zero or more recursive unordered-lists.
# We are interested in a few of those inner lists with name hierarchy like
# Job -> Job Details -> TradeGroup
# Job -> Component [Grid]
#
# logic:
# When we see a Name we are interested in, we transition from CurrentState to
# new state called CurrentState->Name
# Then when we see the end tag </a> for that Name, we transition to
# new state called CurrentState->Name->
# It is in this state that we start processing actual data.
# This is because we want to skip similar looking data a) outside the inner lists
# we are interested in, and b) in one case even inside the <a>Name...</a>
#
# We exit state CurrentState->Name-> back to CurrentState-> when we see the 
# end tag for the <li> enclosing <a>Name...</a> and its zero or more recursive
# unordered-lists.
#
class HTMLPerfReportParser(HTMLParser):
    def __init__(self, num_tasks, isdebug, results):
        HTMLParser.__init__(self)
        self.num_tasks = num_tasks
        self.isdebug = isdebug
        self.results = results

        self.state = 'html->'
        self.li_counters = {}
        self.last_task = None
        self.is_tgsection_present = False
        
        # Duration = [00:00:03.159], Start = [00:13:54.897], End = [00:13:58.056], Computational = [2.11:34:03.159]
        self.computational_pattern = re.compile(
            r'\s*Computational\s*=\s*\[(\d*).(\d*):(\d*):(\d*).(?:\d*)\]'
        )

        self.is_legacy_format = None
        self.tradegroup_pattern = None

        # TaskTradeGroupId = 1#80012#TradeGroup#1089#2019-04-11 00:00:00#2019-05-23 19:07:16#8#100#8000#100#False#8
        # TaskTradeGroupId = 1#80012#TradeGroup#109#2019-04-11 00:00:00#2019-05-23 19:07:16#100#100#8000#100#True#1
        self.tradegroup_new_pattern = re.compile(
            r'\d*#\d*#TradeGroup#(\d*)#(?:\d|\-|\s|\:)*#(?:\d|\-|\s|\:)*#\d*#\d*#\d*#\d*#(?:True|False)#(\d*)'
        )

        # TaskTradeGroupId = 1#80012#TradeGroup#1089#2019-04-11 00:00:00#2019-05-23 19:07:16#8#100#8000#100
        self.tradegroup_legacy_pattern = re.compile(
            r'\d*#\d*#TradeGroup#(\d*)#(?:\d|\-|\s|\:)*#(?:\d|\-|\s|\:)*#\d*#\d*#\d*#\d*'
        )

        # No.Pos = 60 Pricing Credit.Cdx 
        self.pos_pricer_pattern = re.compile(
            # r'No\.Pos\s*=\s*(\d+)\s+Pricing\s+(^\s*)'
            r'No\.Pos\s*=\s*(\d+)\s+Pricing\s+(\S*)'
        )

        # 4900235#MFL1088#11:20, Success, 
        # 4900235#MFL1088#-1:-1, Success, 
        self.task_pattern_success = re.compile(
            r'\d*#MFL(\d*)#(-?\d*:-?\d*),\s*(Success),'
        )

        # 4900235#MFL1088#11:20, Success, 
        # 4900235#MFL1088#-1:-1, Success, 
        # 4127083#MFL204#20:29, Unhandled Exception,
        self.task_pattern = re.compile(
            r'\d*#MFL(\d*)#(-?\d*:-?\d*),\s*([A-Za-z]+\s?[A-Za-z]*),'
        )

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
            # print tradegroup.group(0)
            trade_group.id = tradegroup.group(1)
            trade_group.cap_threads = (
                1 if self.is_legacy_format else (int (tradegroup.group(2)))
            )
        else:
            raise Exception("parse error: TradeGroup ")
            
    def parse_task (self, data):
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
            raise Exception("parse error: task " + data)
        
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
                self.state = 'html->body->'
                if self.isdebug:
                    print self.state
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
                self.state = 'html->'
                if self.isdebug:
                    print self.state
            else:
                raise Exception("state transition logic error")
        elif tag == 'a':
            if self.state == 'html->body->jobdetails':
                self.state = 'html->body->jobdetails->'
                if self.isdebug:
                    print self.state
            elif self.state == 'html->body->jobdetails->tradegroup':
                self.state = 'html->body->jobdetails->tradegroup->'
                self.is_tgsection_present = True
                if self.isdebug:
                    print self.state
            elif self.state == 'html->body->grid':
                self.state = 'html->body->grid->'
                if not self.is_tgsection_present:
                    print "WARN: Performance report does not have section " + \
                        "html->body->jobdetails->tradegroup"
                if self.isdebug:
                    print self.state
        elif tag == 'li':
            if self.state not in self.li_counters:
                self.li_counters[self.state] = 0
                
            if self.state == 'html->body->jobdetails->':
                if self.li_counters[self.state] == 0:
                    self.state = 'html->body->'
                    if self.isdebug:
                        print self.state
                self.li_counters[self.state] -= 1
            elif self.state == 'html->body->jobdetails->tradegroup->':
                if self.li_counters[self.state] == 0:
                    self.state = 'html->body->jobdetails->'
                    if self.isdebug:
                        print self.state
                self.li_counters[self.state] -= 1
            elif self.state == 'html->body->grid->':
                if self.li_counters[self.state] == 0:
                    self.state = 'html->body->'
                    if self.isdebug:
                        print self.state
                self.li_counters[self.state] -= 1
                
            assert self.li_counters[self.state] >= 0

    def handle_data(self, data):
        #print "Encountered data  :", data
        if self.state == 'html->body->':
            if 'Job Details' == data:
                self.state = 'html->body->jobdetails'
                if self.isdebug:
                    print self.state
            elif 'Component [Grid],' == data:
                self.state = 'html->body->grid'
                if self.isdebug:
                    print self.state
        elif self.state == 'html->body->jobdetails->':
            if 'TradeGroup' == data:
                self.state = 'html->body->jobdetails->tradegroup'
                if self.isdebug:
                    print self.state
        elif self.state == 'html->body->jobdetails->tradegroup->':
            if '#TradeGroup#' in data:
                # print data
                tradegroup = trade_group_t()
                self.parse_tradegroup (data, tradegroup)
                self.parse_pos_pricer (data, tradegroup)
                self.results.tradegroups[tradegroup.id] = tradegroup
        elif self.state == 'html->body->grid->':
            # TODO : '#MFL' is a weak pattern, but ok for now.
            if '#MFL' in data:
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
                    days = int (computational_duration.group(1))
                    hours = int (computational_duration.group(2))
                    minutes = int (computational_duration.group(3))
                    seconds = int (computational_duration.group(4))

                    if self.last_task is not None:
                        self.last_task.compute_time = duration_t(
                            days, hours, minutes, seconds
                        ) 
                        tradegroup = self.results.tradegroups[
                            self.last_task.tradegroup_id
                        ]
                        tradegroup.tasks.append(self.last_task)
                        
                        if self.num_tasks > 0:
                            print "{:<40}  {:>2} {}  positions {:<4}".format (
                                tradegroup.pricer,
                                ("MT" if tradegroup.cap_threads > 1 else "ST"),
                                self.last_task,
                                tradegroup.num_positions
                            )
                                
                            self.num_tasks -= 1
                            
                            if self.num_tasks == 0:
                                exit(0)
                                
                        self.last_task = None
                    else:
                        raise Exception("report error: task not found before this computational_duration")
                else:
                    raise Exception("parse error: computational_duration")

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

def parse_perfreport (projpath, num_tasks, isdebug, results):

    print "parsing performance report: {}".format (get_filename_only (projpath))
    
    with open(projpath, 'r') as perfreport_file:
        perfreport_html = perfreport_file.read().replace('\n', '')
    
    perfreport_parser = HTMLPerfReportParser (num_tasks, isdebug, results)
    
    perfreport_parser.feed(perfreport_html)


if __name__ == "__main__":

    args = init_options()

    filepath = str(args.f)
    filepath = filepath.replace('/', '\\')
    if not os.path.isfile(filepath):
        print "the specified input file does not exist: " , filepath
        exit(0)
        
    perfreport_paths = []
    
    if filepath.endswith('html'):
        perfreport_paths.append(filepath)
    else:
        perfreport_paths = get_perfreport_paths_in (filepath)
        
    results = parsed_results_t();
    
    mt_duration = duration_t(0,0,0,0)
    st_duration = duration_t(0,0,0,0)
    num_mt_tasks = 0
    num_st_tasks = 0
    
    for perfreport_path in perfreport_paths:
        parse_perfreport (perfreport_path, args.t, args.d, results)
        
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
                    num_mt_tasks += 1
                    mt_duration += task.compute_time
                else:
                    num_st_tasks += 1
                    st_duration += task.compute_time
            
        # clear only tradegroups but not pricers
        results.tradegroups.clear()
        
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
    
    for item in sorted_results:
        print format_string.format (
            item[1].pricer,
            ("MT" if item[1].cap_threads > 1 else "ST"),
            item[1].compute_time,
            item[1].num_tradegroups,
            item[1].num_tasks
        )
    
    # print total tasks and total grid compute time summary
    
    input_file_name = get_filename_only(filepath)

    print(
        "\nSummary: {} ".format(
            input_file_name
        )
    )

    print "Number of tasks ST:MT is     ", num_st_tasks, " : ", num_mt_tasks
    print "Compute time ST:MT is     ", st_duration.to_seconds(), " : ", mt_duration.to_seconds()

