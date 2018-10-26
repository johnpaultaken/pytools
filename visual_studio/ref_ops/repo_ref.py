# 
# Update assembly reference in
# all proj and config files
# outside a specified visual studio solution.
# 

import argparse
import os.path
import os
import pickle
import re
from xml.dom.minidom import parse, parseString
from parse_sln import presults, get_filename_only, get_absolute_path
from os.path import relpath
import copy
import codecs
from update_ref import update_refs


def init_options():
    # usage:
    # find_ref --sln "path\sln_to_remove.bin" --ref "log4net"
    arg_parser = argparse.ArgumentParser(
        description="Update assembly references outside a specified visual"
                    " studio solution.",
        conflict_handler='resolve',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    arg_parser.add_argument(
        "--repo",
        type=str,
        help="repo root path.",
        required=True
    )

    arg_parser.add_argument(
        "--sln",
        type=str,
        help="full path to the .bin of solution.",
        required=True
    )

    arg_parser.add_argument(
        "--ref",
        type=str,
        help="name of the assembly reference (case insensitive).",
        required=True
    )

    args = arg_parser.parse_args()
    
    args.xml_reference = r"""
        <Reference Include="log4net, Version=2.0.8.0, Culture=neutral, PublicKeyToken=669e0ddf0bb1aa2a, processorArchitecture=MSIL">
            <HintPath>C:\BMOdev\rcng\rcng\NewPlatform\build\packages\MFL.20181014.76557.64\lib\log4net.dll</HintPath>
            <Private>True</Private>
        </Reference>
    """
    
    args.xml_section =r"""
        <section name="log4net" type="log4net.Config.Log4NetConfigurationSectionHandler,log4net,Version=2.0.8.0, Culture=neutral, PublicKeyToken=669e0ddf0bb1aa2a" />
    """
    
    args.xml_depassembly = r"""
      <dependentAssembly>
        <assemblyIdentity name="log4net" publicKeyToken="669e0ddf0bb1aa2a" culture="neutral" />
        <codeBase version="2.0.8.0" href="log4net\log4netv2.0.8.0\log4net.dll" />
      </dependentAssembly>
    """

    args.xml_package = r"""
        <package id="log4net" targetFramework="net462" version="2.0.8"/>
    """
    
    return args
    


if __name__ == "__main__":

    args = init_options()

    sln = str(args.sln)
    sln = sln.replace('/', '\\')
    if not os.path.isfile(sln):
        print "specified bin file does not exist: ", sln
        exit(0)

    sln_name = get_filename_only(sln)
    sln_projects = set()
    sln_files = set()

    with open(sln, 'r') as fsln:
        sln_results = pickle.load(fsln)

        #convert to lower case because windows path is case insensitive.
        for slnproj in sln_results.projects_in_sln:
            sln_projects.add(slnproj.lower())
        for slnfile in sln_results.files_references:
            sln_files.add(slnfile.lower())

        print "found " + str(len(sln_projects)) + " projects in solution."
        print "found " + str(len(sln_files)) + " files in solution."

    repo_projects = set()
    repo_files = set()
    
    for root, dirnames, filenames in os.walk(args.repo):
        for filename in filenames:
            if (
                filename.endswith(".csproj") or
                filename.endswith(".fsproj")
            ):
                #convert to lower case because windows path is case insensitive.
                repo_projects.add(os.path.join(root, filename).lower())
            elif (
                filename.endswith("App.config") or
                filename.endswith("app.config") or
                filename.endswith("AppDomain.config") or
                filename.endswith("appdomain.config") or
                filename.endswith("BMO.Workflow.Visual.exe.config") or
                filename.endswith("bmo.workflow.visual.exe.config") or
                filename.endswith("Web.config") or
                filename.endswith("web.config") or
                filename.endswith("packages.config")
            ):
                #convert to lower case because windows path is case insensitive.
                repo_files.add(os.path.join(root, filename).lower())
    
    # for test only
    #repo_projects.add(r'c:\bmodev\rcng\rcng\newplatform\risk\calculatorframework\bmo.risk.r\bmo.risk.r.csproj')
    #repo_files.add(r'c:\bmodev\rcng\rcng\newplatform\tests\irswaptionpricerperformance.test\app.config')
    #repo_files.add(r'C:\BMOdev\rcng\rcng\NewPlatform\Infrastructure\Shared\Bmo.Shared\packages.config')

    print "found " + str(len(repo_projects)) + " projects in repo."
    print "found " + str(len(repo_files)) + " files in repo."

    diff_projects = set.difference(repo_projects, sln_projects)
    diff_files = set.difference(repo_files, sln_files)
    print "found " + str(len(diff_projects)) + " projects in repo but outside solution."
    print "found " + str(len(diff_files)) + " files in repo but outside solution."

    # just a safety check
    for fn in sorted(diff_files):
        if fn in sln_files:
            raise Exception("file in solution must not be modified")
        else:
            pass

    # just a safety check
    for pn in sorted(diff_projects):
        if pn in sln_projects:
            raise Exception("project in solution must not be modified")
        else:
            pass

    
    sln_name = get_filename_only(args.sln)
    report_fname = args.ref + "_in_repo_outside_" + sln_name + ".txt"
    with open(report_fname, 'w') as freport:
        update_refs(args, diff_projects, diff_files, freport)
    

