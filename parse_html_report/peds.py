# PErformance Daily Summary tool.
# Run help (-h) for description.
# usage:
# peds "C:\path_daily_perf_files\"

import re
import argparse
import os.path
from HTMLParser import HTMLParser
from datetime import datetime 


def init_options():
    arg_parser = argparse.ArgumentParser(
        description="Given a directory with a full days perf reports, "
            "parse all reports in the directory to obtain "
            "the start and end times of provisioning, grid compute "
            "and result writing. "
            "Then draw a web page with this time sequence diagram for all jobs.",
        conflict_handler='resolve',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    arg_parser.add_argument(
        "p",
        type=str,
        help="path - full path to one of the following: " \
            "a) a performance report html file."
            "c) a text file containing a list of performance report html files."
            "c) a directory containing the performance report html files."
    )
    
    arg_parser.add_argument(
        "-d",
        help="debug - print debug trace.",
        action='store_true'
    )

    return arg_parser.parse_args()


class job_t(object):
    def __init__(self):
        self.id = None
        self.name = None
        self.status = None
        self.start = None
        self.end = None
        self.start_provision = None
        self.end_provision = None
        self.start_compute = None
        self.end_compute = None
        self.start_resultwrite = None
        self.end_resultwrite = None


class results_t (object):
    def __init__(self):
        # list of parsed jobs sorted by start
        self.jobs = []
        
        # start of days run
        self.start = None
        
        # end of days run
        self.end = None


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
# Job
# Job -> Component [CnC] -> Provisioning
# Job -> Component [Grid]
# Job -> Component [RWS]
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
# When we enter a new state we set its li counter to 1.
# When we see a <li> we increment li counter of current state.
# When we see a </li> 
# 1. decrement li counter of current state.
# 2. if the current state li counter has reduced to 0 we 
#     a. exit the current state, goes to its outer state which makes it
#        the new current state
#     b. decrement the li counter of the current state.
#
class HTMLPerfReportParser(HTMLParser):
    def __init__(
            self, 
            is_debug,               # print debug trace
            result                  # out: result of parsing; of type job_t
        ):
        HTMLParser.__init__(self)
        self.is_debug = is_debug
        self.job = result

        self.state = 'html->'
        self.li_counters = {}
        self.jobid = '?'
        self.jobsummary = '?'

        self.callback_parser = HTMLCallbackParser (self)

        # Job [4134826], Success,
        self.jobid_pattern = re.compile(
            r'Job\s\[(\d*)\],\s*([A-Za-z]+\s?[A-Za-z]*),'
        )

        # , Start = [2019-10-30 02:49:50.065], End = [2019-10-30 05:19:37.269]
        # , Start = [04:15:26.933], End = [04:20:56.817]
        self.duration_pattern = re.compile(
            r',\s*Start\s*=\s*\[((?:\d|-|\s|:|\.)*)]\s*,\s*End\s*=\s*\[((?:\d|-|\s|:|\.)*)]'
        )

    #
    # call before parsing another performance report with the same instance of
    # this Parser class
    #
    def next(self):
        self.state = 'html->'
        self.li_counters = {}

    def enter_state(self, state):
        is_valid_state_transition = False
        if state.startswith (self.state):
            if state.replace(self.state, "").count("->") <= 1:
                is_valid_state_transition = True
                
        if not is_valid_state_transition:
            raise Exception(
                "Invalid State transition: " + self.state + " to " + state
            )
            
        if self.is_debug:
            print "State transition: ", self.state, " to ", state
        
        self.state = state
        
        if self.state.endswith ('->'):
            self.li_counters[self.state] = 1

    def exit_state(self):
        outer_state = self.state[0 : self.state[0:-2].rindex('->') + 2]

        if self.is_debug:
            print "State transition: ", self.state, " to ", outer_state
        
        self.state = outer_state
    
    def parse_job_header (self, data):
        jobmatch = self.jobid_pattern.search(data)
        if jobmatch:
            # print jobmatch.group(1), jobmatch.group(2)
            return (jobmatch.group(1), jobmatch.group(2))
        else:
            raise Exception("parse error: job header " + data)

    def parse_duration (self, data):
        match = self.duration_pattern.search(data)
        if match:
            # print match.group(1), match.group(2)
            try:
                start = datetime.strptime (match.group(1), "%Y-%m-%d %H:%M:%S.%f")
                end = datetime.strptime (match.group(2), "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                start = datetime.strptime (match.group(1), "%H:%M:%S.%f")
                end = datetime.strptime (match.group(2), "%H:%M:%S.%f")
                
            return (start, end)
        else:
            raise Exception("parse error: duration  " + data)

    def handle_starttag(self, tag, attrs):
        #print "Encountered start tag:", tag
        if tag == 'body':
            if self.state == 'html->':
                self.enter_state ('html->body->')
            else:
                raise Exception("state transition logic error")
        elif tag == 'li':
            if self.state in self.li_counters:
                self.li_counters[self.state] += 1
            else:
                raise Exception("state transition logic error")

    def handle_endtag(self, tag):
        #print "Encountered end tag :", tag
        if tag == 'body':
            if self.state == 'html->body->':
                self.exit_state ()
            else:
                raise Exception("state transition logic error")
        elif tag == 'a':
            if self.state == 'html->body->job':
                self.enter_state ('html->body->job->')
            elif self.state == 'html->body->job->cnc':
                self.enter_state ('html->body->job->cnc->')
            elif self.state == 'html->body->job->cnc->provisioning':
                self.enter_state ('html->body->job->cnc->provisioning->')
            elif self.state == 'html->body->job->grid':
                self.enter_state ('html->body->job->grid->')
            elif self.state == 'html->body->job->rws':
                self.enter_state ('html->body->job->rws->')

        elif tag == 'li':
            if self.state in self.li_counters:
                self.li_counters[self.state] -= 1
            else:
                raise Exception("state transition logic error")
                
            if self.li_counters[self.state] == 0:
                if self.state == 'html->body->job->':
                    self.exit_state ()
                elif self.state == 'html->body->job->cnc->':
                    self.exit_state ()
                elif self.state == 'html->body->job->cnc->provisioning->':
                    self.exit_state ()
                elif self.state == 'html->body->job->grid->':
                    self.exit_state ()
                elif self.state == 'html->body->job->rws->':
                    self.exit_state ()
                else:
                    print "li counter reached zero for unexpected ", self.state
                
                self.li_counters[self.state] -= 1
                assert self.li_counters[self.state] > 0

    def handle_data(self, data):
        #print "Encountered data  :", data
        if self.state == 'html->body->':
            if 'Job [' in data:
                self.enter_state ('html->body->job')
                (self.job.id, self.job.status) = self.parse_job_header (data)
        elif self.state == 'html->body->job':
            if 'Start = [' in data:
                (self.job.start, self.job.end) = self.parse_duration (data)
        elif self.state == 'html->body->job->':
            if 'Component [CnC],' == data:
                self.enter_state ('html->body->job->cnc')
            elif 'Component [Grid],' == data:
                self.enter_state ('html->body->job->grid')
            elif 'Component [RWS],' == data:
                self.enter_state ('html->body->job->rws')
        elif self.state == 'html->body->job->cnc->':
            if 'Provisioning,' == data:
                self.enter_state ('html->body->job->cnc->provisioning')
        elif self.state == 'html->body->job->cnc->provisioning':
            if 'Start = [' in data:
                (self.job.start_provision, self.job.end_provision) = \
                    self.parse_duration (data)
        elif self.state == 'html->body->job->grid':
            if 'Start = [' in data:
                (self.job.start_compute, self.job.end_compute) = \
                    self.parse_duration (data)
        elif self.state == 'html->body->job->rws':
            if 'Start = [' in data:
                (self.job.start_resultwrite, self.job.end_resultwrite) = \
                    self.parse_duration (data)


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

def get_perfreport_paths_in_file (filepath):
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

def get_perfreport_paths_in_dir (dirpath):
    return []

def parse_perfreport (
        filepath, 
        is_debug, 
        result      # out
):
    filename = get_filename_only (filepath)
    print "parsing performance report: {}".format (filename)
    
    with open(filepath, 'r') as perfreport_file:
        perfreport_html = perfreport_file.read().replace('\n', '')
    
        perfreport_parser = (
            HTMLPerfReportParser (
                is_debug, 
                result
            )
        )
        
        perfreport_parser.feed(perfreport_html)
        
        result.name = filename[filename.index('_') + 1 : filename.rindex('_')]

def parse_perfreports (
        path, 
        is_debug, 
        results     # out
):
    path = str(path)
    path = path.replace('/', '\\')
    if not os.path.exists(path):
        print "the specified path does not exist: " , path
        exit(0)
        
    perfreport_paths = []
    
    if os.path.isfile(path):
        if path.endswith('html'):
            perfreport_paths.append(path)
        else:
            perfreport_paths = get_perfreport_paths_in_file (path)
    else:
        perfreport_paths = get_perfreport_paths_in_dir (path)
        
    for perfreport_path in perfreport_paths:
        result = job_t()
        
        parse_perfreport (
            perfreport_path, 
            is_debug, 
            result
        )
        
        results.jobs.append(result)

def draw_results (results, dt_origin):
    for job in results.jobs:
        attrs = vars(job)
        for item in attrs.items():
            print item[0], ': ', item[1]
  

if __name__ == "__main__":

    args = init_options()

    results = results_t();
    
    parse_perfreports (args.p, False, results)
    
    draw_results (results, datetime.now())
