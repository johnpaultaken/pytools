# usage:
# parse_sln "C:\path\VS2015solution.sln"

from xml.dom.minidom import parse
import re
import argparse
import os.path
import pickle

def init_options():
    # usage:
    # parse_sln "C:\path\VS2015solution.sln"
    arg_parser = argparse.ArgumentParser(
        description="Parse a VS2015 sln file to "
                    "print all files referenced by the sln and the included projects.",
        conflict_handler='resolve',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    arg_parser.add_argument(
        "sln",
        type=str,
        help="full path to the sln file.",
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

def parse_proj(projpath, results):

    datasource = open(projpath)
    
    dom = parse(datasource)
    
    itemgroups = dom.documentElement.getElementsByTagName("ItemGroup")
    
    for itemgroup in itemgroups:
        for item in itemgroup.childNodes:
            if (
                item.nodeType == 1 and 
                item.tagName != "Reference" and
                item.tagName != "BootstrapperPackage" and
                item.tagName != "Service" and
                item.tagName != "WCFMetadata" and
                item.tagName != "CodeAnalysisDependentAssemblyPaths"
                ):
                filepath = item.getAttribute("Include")
                #print projpath, filepath
                filepath = get_absolute_path(projpath, filepath)
                #print item.tagName, filepath
                if item.tagName == "ProjectReference":
                    if filepath not in results.projects_references:
                        results.projects_references.add (filepath)
                else:
                    if filepath not in results.files_references:
                        results.files_references.add (filepath)


def parse_projrefs(ref_projects, results):
    for projpath in ref_projects:
        if projpath not in results.projects_in_sln:
            results.projects_in_sln.add (projpath)
            if os.path.isfile(projpath):
                parse_proj (projpath, results)
            else:
                print "project referenced project does not exist: " , projpath


def parse_sln(slnpath, results):
    with open(slnpath, 'r') as slnfile:
        slnstring = slnfile.read()
    
    # we want to match this pattern.
    # Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "MRNG.CmdLine", "..\Command-Control\Projects\MRNG\MRNG.CmdLine\MRNG.CmdLine.csproj", "{B9CFF7AB-22C0-44C6-8C35-A665A6560F31}"
    # Also we want to capture the first GUID and the project path.
    # If the first GUID is 2150E333-8FDC-42A3-9474-1A3956D46DE8 it is not a project but a grouping folder.
    proj_pattern = re.compile(
        r'Project\("{((?:[A-Z]|[0-9]|-)*)}"\)\s*'
        r'=\s*"(?:[A-Z]|[a-z]|[0-9]|\.| |-|_)*"'
        r',\s*"((?:[A-Z]|[a-z]|[0-9]|\.| |-|_|\\)*)"'
    )

    projects = proj_pattern.findall(slnstring)
    for project in projects:
        if project[0] != '2150E333-8FDC-42A3-9474-1A3956D46DE8':
            # sanity check
            if (project[0] != 'FAE04EC0-301F-11D3-BF4B-00C04F79EFBC' # csproj
                and
                project[0] != 'F2A71F9B-5D33-465A-A702-920D77279786' # fsproj
                ):
                raise Exception('unexpected project GUID: ' + str(project))
            # sanity check
            if not project[1].endswith("proj"):
                raise Exception('no proj extension for: ' + project[1])
            
            # print project[1]
            projpath = get_absolute_path(slnpath, project[1])
            #print projpath
            if projpath not in results.projects_in_sln:
                results.projects_in_sln.add (projpath)
                if os.path.isfile(projpath):
                    parse_proj (projpath, results)
                else:
                    print "project in solution does not exist: " , projpath

class presults(object):
    def __init__(self):
        self.projects_in_sln = set()
        self.projects_references = set()
        self.files_references = set()


if __name__ == "__main__":

    args = init_options()

    slnpath = str(args.sln)
    slnpath = slnpath.replace('/', '\\')
    if not os.path.isfile(slnpath):
        print "specified sln file does not exist: " , slnpath
        exit(0)

    results = presults();

    parse_sln(slnpath, results)
    
    unparsed_projects = set.difference (results.projects_references, results.projects_in_sln)
    if len(unparsed_projects) > 0:
        print 'Error: these project referenced projects not included in solution :'
        for unparsed_project in unparsed_projects:
            print unparsed_project

    # parse all the project referenced projects recursively
    while len(unparsed_projects) > 0:
        results.projects_references.clear()
        parse_projrefs(unparsed_projects, results)
        unparsed_projects = set.difference (results.projects_references, results.projects_in_sln)

    results.files = set.union (results.files_references, results.projects_in_sln)
    
    sln_name = get_filename_only(slnpath)

    sln_files = sln_name + "_files.txt"
    with open(sln_files, 'w') as f:
        for filepath in sorted(results.files):
            f.write(filepath + '\n')

    num_file_exists = 0
    sln_files = sln_name + "_existing_files.txt"
    with open(sln_files, 'w') as f:
        for filepath in sorted(results.files):
            if os.path.isfile(filepath):
                f.write(filepath + '\n')
                num_file_exists = num_file_exists + 1

    sln_results = sln_name + ".bin"
    with open(sln_results, 'w') as f:
        pickle.dump(results, f)

    print(
        "Summary: "
        "\nFound {} projects in solution."
        "\n{} files in total are referenced by the solution."
        "\n{} referenced files exist.".format(
            len(results.projects_in_sln),
            len(results.files),
            num_file_exists
        )
    )
