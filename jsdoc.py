#!/usr/bin/env python

"""
Python library & command-line tool for performing a variety of build
& deployment tasks of jQuery plugins.  

This offers the following features:

* List all dependencies of a plugin or plugins
* Check for method name conflicts among a set of plugins
* Extract metadata from doc comments
* Generate documentation for a set of files.

It depends on the existence of certain @tags in the documentation.  These are:

* @module: Display name of the module
* @author: Author's name
* @version: Version number
* @organization: Name of sponsoring organization, if any
* @license: License type (BSD/MIT/GPL/LGPL/Artistic/etc.)
* @dependency: Filename of parent plugin.  Multiple tags allowed
"""

import os
import re
import sys
import getopt
import cgi

##### INPUT/OUTPUT #####

def warn(format, *args):
    sys.stderr.write(format % args)

def is_js_file(filename):
    """
    Returns true if the filename ends in .js and is not a packed or
    minified file (no '.pack' or '.min' in the filename)

    >>> is_js_file('jquery.min.js')
    False
    >>> is_js_file('foo.json')
    False
    >>> is_js_file('ui.combobox.js')
    True

    """
    return filename.endswith('.js') \
       and not '.pack' in filename \
       and not '.min' in filename

def list_js_files(dir):
    """
    Generator for all JavaScript files in the directory, recursively

    >>> list_js_files('examples').next()
    'examples/module.js'

    """
    for dirpath, dirnames, filenames in os.walk(dir):
        for filename in filenames:
            if is_js_file(filename):
                yield os.path.join(dirpath, filename)

def get_path_list(opts):
    """
    Returns a list of all root paths where JS files can be found, given the
    command line options for this script.
    """
    paths = []
    for opt, arg in opts:
        if opt in ('-i', '--input'):
            return [line.strip() for line in sys.stdin.readlines()]
        elif opt in ('-p', '--jspath'):
            paths.append(arg)
    return paths or [os.getcwd()]

def get_file_list(paths):
    """
    Returns a list of all JS files, given the root paths.
    """
    retval = []
    for path in paths:
        retval.extend(list_js_files(path))
    return retval

def read_file(path):
    """
    Opens a file, reads it into a string, closes the file, and returns
    the file text.
    """
    fd = open(path)
    try:
        return fd.read()
    finally:
        fd.close()

def save_file(path, text):
    """
    Saves a string to a file
    """
    fd = open(path, 'w')
    try:
        fd.write(text)
    finally:
        fd.close()

##### Parsing utilities #####

def split_delimited(delimiters, split_by, text):
    """
    Generator that walks the ``text`` and splits it into an array on
    ``split_by``, being careful not to break inside a delimiter pair.
    ``delimiters`` should be an even-length string with each pair of matching
    delimiters listed together, open first.

    ``split_by`` may be a predicate function instead of a string, in which
    case it should return true on a character to split.

    >>> list(split_delimited('{}[]', ',', ''))
    ['']
    >>> list(split_delimited('', ',', 'foo,bar'))
    ['foo', 'bar']
    >>> list(split_delimited('[]', ',', 'foo,[bar, baz]'))
    ['foo', '[bar, baz]']
    >>> list(split_delimited('[]{}', ',', '[{foo,[bar, baz]}]'))
    ['[{foo,[bar, baz]}]']
    >>> list(split_delimited('', lambda c: c in '[]{}, ', '[{foo,[bar, baz]}]'))
    ['', '', 'foo', '', 'bar', '', 'baz', '', '', '']

    """
    delims = [0] * (len(delimiters) / 2)
    actions = {}
    for i in xrange(0, len(delimiters), 2):
        actions[delimiters[i]] = (i / 2, 1)
        actions[delimiters[i + 1]] = (i / 2, -1)

    if isinstance(split_by, str):
        def split_fn(c): return c == split_by
    else:
        split_fn = split_by
    last = 0

    for i in xrange(len(text)):
        c = text[i]
        if split_fn(c) and not any(delims):
            yield text[last:i]
            last = i + 1
        try:
            which, dir = actions[c]
            delims[which] = delims[which] + dir
        except KeyError:
            pass # Normal character
    yield text[last:]

def get_doc_comments(text):
    r"""
    Returns a list of all documentation comments in the file text.  Each
    comment is a pair, with the first element being the comment text and
    the second element being the line after it, which may be needed to
    guess function & arguments.

    >>> get_doc_comments(read_file('examples/module.js'))[0][0][:40]
    '/**\n * This is the module documentation.'
    >>> get_doc_comments(read_file('examples/module.js'))[1][0][7:50]
    'This is documentation for the first method.'
    >>> get_doc_comments(read_file('examples/module.js'))[1][1]
    'function the_first_function(arg1, arg2) '
    >>> get_doc_comments(read_file('examples/module.js'))[2][0]
    '/** This is the documentation for the second function. */'


    """
    def make_pair(match):
        comment = match.group()
        try:
            end = text.find('\n', match.end(0)) + 1
            if '@class' not in comment:
                next_line = split_delimited('()', '\n', text[end:]).next()
            else:
                next_line = text[end:text.find('\n', end)]
        except StopIteration:
            next_line = ''
        return (comment, next_line)
    return [make_pair(match) for match in re.finditer('/\*\*(.*?)\*/', 
            text, re.DOTALL)]


def usage(command_name):
    print """
Usage: %(name)s <command> [options]

Available commands:

  depend [start files]: Generate a list of all dependencies of the specified
                        start files.
  doc [filename]: Writes HTML documentation for specified file to STDOUT
  build: Build HTML documentation for all files on the JSPath

By default, this tool recursively searches the current directory for .js files
to build up its dependency database.  This can be changed with the --input or
--jspath options (see below).

Available options:

  -p, --jspath  Directory to search for JS libraries (multiple allowed)
  -i, --input   Read available JS files from STDIN 
  -o, --output  Output to file (or directory, for build) instead of STDOUT
  -j, --json    Write output in JSON format (requires python-json module)
  -h, --help    Print usage information and exit
  -t, --test    Run PyJSDoc unit tests

Cookbook of common tasks:

  Find dependencies of the Dimensions plugin in the jQuery CVS repository, 
  filtering out packed files from the search path:

  $ find trunk/plugins -name "*.js" | grep -v pack | %(name)s -i depend jquery.dimensions.js

  Concatenate dependent plugins into a single file for web page:

  $ %(name)s depend myplugin1.js myplugin2.js | xargs cat > scripts.js

  Read documentation information for form plugin (including full dependencies),
  and include on a PHP web page using the PHP Services_JSON module:

  <?php
  $json = new Services_JSON();
  $jsdoc = $json->decode(`jsdoc doc jquery.form.js -j -p trunk/plugins`);
  ?>

  Build documentation for all plugins on your system:

  $ %(name)s build -o /var/www/htdocs/jqdocs
""" % {'name': os.path.basename(command_name) }


def main():
    """
    Main command-line invocation.
    """

    if '--test' in sys.argv:
        import doctest
        doctest.testmod()
        sys.exit(0)

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'p:io:jt', [
            'jspath=', 'input', 'output=', 'json', 'test'])
    except getopt.GetoptError:
        usage(sys.argv[0])
        sys.exit(2)

    js_paths = get_path_list(opts)
    js_files = get_file_list(js_paths)

    try:
       data_fn = globals()[args[0] + '_data']
       format_fn = globals()[args[0] + '_format']
    except (KeyError, IndexError):
        usage(sys.argv[0])
        sys.exit(2)

    show_json = False
    output_file = False
    for opt, arg in opts:
        if opt in ['-j', '--json']:
            show_json = True
        elif opt in ['-o', '--output']:
            output_file = arg

    def add_trailing_slash(path):
        return path + ('/' if not path.endswith('/') else '')
    js_paths = map(add_trailing_slash, js_paths)

    try:
        result = data_fn(args, js_paths, js_files)
        output = show_json and json_format(result) or \
                 format_fn(args, result, js_files, output_file)
        if output_file and format_fn != build_format:
            save_file(output_file, output)
        else:
            print output
    except ArgNotFound, e:
        print e

if __name__ == '__main__':
    main()
