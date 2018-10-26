# 
# Find all files you can delete from a visual studio sln you want to remove,
# while keeping several other solutions,
# without deleting shared files from sln you want to keep.
# Usage:
# diff_sln.py --remove "C:\path\removesln.bin"
#             --keep "C:\path\keepsln1.bin"
#             --keep "C:\path\keepsln2bin"
#             --reporoot "C:\gitroot\\"
#             --excludedir "C:\gitroot\do_not_remove\\"
#
# notes:
# bin file for a sln can be produced using parse_sln.py.
# parameters ending with \ must use escape \\
# directory params must end with \\
#

import argparse
import os.path
import pickle
from parse_sln import presults, get_filename_only


def init_options():
    arg_parser = argparse.ArgumentParser(
        description="Find all files you can delete from a sln you want to remove,"
                    " while keeping several other solutions,"
                    " without deleting shared files from sln you want to keep."
                    "Note: bin file for a sln can be produced using parse_sln.py",
        conflict_handler='resolve',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    arg_parser.add_argument(
        "--remove",
        type=str,
        help="full path to the .bin of solution you want to remove.",
        required=True
    )

    arg_parser.add_argument(
        "--keep",
        action='append',
        type=str,
        default=[],
        help="full path to the .bin of solution you want to keep."
    )

    arg_parser.add_argument(
        "--reporoot",
        type=str,
        help="full path to the root of the repo.",
        required=True
    )

    arg_parser.add_argument(
        "--excludedir",
        action='append',
        type=str,
        default=[],
        help="full path to the directory you want to exclude from remove."
    )

    return arg_parser.parse_args()


def to_git_path(filepath, git_root):
    if not git_root.endswith('\\'):
        git_root = git_root + '\\'

    if filepath.startswith(git_root):
        return filepath.replace(git_root, "", 1).replace('\\','/')
    else:
        raise Exception("file " + filepath + " is outside gitroot " + git_root)


if __name__ == "__main__":

    args = init_options()

    remove_files = set()

    remove_sln = str(args.remove)
    remove_sln = remove_sln.replace('/', '\\')
    if not os.path.isfile(remove_sln):
        print "specified bin file does not exist: ", remove_sln
        exit(0)

    remove_sln_name = get_filename_only(remove_sln)

    with open(remove_sln, 'r') as fremove:
        remove_results = pickle.load(fremove)

        remove_files = remove_results.files

        print "generating removable files for solution ",
        print remove_sln_name, '(' + str(len(remove_files)) + ')'
        print " while keeping all files for the following solutions:"

    keep_files = set()

    for keep_sln in args.keep:
        keep_sln = keep_sln.replace('/', '\\')
        if not os.path.isfile(keep_sln):
            print "specified bin file does not exist: " , keep_sln
            exit(0)

        with open(keep_sln, 'r') as fkeep:
            keep_results = pickle.load(fkeep)

            print " ", get_filename_only(keep_sln),
            print '(' + str(len(keep_results.files)) + ')'
            
            keep_files = set.union(keep_files, keep_results.files)

    remove_files = set.difference(remove_files, keep_files)

    # since windows file path is case insensitive,
    # a VS project can specify the same file with different case.
    # So we have to do this.
    keep_files_lowercase = set()
    for filepath in keep_files:
        keep_files_lowercase.add(filepath.lower())
    for filepath in remove_files.copy():
        if filepath.lower() in keep_files_lowercase:
            remove_files.remove(filepath)

    print len(remove_files), "files from", remove_sln_name, "can be removed."

    net_remove_files = set()

    for filepath in remove_files:
        can_remove = True
        for excludedir in args.excludedir:
            if filepath.startswith(excludedir):
                can_remove = False
                break

        if can_remove and os.path.isfile(filepath):
            net_remove_files.add(to_git_path(filepath, args.reporoot))

    print len(net_remove_files),
    print "files can be removed excluding excludedirs and non-existant:"

    net_remove_name = remove_sln_name + "_remove_files.txt"
    with open(net_remove_name, 'w') as f:
        for filepath in sorted(net_remove_files):
            f.write(filepath + '\n')
            print filepath
