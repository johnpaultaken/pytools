# 
# Enumerate all files of a specified type that can be removed from a repo
# while keeping all files referenced by specified visual studio solutions.
# If remove type specified is 'sln' or 'proj' then removable files enumerated
# will also include files referenced by the removable 'sln' or 'proj' files.
# Usage:
# repo_clean.py --repo "C:\gitroot"
#               --removetype "cs"
#               --keepsln "C:\path\keepsln1.bin"
#               --keepsln "C:\path\keepsln2.bin"
#               --excludedir "C:\gitroot\do_not_remove"
#
# notes:
# bin file for a sln can be produced using parse_sln.py.
# directory params must NOT end with \
#


import argparse
import os.path
import pickle
from parse_sln import presults, get_filename_only, parse_projrefs
from diff_sln import to_git_path


def init_options():

    arg_parser = argparse.ArgumentParser(
        description="Clean repo while keeping specified visual studio"
                    " solutions.",
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
        "--keepsln",
        action='append',
        type=str,
        default=[],
        help="full path to the .bin of solution you want to keep."
    )

    arg_parser.add_argument(
        "--removetype",
        type=str,
        help="type of files you want removed from repo.",
        required=True
    )

    arg_parser.add_argument(
        "--excludedir",
        action='append',
        type=str,
        default=[],
        help="full path to the directory you want to exclude from remove."
    )

    args = arg_parser.parse_args()
    
    return args


if __name__ == "__main__":

    args = init_options()

    removetype = str(args.removetype)
    if removetype.lower() == 'sln':
        print "sln files not supported as of now."
        exit(0)
    removeextn = '.' + removetype
    removeextn_lc = removeextn.lower()
    print "Finding all removable " + removeextn_lc + " from ",

    repopath = str(args.repo)
    repopath = repopath.replace('/', '\\')
    if not os.path.isdir(repopath):
        print "specified repo does not exist: ", repopath
        exit(0)
    print repopath + " while keeping files of following solutions:"

    remove_files = set()

    for root, dirnames, filenames in os.walk(repopath):
        is_exclude_dir = False
        for excludedir in args.excludedir:
            if root.lower().startswith(excludedir.lower()):
                is_exclude_dir = True
                break;
        if is_exclude_dir:
            continue

        for filename in filenames:
            if filename.lower().endswith(removeextn_lc):
                remove_files.add(os.path.join(root, filename))

    if (removeextn_lc=='.csproj' or removeextn_lc=='.fsproj'):
        remove_projs = remove_files
        remove_files = set()
        
        unparsed_projects = remove_projs.copy()
        results = presults();
        # parse all the project referenced projects recursively
        while len(unparsed_projects) > 0:
            results.projects_references.clear()
            parse_projrefs(unparsed_projects, results)
            unparsed_projects = set.difference (
                results.projects_references, results.projects_in_sln
            )

        remove_files = set.union (
            results.files_references, results.projects_in_sln
        )

    keep_files = set()

    for keep_sln in args.keepsln:
        keep_sln = keep_sln.replace('/', '\\')
        if not keep_sln.lower().endswith('.bin'):
            print "need .bin file for .sln created using parse_sln"
            exit(0)
        if not os.path.isfile(keep_sln):
            print "specified bin file does not exist: " , keep_sln
            exit(0)

        with open(keep_sln, 'r') as fkeep:
            keep_results = pickle.load(fkeep)

            print " ", get_filename_only(keep_sln),
            print '(' + str(len(keep_results.files)) + ')'
            
            keep_files = set.union(keep_files, keep_results.files)

    remove_files = set.difference(remove_files, keep_files)

    # since windows file path is case insensitive, we have to do this.
    keep_files_lowercase = set()
    for filepath in keep_files:
        keep_files_lowercase.add(filepath.lower())
    for filepath in remove_files.copy():
        if filepath.lower() in keep_files_lowercase:
            remove_files.remove(filepath)

    print len(remove_files), "files from", repopath, "can be removed."
    
    net_remove_files = set()
    for filepath in remove_files:
        if os.path.isfile(filepath):
            net_remove_files.add(to_git_path(filepath, repopath))

    print len(net_remove_files), "files can be removed excluding non-existant:"

    net_remove_name = "repo_" + removetype + "_remove_files.txt"
    with open(net_remove_name, 'w') as f:
        for filepath in sorted(net_remove_files):
            f.write(filepath + '\n')
            print filepath
