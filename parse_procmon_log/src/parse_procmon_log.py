# 
# Parse a Process Monitor log file in XML format.
#

from xml.dom.minidom import parse
import re
import argparse
import os.path
import pickle


def init_options():
    arg_parser = argparse.ArgumentParser(
        description="Parse a Process Monitor log file in XML format.",
        conflict_handler='resolve',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    arg_parser.add_argument(
        "f",
        type=str,
        help="full path to the procmon log file in xml format.",
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


def parse_log(logpath, results):

    datasource = open(logpath)
    
    dom = parse(datasource)
    
    events = dom.documentElement.getElementsByTagName("event")
    
    for event in events:
        isCreateFile = False
        path = None
        for item in event.childNodes:
            if (
                    item.nodeType == 1 and 
                    item.tagName == "Operation"
                ):
                if "CreateFile" in item.childNodes[0].nodeValue:
                    isCreateFile = True

            if (
                    item.nodeType == 1 and 
                    item.tagName == "Path"
                ):
                path = item.childNodes[0].nodeValue
                
        if isCreateFile and path is not None:
            results.CreateFile_Path.add (path)

class presults(object):
    def __init__(self):
        self.CreateFile_Path = set()


if __name__ == "__main__":

    args = init_options()

    logpath = str(args.f)
    logpath = logpath.replace('/', '\\')
    if not os.path.isfile(logpath):
        print "specified file does not exist: " , logpath
        exit(0)

    results = presults();

    parse_log(logpath, results)
    
    log_name = get_filename_only(logpath)

    output_filename = log_name + "_files.txt"
    with open(output_filename, 'w') as f:
        for filepath in sorted(results.CreateFile_Path):
            f.write(filepath + '\n')

    num_file_exists = 0
    output_filename = log_name + "_existing_files.txt"
    with open(output_filename, 'w') as f:
        for filepath in sorted(results.CreateFile_Path):
            if os.path.isfile(filepath):
                f.write(filepath + '\n')
                num_file_exists = num_file_exists + 1

    """
    output_filename = log_name + ".bin"
    with open(output_filename, 'w') as f:
        pickle.dump(results, f)
    """
    
    print(
        "Summary: "
        "\nFound {} CreateFile Paths in Process Monitor log."
        "\nOnly {} of those files exist.".format(
            len(results.CreateFile_Path),
            num_file_exists
        )
    )
