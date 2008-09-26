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


    >>> list(split_delimited('{}[]', ',', ''))
    ['']
    >>> list(split_delimited('', ',', 'foo,bar'))
    ['foo', 'bar']
    >>> list(split_delimited('[]', ',', 'foo,[bar, baz]'))
    ['foo', '[bar, baz]']
    >>> list(split_delimited('{}', ' ', '{Type Name} name Desc'))
    ['{Type Name}', 'name', 'Desc']
    >>> list(split_delimited('[]{}', ',', '[{foo,[bar, baz]}]'))
    ['[{foo,[bar, baz]}]']

    Two adjacent delimiters result in a zero-length string between them:

    >>> list(split_delimited('{}', ' ', '{Type Name}  Desc'))
    ['{Type Name}', '', 'Desc']

    ``split_by`` may be a predicate function instead of a string, in which
    case it should return true on a character to split.

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

def strip_stars(doc_comment):
    r"""
    Strips leading stars from a doc comment.  

    >>> strip_stars('/** This is a comment. */')
    'This is a comment.'
    >>> strip_stars('/**\n * This is a\n * multiline comment. */')
    'This is a\n multiline comment.'
    >>> strip_stars('/** \n\t * This is a\n\t * multiline comment. \n*/')
    'This is a\n multiline comment.'


    """
    return re.sub('\n\s*?\*\s*?', '\n', doc_comment[3:-2]).strip()

def split_tag(section):
    """
    Splits the JSDoc tag text (everything following the @) at the first
    whitespace.  Returns a tuple of (tagname, body).
    """
    splitval = re.split('\s+', section, 1)
    tag, body = len(splitval) > 1 and splitval or (splitval[0], '')
    return tag.strip(), body.strip()

FUNCTION_REGEXPS = [
    'function (\w+)',
    '(\w+):\sfunction',
    '\.(\w+)\s*=\s*function',
]

def guess_function_name(next_line, regexps=FUNCTION_REGEXPS):
    """
    Attempts to determine the function name from the first code line
    following the comment.  The patterns recognized are described by
    `regexps`, which defaults to FUNCTION_REGEXPS.  If a match is successful, 
    returns the function name.  Otherwise, returns None.
    """
    for regexp in regexps:
        match = re.search(regexp, next_line)
        if match:
            return match.group(1)
    return None

def guess_parameters(next_line):
    """
    Attempts to guess parameters based on the presence of a parenthesized
    group of identifiers.  If successful, returns a list of parameter names;
    otherwise, returns None.
    """
    match = re.search('\(([\w\s,]+)\)', next_line)
    if match:
        return [arg.strip() for arg in match.group(1).split(',')]
    else:
        return None

def parse_comment(doc_comment):
    r"""
    Splits the raw comment text into a dictionary of tags.  The main comment
    body is included as 'doc'.

    >>> comment = get_doc_comments(read_file('examples/module.js'))[4][0]
    >>> parse_comment(strip_stars(comment))['doc']
    'This is the documentation for the fourth function.\n\n Since the function being documented is itself generated from another\n function, its name needs to be specified explicitly. using the @function tag'
    >>> parse_comment(strip_stars(comment))['function']
    'not_auto_discovered'

    If there are multiple tags with the same name, they're included as a list:

    >>> parse_comment(strip_stars(comment))['param']
    ['{String} arg1 The first argument.', '{Int} arg2 The second argument.']

    """
    sections = re.split('\n\s*@', doc_comment)
    tags = { 'doc': sections[0].strip() }
    for section in sections[1:]:
        tag, body = split_tag(section)
        if tag in tags:
            existing = tags[tag]
            try:
                existing.append(body)
            except AttributeError:
                tags[tag] = [existing, body]
        else:
            tags[tag] = body
    return tags

def make_comment(next_line, parsed_comment):
    """
    Creates the appropriate Doc class for a next_line, parsed_comment pair.
    """
    if 'fileoverview' in parsed_comment:
        parsed_comment.name = 'file_overview'
        return parsed_comment

    function_name = parsed_comment.get('function') or \
                    guess_function_name(next_line, parsed_comment)
    if function_name:
        return 

#### Classes #####

class FileDoc(object):
    """
    Represents documentaion for an entire file.  The constructor takes the
    source text for file, parses it, then provides a class wrapper around
    the parsed text.
    """

    def __init__(self, file_name, file_text):
        self.name = file_name
        self.order = []
        self.comments = {}
        for comment in get_doc_comments(file_text):
            parsed_comment = make_comment(parse_comment(strip_stars(comment)))
            self.order.append(parse_comment.name)
            self.comments[parse_comment.name] = parse_comment

    def __str__(self):
        return "Docs for file " + self.name

    def __iter__(self):
        """
        Returns all comments from the file, in the order they appear.
        """
        return (self.comments[name] for name in self.order)

    def __getitem__(self, name):
        """
        Returns the specific method/function/class from the file.
        """
        return self.comments[name]

    def _module_prop(self, name, default=''):
        return self.comments['file_overview'].get(prop, default)

    @property
    def doc(self):
        return self._module_prop('body')

    @property
    def author(self):
        return self._module_prop('author')

    @property
    def version(self):
        return self._module_prop('version')

    @property
    def dependencies(self):
        val = self._module_prop('dependency', [])
        if isinstance(val, list):
            return val
        else:
            return [val]

    def _filtered_iter(self, pred):
        return (self.comments[name] for name in self.order 
                if pred(self.comments[name]))

    @property
    def functions(self):
        """
        Returns all standalone functions in the file, in textual order.
        """
        def is_function(comment):
            return isinstance(comment, FunctionDoc) \
                    and comment.member_of is None
        return self._filtered_iter(is_function)

    @property
    def methods(self):
        """
        Returns all member functions in the file, in textual order.
        """
        def is_method(comment):
            return isinstance(comment, FunctionDoc) \
                    and comment.member_of is not None
        return self._filtered_iter(is_method)

    @property
    def classes(self):
        return self._filtered_iter(lambda c: isinstance(c, ClassDoc))

class CommentDoc(object):
    """
    Base class for all classes that represent a parsed comment of some sort.
    """
    def __init__(self, parsed_comment):
        self.parsed = parse_comment

    def __str__(self):
        return "Docs for function " + self.name

    def __getitem__(self, tag_name):
        return self.get(tag_name)

    def get(self, tag_name, default=''):
        """
        Returns the value of a particular tag, or None if that tag doesn't
        exist.  Use 'doc' for the comment body itself.
        """
        return self.parsed.get(tag_name, default)

    def get_as_list(self, tag_name):
        """
        Returns the value of a tag, making sure that it's a list.  Absent
        tags are returned as an empty-list; single tags are returned as a
        one-element list.
        """
        val = self.get(tag_name, [])
        if isinstance(val, list):
            return val
        else:
            return [val]

def FunctionDoc(CommentDoc):
    """
    Represents documentation for a single function or method.  Takes a parsed
    comment and provides accessors for accessing the various fields.
    """
    
    @property
    def name(self): 
        return self.get('function')

    @property
    def doc(self):
        return self.get('doc')

    @property
    def params(self):
        return [ParamDoc(text) for text 
                in self.get_as_list('param') + self.get_as_list('argument')]

    @property
    def options(self):
        return [ParamDoc(text) for text in self.get_as_list('option')]

    @property
    def return_val(self):
        ret = self.get('return') or self.get('returns')
        type = self.get('type')
        if '{' in ret and '}' in ret:
            return ParamDoc(ret)
        if ret and type:
            return ParamDoc('{%s} %s' % (type, ret))
        return ParamDoc(ret)

    @property
    def throws(self):
        def make_param(text):
            if not ('{' in text and '}' in text):
                # Handle old JSDoc format
                text = '{%s} %s' % text.split(maxsplit=1)
            return ParamDoc(text)
        return [make_param(text) for text in 
                self.get_as_list('throws') + self.get_as_list('exception')]

    @property
    def private(self):
        return 'private' in self.parsed

    @property
    def member_of(self):
        return self.get('member')

class ClassDoc(CommentDoc):
    """
    Represents documentation for a single class.
    """
    # The 'methods' attribute should be set externally after creation to a
    # list of methods

    @property
    def name(self):
        return self.get('class') or self.get('constructor')

    @property
    def superclass(self):
        return self.get('base')

class ParamDoc(object):
    """
    Represents a parameter, option, or parameter-like object, basically
    anything that has a name, a type, and a description, separated by spaces.
    This is also used for return types and exceptions, which use an empty
    string for the name.

    >>> param = ParamDoc('{Array<DOM>} elems The elements to act upon')
    >>> param.name
    'elems'
    >>> param.doc
    'The elements to act upon'
    >>> param.type
    'Array<DOM>'

    You can also omit the type: if the first element is not surrounded by
    curly braces, it's assumed to be the name instead:

    >>> param2 = ParamDoc('param1 The first param')
    >>> param2.type
    ''
    >>> param2.name
    'param1'
    >>> param2.doc
    'The first param'

    """
    def __init__(self, text):
        parsed = list(split_delimited('{}', ' ', text))
        if parsed[0].startswith('{') and parsed[0].endswith('}'):
            self.type = parsed[0][1:-1]
            self.name = parsed[1]
            self.doc = ' '.join(parsed[2:])
        else:
            self.type = ''
            self.name = parsed[0]
            self.doc = ' '.join(parsed[1:])

##### Command-line functions #####

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
