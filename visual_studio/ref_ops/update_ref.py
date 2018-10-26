# 
# update assembly reference in
# all proj and config files
# inside a specified visual studio solution.
# 

import argparse
import os.path
import pickle
import re
from xml.dom.minidom import parse, parseString
from parse_sln import presults, get_filename_only, get_absolute_path
from os.path import relpath
import copy
import codecs

def init_options():
    # usage:
    # find_ref --sln "path\sln_to_remove.bin" --ref "log4net"
    arg_parser = argparse.ArgumentParser(
        description="Update assembly references inside a specified visual"
                    " studio solution.",
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


def parse_pkgconfig(filepath, refname, dom_package, ref_pkgconfigs, freport):

    update_fpkgcfg = False

    with open(filepath, 'r') as fpkgcfg:
        dom = parse(fpkgcfg)

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
                        
                    package.parentNode.replaceChild(dom_package, package)
                    update_fpkgcfg = True

    if update_fpkgcfg:
        with codecs.open(filepath, 'w', "utf-8") as fpkgcfg:
            dom.writexml(fpkgcfg, encoding="utf-8")


def parse_appconfig(filepath, refname, dom_section, dom_depassembly, ref_appconfigs, freport):

    update_fappcfg = False

    with open(filepath, 'r') as fappcfg:
        dom = parse(fappcfg)
        
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
                        
                        depassembly.parentNode.replaceChild(dom_depassembly, depassembly)
                        update_fappcfg = True
        
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

                        cfgsection.replaceChild(dom_section, section)
                        update_fappcfg = True

    if update_fappcfg:
        with codecs.open(filepath, 'w', "utf-8") as fappcfg:
            dom.writexml(fappcfg, encoding="utf-8")


def parse_proj(projpath, refname, dom_reference, hint_abspath, ref_projects, freport):

    update_fproj = False

    with open(projpath, 'r') as fproj:
        try:
            dom = parse(fproj)
        except:
            print "failed to parse " + projpath
            raise
        
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
                        
                        hint_path =  relpath(hint_abspath, os.path.dirname(projpath))
                        newitem = copy.deepcopy(dom_reference)
                        newitem.getElementsByTagName("HintPath")[0].childNodes[0].nodeValue = hint_path
                        itemgroup.replaceChild(newitem, item)
                        
                        update_fproj = True
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
    if update_fproj:
        with codecs.open(projpath, 'w', "utf-8") as fproj:
            dom.writexml(fproj, encoding="utf-8")


def update_refs(args, set_projects, set_files, freport):
    ref_projects = set()
    ref_appconfigs = set()
    ref_pkgconfigs = set()

    dom_reference = parseString(args.xml_reference)
    dom_reference = dom_reference.getElementsByTagName("Reference")[0]
    dom_reference_abspath = dom_reference.getElementsByTagName("HintPath")[0].childNodes[0].nodeValue
    if not os.path.isfile(dom_reference_abspath):
        raise ValueError('arg xml_reference HintPath ' + dom_reference_abspath + ' doesnt exist.')
    
    for projpath in set_projects:
        parse_proj(projpath, args.ref, dom_reference, dom_reference_abspath, ref_projects, freport)

    freport.write("\n----------------------------------------------------")
    freport.write("----------------------------------------------------\n")

    dom_section = parseString(args.xml_section)
    dom_section = dom_section.getElementsByTagName("section")[0]
    dom_depassembly = parseString(args.xml_depassembly)
    dom_depassembly = dom_depassembly.getElementsByTagName("dependentAssembly")[0]

    for filepath in set_files:
        if os.path.isfile(filepath):
            if (
                filepath.endswith("App.config") or
                filepath.endswith("app.config") or
                filepath.endswith("AppDomain.config") or
                filepath.endswith("appdomain.config") or
                filepath.endswith("BMO.Workflow.Visual.exe.config") or
                filepath.endswith("bmo.workflow.visual.exe.config") or
                filepath.endswith("Web.config") or
                filepath.endswith("web.config")
            ):
                parse_appconfig(filepath, args.ref, dom_section, dom_depassembly, ref_appconfigs, freport)

    freport.write("\n----------------------------------------------------")
    freport.write("----------------------------------------------------\n")

    dom_package = parseString(args.xml_package)
    dom_package = dom_package.getElementsByTagName("package")[0]

    for filepath in set_files:
        if os.path.isfile(filepath):
            if filepath.endswith("packages.config"):
                parse_pkgconfig(filepath, args.ref, dom_package, ref_pkgconfigs, freport)

    freport.write("\n----------------------------------------------------")
    freport.write("----------------------------------------------------\n")

    print "\nSummary:"
    freport.write("\nSummary:" + '\n')

    proj_summary = (
        str(len(ref_projects)) + " projects updated.\n"
    )
    print proj_summary
    freport.write(proj_summary + '\n')

    appcfg_summary = (
        str(len(ref_appconfigs)) + " App.config updated.\n"
    )
    print appcfg_summary
    freport.write(appcfg_summary + '\n')

    pkgcfg_summary = (
        str(len(ref_pkgconfigs)) + " packages.config updated.\n"
    )
    print pkgcfg_summary
    freport.write(pkgcfg_summary + '\n')

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

        sln_projects = sln_results.projects_in_sln
        sln_files = sln_results.files_references        

        print "searching " + str(len(sln_projects)) + " projects in solution ",
        print sln_name + " for references to assembly " + args.ref

    # for test only
    # sln_projects.add(r'C:\BMOdev\rcng\rcng\NewPlatform\IntegrationTests\BMO.Risk.CacheToDbWriter.IntegrationTest\BMO.Risk.CacheToDbWriter.IntegrationTest.csproj')
    # sln_files.add(r'C:\BMOdev\rcng\rcng\NewPlatform\Risk\ResultWriting\BMO.Risk.ResultWritingTests\BMO.Risk.ResultWritingTests\App.config')
    # sln_files.add(r'C:\BMOdev\rcng\rcng\NewPlatform\Risk\Calculators\BMO.Risk.EnterpriseRiskCalculators\packages.config')

    sln_name = get_filename_only(args.sln)
    report_fname = args.ref + "_references_in_" + sln_name + ".txt"
    with open(report_fname, 'w') as freport:
        update_refs(args, sln_projects, sln_files, freport)
