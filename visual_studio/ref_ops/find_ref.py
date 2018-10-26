#
# Find all projects and config files in a solution that references a particular
# assembly.
# usage:
# find_ref --sln "path\sln_to_remove.bin" --ref "log4net"
#     note: the bin file for a sln can be produced using parse_sln.py

import argparse
import os.path
import pickle
import re
from xml.dom.minidom import parse
from parse_sln import presults, get_filename_only, get_absolute_path

def init_options():
    # usage:
    # find_ref --sln "path\sln_to_remove.bin" --ref "log4net"
    arg_parser = argparse.ArgumentParser(
        description="Find all projects and config files in a solution "
                    "that references a particular assembly. "
                    "Note: bin file for a sln can be produced using parse_sln.py",
        conflict_handler='resolve',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
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

    return arg_parser.parse_args()


def parse_pkgconfig(filepath, refname, ref_pkgconfigs, freport):

    datasource = open(filepath)

    dom = parse(datasource)
    
    packages = dom.documentElement.getElementsByTagName("package")
    
    for package in packages:
        if (
            package.nodeType == 1
        ):
            assembly = package.getAttribute("id")
            assembly_lowercase = assembly.lower()
            if assembly_lowercase.find(refname.lower()) >= 0:
                ref_pkgconfigs.add(filepath)
                freport.write(filepath + '\n')
                freport.write(package.toxml() + '\n')


def parse_appconfig(filepath, refname, ref_appconfigs, freport):

    datasource = open(filepath)
    
    dom = parse(datasource)
    
    depassemblies = dom.documentElement.getElementsByTagName("dependentAssembly")
    
    for depassembly in depassemblies:
        for childnode in depassembly.childNodes:
            if (
                childnode.nodeType == 1 and
                childnode.tagName == "assemblyIdentity"
            ):
                assembly = childnode.getAttribute("name")
                assembly_lowercase = assembly.lower()
                if assembly_lowercase.find(refname.lower()) >= 0:
                    ref_appconfigs.add(filepath)
                    freport.write(filepath + '\n')
                    freport.write(depassembly.toxml() + '\n')
    
    cfgsections = dom.documentElement.getElementsByTagName("configSections")
    
    for cfgsection in cfgsections:
        for section in cfgsection.childNodes:
            if (
                section.nodeType == 1 and
                section.tagName == "section"
            ):
                assembly = section.getAttribute("name")
                assembly_lowercase = assembly.lower()
                if assembly_lowercase.find(refname.lower()) >= 0:
                    ref_appconfigs.add(filepath)
                    freport.write(filepath + '\n')
                    freport.write(section.toxml() + '\n')

def parse_proj(projpath, refname, ref_projects, freport):

    datasource = open(projpath)
    
    dom = parse(datasource)
    
    itemgroups = dom.documentElement.getElementsByTagName("ItemGroup")
    
    for itemgroup in itemgroups:
        for item in itemgroup.childNodes:
            if (
                item.nodeType == 1 and 
                item.tagName == "Reference"
            ):
                assembly = item.getAttribute("Include")
                if assembly is None:
                    assembly = item.getAttribute("include")
                assembly_lowercase = assembly.lower()
                if assembly_lowercase.find(refname.lower()) >= 0:
                    ref_projects.add(projpath)
                    freport.write(projpath + '\n')
                    freport.write(item.toxml() + '\n')

                    """
                    # we want to match pattern that looks like
                    # Version=1.2.10.0, Culture=neutral, PublicKeyToken=1b44e1d426115821, processorArchitecture=MSIL.
                    # Also we want to capture the version number which could be 3 or 4 parts.
                    version_pattern = re.compile(
                        r'version\s*=\s*((?:[0-9]|\.)*)'
                    )
                    assembly_version = version_pattern.findall(assembly_lowercase)
                    if assembly_version:
                        freport.write(assembly_version[0] + '\n')
                    else:
                        freport.write("version unspecified" + '\n')

                    hintpaths = item.getElementsByTagName("HintPath")
                    for hintpathnode in hintpaths:
                        for childnode in hintpathnode.childNodes:
                            if childnode.nodeType == 3 :
                                freport.write(childnode.nodeValue + '\n')
                                hintpath = get_absolute_path(projpath, childnode.nodeValue)
                                freport.write(hintpath + '\n')

                    """

if __name__ == "__main__":

    args = init_options()

    sln_projects = set()

    sln = str(args.sln)
    sln = sln.replace('/', '\\')
    if not os.path.isfile(sln):
        print "specified bin file does not exist: ", sln
        exit(0)

    sln_name = get_filename_only(sln)

    with open(sln, 'r') as fsln:
        sln_results = pickle.load(fsln)

        sln_projects = sln_results.projects_in_sln
        sln_files = sln_results.files_references        

        print "searching " + str(len(sln_projects)) + " projects in solution ",
        print sln_name + " for references to assembly " + args.ref

    ref_projects = set()
    ref_appconfigs = set()
    ref_pkgconfigs = set()

    sln_name = get_filename_only(args.sln)
    report_fname = args.ref + "_references_in_" + sln_name + ".txt"
    with open(report_fname, 'w') as freport:
        for projpath in sln_projects:
            parse_proj(projpath, args.ref, ref_projects, freport)

        freport.write("\n----------------------------------------------------")
        freport.write("----------------------------------------------------\n")
        
        for filepath in sln_files:
            if os.path.isfile(filepath):
                if filepath.endswith("App.config"):
                    parse_appconfig(filepath, args.ref, ref_appconfigs, freport)

        freport.write("\n----------------------------------------------------")
        freport.write("----------------------------------------------------\n")
        
        for filepath in sln_files:
            if os.path.isfile(filepath):
                if filepath.endswith("packages.config"):
                    parse_pkgconfig(filepath, args.ref, ref_pkgconfigs, freport)

        freport.write("\n----------------------------------------------------")
        freport.write("----------------------------------------------------\n")

        print "\nSummary:"
        freport.write("\nSummary:" + '\n')

        proj_summary = (
            str(len(ref_projects)) + " projects in solution " + sln_name
            + " references assembly " + args.ref + "\n"
        )
        print proj_summary
        freport.write(proj_summary + '\n')

        appcfg_summary = (
            str(len(ref_appconfigs)) + " App.config in solution " + sln_name
            + " references assembly " + args.ref + "\n"
        )
        print appcfg_summary
        freport.write(appcfg_summary + '\n')

        pkgcfg_summary = (
            str(len(ref_pkgconfigs)) + " packages.config in solution " + sln_name
            + " references assembly " + args.ref + "\n"
        )
        print pkgcfg_summary
        freport.write(pkgcfg_summary + '\n')
