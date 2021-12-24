#!/usr/bin/env python2.7

import argparse
import os.path
from tokenize import generate_tokens


class tokenizer_t(object):
    def __init__(self, special_char_tokens):
        self.special_char_tokens = special_char_tokens

    def tokenize(self, full_text):
        tokens = []
        token = ""
        inside_single_quote = False
        inside_double_quote = False
        for c in full_text:
            if c == "'":
                if inside_single_quote:
                    inside_single_quote = False
                else:
                    inside_single_quote = True
                token += c
            elif c == '"':
                if inside_double_quote:
                    inside_double_quote = False
                else:
                    inside_double_quote = True
                token += c
            elif c in self.special_char_tokens:
                if token:
                    tokens.append (token)
                token = ""
                tokens.append (c)
            elif c.isspace():
                if inside_single_quote or inside_double_quote:
                    token += c
                else:
                    if token:
                        tokens.append (token)
                    token = ""                
            else:
                token += c
                    
        return tokens


def init_options():
    arg_parser = argparse.ArgumentParser(
        description="Parse objects in gdb print format and convert to cpp code.",
        conflict_handler='resolve',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    arg_parser.add_argument(
        "-i",
        type=str,
        help="full path to the input file containing objects in gdb print format.",
    )

    arg_parser.add_argument(
        "-o",
        type=str,
        help="full path to the output file of cpp code.",
    )

    return arg_parser.parse_args()


def pick_best_value (values):
    if (len(values) > 1) and (values[1][0] == "'"):
        return values[1]
    else:
        if (values[0][0] == '"'):
            idx = values[0].find(r'\000')
            if (idx != 1):
                values[0] = values[0][0:idx] + '"'
        return values[0]

def serialize_name_value (name_stack, values, outf):
    string_is_char_array = True
    if name_stack and values:
        lhs = name_stack[0]
        for name in name_stack[1:]:
            lhs += "."
            lhs += name
        value = pick_best_value(values)
        if value[0] == '"' and string_is_char_array:
            output = "strcpy (" + lhs + ", " + value + ");"
        else:
            output = lhs + " = " + value + ";"
        print (output)


def serialize (tokens, outf):
    state = "NEXT"
    name_stack = []
    values = []
    for token in tokens:
        if (state == "NEXT"):
            name_stack.append (token)
            state = "NAME"
        elif (state == "NAME"):
            if token == "=":
                state = "="
            # some fields between commas need ignore like
            # , '\000' <repeats 12 times>, "\220", 
            elif token == ",":
                name_stack.pop()
                state = "NEXT"
            elif token == "}":
                name_stack.pop()
                state = "VALUE"
            else:
                pass
        elif (state == "="):
            if token == "{":
                state = "NEXT"
            else:
                values.append (token)
                state = "VALUE"
        elif (state == "VALUE"):
            if token == ",":
                serialize_name_value (name_stack, values, outf)
                values.clear()
                name_stack.pop()
                state = "NEXT"
            elif token == "}":
                serialize_name_value (name_stack, values, outf)
                values.clear()
                name_stack.pop()
                # state remains at "VALUE"
            else:
                values.append (token)
                # state remains at "VALUE"


if __name__ == "__main__":

    args = init_options()

    infile = str(args.i)
    infile = infile.replace('/', '\\')
    if not os.path.isfile(infile):
        print ("specified file does not exist: " , infile)
        exit(0)

    outfile = str(args.o)
    outfile = outfile.replace('/', '\\')

    with open(infile, 'r') as inf, open(outfile, 'w') as outf :
        # read the entire file as one string
        objects = inf.read().replace('\n', ' ')
        
        tokenizer = tokenizer_t( ('{', '=', '}', ',') )
        
        tokens = tokenizer.tokenize (objects)
        
        # print (tokens)
        
        serialize (tokens, outf)

        