#!/usr/bin/env python

# Copyright (c) 2007 by Jonathan Tang, Diffle Inc.
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

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
    """
    return filename.endswith('.js') \
       and filename.find('.pack') == -1 \
       and filename.find('.min') == -1

def list_files(dir):
    """
    Generator for all JavaScript files in the directory, recursively
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
        retval.extend(list_files(path))
    return retval

def read_file(path):
    """
    Opens a file, reads it into a string, closes the file, and returns
    the file text.
    """
    fd = open(path)
    try:
        return ''.join(fd.readlines())
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

##### PARSING #####

def split_tag(section):
    """
    Splits the JSDoc tag text (everything following the @) at the first
    whitespace.  Returns a tuple of (tagname, body).
    """
    splitval = re.split('\s+', section, 1)
    tag, body = len(splitval) > 1 and splitval or (splitval[0], '')
    return tag.strip(), body.strip()
       
def extract_type(param_comment):
    """
    Walks through the tag body and extracts a typename.  Typenames are
    delimited by the first whitespace that's *not* enclosed in matched
    delimiters ([](){}<>).  Returns the typename.

    >>> extract_type('Position()')
    'Position()'

    >>> extract_type('Array<Number> my_var This is the description')
    'Array<Number>'

    >>> extract_type('[DOM] my_var This is the description')
    '[DOM]'

    >>> extract_type('RadioButtons(["foo", "bar"]) my_var The description')
    'RadioButtons(["foo", "bar"])'

    """
    return split_delimited('()[]{}<>', str.isspace, param_comment)[0]

def split_delimited(delimiters, split_by, text):
    """
    Walks the ``text`` and splits it into an array on ``split_by``, being
    careful not to break inside a delimiter pair.  ``delimiters`` should
    be an even-length string with each pair of matching delimiters listed
    together, open first.

    ``split_by`` may be a predicate function instead of a string, in which
    case it should return true on a character to split.

    >>> split_delimited('{}[]', ',', '')
    ['']
    >>> split_delimited('', ',', 'foo,bar')
    ['foo', 'bar']
    >>> split_delimited('[]', ',', 'foo,[bar, baz]')
    ['foo', '[bar, baz]']
    >>> split_delimited('[]{}', ',', '[{foo,[bar, baz]}]')
    ['[{foo,[bar, baz]}]']
    >>> split_delimited('', lambda c: c in '[]{}, ', '[{foo,[bar, baz]}]')
    ['', '', 'foo', '', 'bar', '', 'baz', '', '', '']


    """
    delims = [0] * (len(delimiters) / 2)
    actions = {}
    for i in xrange(0, len(delimiters), 2):
        actions[delimiters[i]] = (i / 2, 1)
        actions[delimiters[i + 1]] = (i / 2, -1)

    split_fn = (lambda c: c == split_by) if isinstance(split_by, str) else split_by
    last = 0
    retval = []

    for i in xrange(len(text)):
        c = text[i]
        if split_fn(c) and not any(delims):
            retval.append(text[last:i])
            last = i + 1
        try:
            which, dir = actions[c]
            delims[which] = delims[which] + dir
        except KeyError:
            pass # Normal character
    retval.append(text[last:])
    return retval

def parse_param(param_comment):
    """
    Parses a param-style tag.  Parameters, options, and data types all count
    as 'param-style' tags: they all have the format "tagname type name [desc]".
    Returns a dict with keys type, name, and desc.
    """
    try:
        type = extract_type(param_comment)
        splitval = re.split('\s+', param_comment[len(type):].strip(), 1)
        name, desc = len(splitval) == 1 and (splitval[0], '') or splitval
        return { 'type': type, 'name': name, 'desc': desc }
    except ValueError:
        warn('Error on ' + param_comment)
        return {}

def replace_params(key, parsed_comment):
    """
    Mutates the passed-in parsed comment so that the specified key's value is
    replaced by the parsed param representation of each tag body.
    """
    parsed_comment[key] = [parse_param(param) for param in parsed_comment[key]]
       
def strip_stars(doc_comment):
    """
    Strips line breaks and leading stars from a doc comment.  
    """
    return re.sub('\n\s*?\*\s*?', '\n', doc_comment)

def coalesce_examples(section_list):
    """
    Generator to walk through the list of comment sections and collect
    all tags that have to do with examples into a single dict.  The 
    @desc, @before, @after, and @result tags all modify a preceding
    @example tag.  Therefore, they need to be combined before the comment
    as a whole is parsed and its tag ordering destroyed by placing them
    in a dict.  This generator matches up those tags with the preceding
    @example tag until it encounters a tag which is not associated with
    an example, then yields the whole example as a single dictionary.
    """
    example_tags = ['desc', 'before', 'after', 'result']
    example = None
    for section in section_list:
        tag, body = split_tag(section)
        if example:
            if tag in example_tags:
                example[1][tag] = body
                continue
            else:
                yield example
                example = None
        if tag == 'example':
            example = (tag, {'example': body})
            for tag in example_tags:
                example[1][tag] = ''
            continue
        else:
            yield (tag, body)
    
FUNCTION_REGEXPS = [
    'function (\w+)',
    '\w+\.prototype\.(\w+)\s*=\s*function',
    '(\w+):\sfunction',
    '\.(\w+)\s*=\s*function'
]

def guess_function_name(first_code_line, parsed_comment):
    """
    Attempts to determine the function name from the first code line
    following the comment.  The patterns recognized are described by
    FUNCTION_REGEXPS.  If a match is successful, this method modifies
    the 'guessed_name' field of the parsed comment with the matched 
    function name.
    """
    parsed_comment['guessed_name'] = ''
    for regexp in FUNCTION_REGEXPS:
        match = re.search(regexp, first_code_line)
        if match:
            parsed_comment['guessed_name'] = match.group(1)

def guess_parameters(first_code_line, parsed_comment):
    """
    Attempts to guess parameters based on the presence of a parenthesized
    group of identifiers.  If successful, sets the 'guessed_param' field of
    the parsed comment to the matching parameters.  
    """
    match = re.search('\(([\w\s,]+)\)', first_code_line)
    parsed_comment['guessed_param'] = \
        [arg.strip() for arg in match.group(1).split(',')] if match else []

def parse_comment(doc_comment):
    """
    Takes comment text and divides it up by attributes.  Each attribute
    becomes a key in the resulting dictionary; if there are multiple
    occurences of an attribute it they're pushed on to a list.  The comment
    text itself is assigned to the attribute "body".
    """
    comment, first_code_line = doc_comment
    sections = strip_stars(comment).split('@')
    list_tags = ['dependency', 'param', 'option', 'author', 'data',
                 'type', 'return', 'returns',
                 'example', 'see', 'before', 'after', 'desc', 'result']
    attributes = { 'body': sections[0].strip() }
    for tag in list_tags:
        attributes[tag] = []
    for tag, body in coalesce_examples(sections[1:]):
        if tag in list_tags:
            attributes[tag].append(body)
        elif body == '':
            attributes[tag] = True
        else:
            attributes[tag] = body
    replace_params('param', attributes)
    replace_params('option', attributes)
    replace_params('data', attributes)

    guess_function_name(first_code_line, attributes)
    guess_parameters(first_code_line, attributes)
    if not attributes.get('name'):
        attributes['name'] = attributes['guessed_name']
    if not attributes['param']:
        attributes['param'] = [{ 'name': name, 'type': '', 'desc': '' } 
                for name in attributes['guessed_param']]
    
    return attributes

def map_doc_to_functions(comments):
    """
    Takes the list of parsed comments and converts it into a dict keyed by
    method name.  The first comment is entered into the special key "module",
    to represent metadata for the module itself.
    """
    function_map = {}
    if not comments:
        return { 'module': {} }

    function_map['module'] = comments[0]

    for comment in comments:
        if 'name' in comment:
            function_map[comment['name']] = comment
    return function_map

def collect_datatypes(module):
    """
    Collects all occurences of the @data tag found throughout all methods in
    the module, and builds a dictionary keyed by the datatype name.
    """
    datatypes = {}
    for method in module.values():
        for datatype in method.get('data', []):
            datatypes[datatype['name']] = datatype
    return datatypes

def get_doc_comments(text):
    """
    Returns a list of all documentation comments in the file text.
    """
    results = re.findall('/\*\*(.*?)\*/\s+(.*?)\n', text, re.DOTALL)
    return results

def parse_comments(comments):
    """
    Takes a list of doc comments and returns a new list of parsed
    versions of those comments.  The comments will have an
    additional field 'sort_order' that reflects their original
    order in the document.
    """
    def decorate_comment(comment_and_index):
        comment, index = comment_and_index
        comment = parse_comment(comment)
        comment['sort_order'] = index
        return comment
    return [decorate_comment(comment) 
            for comment in zip(comments, xrange(len(comments)))]

def parse_jsdoc(file):
    """
    Takes a file path and returns the parsed JSDoc of all comments
    contained in that file, as a list of parsed comments ordered 
    as they appear in the file.
    """
    return parse_comments(get_doc_comments(read_file(file)))

def parse_all_jsdoc(files, prefix=None):
    """
    Returns the parsed JSDoc for all files in the input list, as a dictionary.

    The dictionary may either be keyed by the basename of the file (the default)
    or by having ``prefix`` chopped off the beginning of each full filename.
    You may pass multiple prefixes as a list; the full filename is tested against
    each and chopped if it matches.
    """
    if isinstance(prefix, str):
        prefix = [prefix]
    def key_name(file_name):
        if prefix is None:
            return os.path.basename(file_name)
        for pre in prefix:
            if file_name.startswith(pre):
                return file_name[len(pre):]
        return file_name
    return dict((key_name(file), map_doc_to_functions(parse_jsdoc(file))) 
                for file in files)

##### DEPENDENCIES #####

class CyclicDependency(Exception):
    """
    Exception raised if there is a cyclic dependency.
    """
    def __init__(self, remaining_dependencies):
        self.values = remaining_dependencies

    def __str__(self):
        return ('The following dependencies result in a cycle: '
              + ', '.join(self.values))

class MissingDependency(Exception):
    """
    Exception raised if a file references a dependency that doesn't exist.
    """
    def __init__(self, file, dependency):
        self.file = file
        self.dependency = dependency

    def __str__(self):
        return "Couldn't find dependency %s when processing %s" % \
                (self.dependency, self.file)


def build_dependency_graph(start_nodes, js_doc):
    """
    Builds a graph where nodes are filenames and edges are reverse dependencies
    (so an edge from jquery.js to jquery.dimensions.js indicates that jquery.js
    must be included before jquery.dimensions.js).  The graph is represented
    as a dictionary from filename to (in-degree, edges) pair, for ease of
    topological sorting.  Also returns a list of nodes of degree zero.
    """
    queue = []
    dependencies = {}
    start_sort = []
    def get_dependencies(file):
        entry = js_doc[file]
        return entry['module'].get('dependency') or []
    def add_vertex(file):
        in_degree = len(get_dependencies(file))
        dependencies[file] = [in_degree, []]
        queue.append(file)
        if in_degree == 0:
            start_sort.append(file)
    def add_edge(from_file, to_file):
        dependencies[from_file][1].append(to_file)
    def is_in_graph(file):
        return file in dependencies

    for file in start_nodes:
        add_vertex(file)
    for file in queue:
        for dependency in get_dependencies(file):
            if dependency not in js_doc:
                raise MissingDependency(file, dependency)
            if not is_in_graph(dependency):
                add_vertex(dependency)
            add_edge(dependency, file)
    return dependencies, start_sort 

def topological_sort(dependencies, start_nodes):
    retval = []
    def edges(node): return dependencies[node][1]
    def in_degree(node): return dependencies[node][0]
    def remove_incoming(node): dependencies[node][0] = in_degree(node) - 1
    while start_nodes:
        node = start_nodes.pop()
        retval.append(node)
        for child in edges(node):
            remove_incoming(child)
            if not in_degree(child):
                start_nodes.append(child)
    leftover_nodes = [node for node in dependencies.keys()
                      if in_degree(node) > 0]
    if leftover_nodes:
        raise CyclicDependency(leftover_nodes)
    else:
        return retval

def find_dependencies(start_nodes, js_doc):
    """ 
    Sorts the dependency graph, taking in a list of starting filenames and a 
    hash from JS filename to parsed documentation.  Returns an ordered list 
    of transitive dependencies such that no module appears before its
    dependencies.
    """
    return topological_sort(*build_dependency_graph(start_nodes, js_doc))

##### HTML Formatting #####

FRAMESET_TMPL = """
<html>
<head>
<title>Generated API Documentation</title>
</head>
<frameset cols = "20%, 80%">
<frameset rows = "50%, 50%">
<frame name = "moduleList" src = "module_list.html">
<frame name = "moduleMethods">
</frameset>
<frame name = "moduleDesc" src = "modules.html">
</frameset>
</html>
"""

PAGE_TMPL = """
<html>
<head>
<title>%(title)s</title>
<link rel = "stylesheet" type = "text/css" href = "docstyles.css" />
</head>
<body>
%(content)s
</body>
</html>
"""

MODULE_ENTRY_TMPL = """
<li><a href = "%(url_prefix)smodule/%(module)s.html" target = "moduleDesc"
       onclick = "parent.moduleMethods.location = '%(url_prefix)smethod/%(module)s.html';">
%(module)s</a></li>
"""
MODULE_LIST_TMPL = '<h3 class = "moduleList">%s</h1><ul>%s</ul>'
MODULE_FULL_ENTRY_TMPL = """
<a name = "%(module)s" />
<dt><a href = "module/%(module)s.html">%(module)s</a></dt>
<dd>%(short_desc)s</dd>
"""
MODULE_DESCS_TMPL = '<h1 class = "moduleFullList">Modules</h1><dl>%s</dl>'

MODULE_INFO_TMPL = """
%(body)s
<dl class = "moduleInfo">
<dt>Immediate Dependencies</dt>
<dd><ul class = "dependencies">
%(immediate_dependency_text)s
</ul></dd>
<dt>All Dependencies</dt>
<dd><ul class = "dependencies">
%(all_dependency_text)s
</ul></dd>
</dl>
"""

MODULE_PAGE_TMPL = """
<h1 class = "modulePage">%(module)s</h1>
%(module_info)s
<h2 class = "sectionHeading">Methods</h2>
<dl class = "methodList">
%(methods_short)s
</dl>

<h2 class = "sectionHeading">Method Descriptions</h2>
%(methods_long)s
"""

EXAMPLE_PAGE_TMPL = """
<h1>%(module)s Example #%(num)d</h1>
<div class = "exampleDesc">
%(desc)s
</div>
<div class = "exampleDiv">
%(before)s
%(dependencies)s
<script type = "text/javascript">
%(example)s
</div>
<div class = "example html">
<h2>HTML</h2>
<pre>
%(before)s
</pre>
</div>
<div class = "example js">
<h2>JavaScript</h2>
<pre>
%(example)s
</pre>
</div>
"""

METHOD_LIST_TMPL = """
<li><a href = "%(url_prefix)smodule/%(module)s.html#%(name)s" target = "moduleDesc">%(name)s</a></li>
"""

METHOD_DESC_SHORT_TMPL = """
<dt><a href = "#%(name)s">%(name)s</a> (%(param_short_text)s)</dt>
<dd>%(short_desc)s</dd>
"""

METHOD_DESC_TMPL = """
<div class = "methodBlock" id = "method%(name)s">
<a name = "%(name)s" />
<h3 class = "methodName">%(name)s</h3>
%(body)s
<p class = "returnType">
<strong class = "returnType">Return type:</strong> %(returns)s
</p>
<h4 class = "methodSection">Parameters</h4>
<dl class = "parameters">
%(parameter_text)s
</dl>
<h4 class = "methodSection">Options</h4>
<dl class = "parameters">
%(option_text)s
</dl>
<h4 class = "methodSection">Examples</h4>
%(example_text)s
</div>
"""

EXAMPLE_DESC_TMPL = """
<div class = "exampleBox">
<h5>Example #%(num)s</h5>
%(desc)s
<pre>%(example_text)s </pre>
</div>
"""

EXAMPLE_RESULT_TMPL = """
<strong>%s</strong>: %s
"""

PARAM_DESC_TMPL = '<dt>%(name)s (%(type_text)s)</dt><dd>%(desc)s</dd>'
TOOLTIP_TMPL = '<span class = "%s tooltip" title = "%s">%s</span>'

def build_type_dict(builtin_list):
    """
    Builds a type dictionary from the list of types in BUILT_IN_TYPES.
    The dictionary is keyed by type name, and the values are dicts with
    name, type, & desc fields.
    """
    datatypes = {}
    for name, type, desc in builtin_list:
        datatypes[name] = {'name': name, 'type': type, 'desc': desc}
    return datatypes

BUILT_IN_TYPES = build_type_dict([
    ('Number', '', 'Javascript number, either integer or decimal.'),
    ('String', '', 'Javascript String object.'),
    ('Boolean', 'true|false', 'Javascript boolean.'),
    ('Date', '', 'Javascript date.'),
    ('Array', '', 'Javascript array.'),
    ('Function', '', 'Javascript function object.'),
    ('Object', '', 'Any Javascript object.'),
    ('jQuery', '', 'JQuery object.'),
    ('jQuerySpec', '', 'JQuery specifier string.'),
    ('Element', '', 'DOM element.'),
    ('ID', '', 'ID string of element on page, including leading #.'),
    ('Map', '', 'Javascript object, used as a dictionary.')
])
BUILT_IN_TYPES.update({
    'DOM': BUILT_IN_TYPES['Element'],
    'Integer': BUILT_IN_TYPES['Number'],
    'int': BUILT_IN_TYPES['Number'],
    'string': BUILT_IN_TYPES['String'],
    'Bool': BUILT_IN_TYPES['Boolean']
})

def first_sentence(str):
    """
    Returns the first sentence of a string - everything up to the period,
    or the whole text if there is no period.
    """
    index = str.find('.')
    return index != -1 and str[0:index] or str

def path_ellipses(name):
    return '../' * (name.count('/') + 1)

def link_refs(text, module_name):
    return re.sub(r'([\w_/]+\.js)#(\w+)', (r'<a href = "%(path)smodule/\1.html#\2" '
        r'"onclick = "parent.moduleMethods.location = \'%(path)smethod/\1.html#\2\'">'
        r'\2</a>') % { 'path': path_ellipses(module_name) }, text)

def htmlize_paragraphs(text):
    """
    Converts paragraphs delimited by blank lines into HTML text enclosed
    in <p> tags.
    """
    paragraphs = re.split('(\r?\n)\s*(\r?\n)', text)
    return '\n'.join('<p>%s</p>' % paragraph for paragraph in paragraphs)

def type_text(initial_type, datatypes):
    """
    Turns all typenames it finds into <span> tooltips with the type
    definition, if there is one, or type description if there is not.
    """
    text = initial_type
    for name, type in datatypes.items():
        tooltip = type['type'] and type['type'] or type['desc']
        text = text.replace(name, TOOLTIP_TMPL % ('arg-type', tooltip, name))
    return text

def param_short_text(param, datatypes):
    """
    Returns the text of a parameter, suitable for a quick method description
    (i.e. "typename paramname", with any more elaborate descriptions relegated
    to tooltips.)
    """
    type = type_text(param['type'], datatypes)
    name = TOOLTIP_TMPL % ('arg-name', param['desc'], param['name'])
    return type + ' ' + name

def build_parameter_text(param_list, datatypes):
    """
    Returns the full parameter text, for detailed param documentation.
    """
    if not param_list:
        return 'None'
    for param in param_list:
        param['type_text'] = type_text(param['type'], datatypes)
    return '\n'.join(PARAM_DESC_TMPL % param for param in param_list)

def build_example_text(example_list):
    """
    Builds the HTML text for an example.
    """
    def print_example(index):
        example = example_list[index].copy()

        segments = []
        if example['before']:
            segments.append(cgi.escape(example['before']) + '\n\n')
        segments.append('&lt;script&gt;\n' + cgi.escape(example['example'])
                      + '\n&lt/script&gt;')
        if example['after']:
            segments.append('\n' + EXAMPLE_RESULT_TMPL % 
                                ('After', cgi.escape(example['after'])))
        if example['result']:
            segments.append(EXAMPLE_RESULT_TMPL % ('Result', example['result']))
       
        return EXAMPLE_DESC_TMPL % {
            'num': index + 1,
            'example_text': ''.join(segments),
            'desc': htmlize_paragraphs(example['desc'])
        }
    return '\n'.join(print_example(i) for i in xrange(len(example_list)))

def build_method_list(tmpl, method_list):
    """
    Builds a method list, using either METHOD_DESC_SHORT_TMPL for brief
    method descriptions or METHOD_DESC_TMPL for the full descriptions.
    """
    if not method_list:
        return 'No documented methods'
    return ''.join(tmpl % method for method in method_list)

def extend_methods(module_name, module, datatypes={}):
    """
    Takes the module documentation and returns a new list containing
    its methods, with each method dict being augmented with various
    new keys to support its use as template variables.
    """
    methods = []

    for name, method in module.items():
        if name == 'module':
            continue
        method = method.copy()
        method.update({
            'module': module_name,
            'url_prefix': path_ellipses(module_name),
            'short_desc': first_sentence(method['body']),
            'body': htmlize_paragraphs(link_refs(method['body'], module_name)),
            'parameter_text': build_parameter_text(method['param'], datatypes),
            'option_text': build_parameter_text(method['option'], datatypes),
            'example_text': build_example_text(method['example']),
            'param_short_text': 
                ', '.join(param_short_text(param, datatypes) for param in method['param'])
        })

        method['returns'].extend(method['return'])
        method['returns'].extend(method['type'])
        method['returns'] = type_text('|'.join(method['returns']), datatypes)

        methods.append(method)

    methods.sort(key=lambda method: method['sort_order'])
    return methods
    
def build_module_page(name, module, all_dependencies=[]):
    """
    Builds the full documentation page for a single module.
    """
    datatypes = {}
    datatypes.update(BUILT_IN_TYPES)
    datatypes.update(collect_datatypes(module))
    
    methods = extend_methods(name, module, datatypes)
    module_info = {
        'module_info': '',
        'module': name,
        'organization': '',
        'version': '',
        'methods_short': 
            build_method_list(METHOD_DESC_SHORT_TMPL, methods),
        'methods_long': 
            build_method_list(METHOD_DESC_TMPL, methods)
    } 

    url_prefix = path_ellipses(name)
    if 'module' in module:
        module_info.update(module['module'])
        module_info.update({
            'author': ', '.join(module_info.get('author', [])),
            'short_desc': first_sentence(module_info.get('body', 'No description provided')),
            'immediate_dependency_text': 
                build_module_list(module_info.get('dependency', []), url_prefix),
            'all_dependency_text': 
                build_module_list(all_dependencies, url_prefix),
            'body': htmlize_paragraphs(link_refs(
                module_info.get('body', 'No module documentation.'), name))
        })
        module_info['module_info'] = MODULE_INFO_TMPL % module_info

    return MODULE_PAGE_TMPL % module_info

def build_module_index(js_doc):
    """
    Builds the module index that appears in the top-left frame.
    """
    return MODULE_LIST_TMPL % ('Modules', build_module_list(js_doc.keys()))
    
def build_method_index(module_name, js_doc):
    """
    Builds the method index that appears in the bottom-left frame.
    """
    methods = extend_methods(module_name, js_doc[module_name])
    return MODULE_LIST_TMPL % ('Methods', 
        build_method_list(METHOD_LIST_TMPL, methods))

def build_module_list(doc_keys, url_prefix=''):
    """
    Builds the module list for the dependency lists and indexes.
    """
    module_names = doc_keys[:]
    module_names.sort()
    return '\n'.join(MODULE_ENTRY_TMPL % {'module': name, 'url_prefix': url_prefix}
                     for name in module_names)

def build_module_descs(modules):
    """
    Builds the initial page for the main frame, with full descriptions
    for each module.
    """
    def fill_template(item):
        name, module = item
        try:
            docs = htmlize_paragraphs(link_refs(module['module']['body'], name))
        except KeyError:
            docs = 'No documentation available.'

        return MODULE_FULL_ENTRY_TMPL % {
            'module': name, 
            'short_desc': first_sentence(docs)
        }
    return MODULE_DESCS_TMPL % ''.join(fill_template(item) for item in modules)
    
def build_example_page(num, module_name, dependency_files, example):
    """
    Builds an example demo page.  Currently mostly untested, and disabled in
    the command-line script.
    """
    script_tag = '<script type = "text/javascript" src = "%s"></script>'
    tmpl_vars = example.copy()
    tmpl_vars.update({
        'num': num,
        'module': module_name,
        'dependencies': '\n'.join(script_tag % file for file in dependency_files)
    })
    return EXAMPLE_PAGE_TMPL % tmpl_vars
    
def build_page(title, content):
    """
    Sets the title and content into the full HTML page template.
    """
    return PAGE_TMPL % { 'title': title, 'content': content }

def save_docs(js_doc, all_files, dir):
    """
    Builds the full documentation tree.
    """
    def save_to(filename, text):
        full_path = os.path.join(dir, filename)
        dir_name = os.path.dirname(full_path)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        save_file(full_path, text)

    save_to('index.html', FRAMESET_TMPL)
    save_to('module_list.html', 
            build_page('Module Index', build_module_index(js_doc)))
    save_to('modules.html', 
            build_page('Modules', build_module_descs(js_doc.items())))

    file_map = get_file_map(all_files)

    for module_name in js_doc.keys():
        module = js_doc[module_name]
        dependencies = find_dependencies([module_name], js_doc)
        save_to(os.path.join('module', module_name + '.html'), 
                build_page(module_name, 
                           build_module_page(module_name, module, dependencies)))
        save_to(os.path.join('method', module_name + '.html'),
                build_page('Methods for ' + module_name, 
                           build_method_index(module_name, js_doc)))
        examples = []
        for method in module.values():
            examples.extend(method.get('example', []))
        include = [js_doc[name] for name in dependencies] 
        for i in xrange(len(examples)):
            # Intentionally not saving yet - example pages aren't working yet
            build_page('Example %d for %s' % (i, module_name),
                   build_example_page(i, module_name, include, examples[i]))

##### COMMANDS #####

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

def get_file_map(all_files):
    """
    Turns the list of file paths into a dict mapping the file name to the full path.
    """
    return dict((os.path.basename(file), file) for file in all_files)

def json_format(output):
    """
    Formats results as a JSON string.
    """
    import simplejson
    return simplejson.write(output)

class ArgNotFound:

    def __init__(self, missing_arg, possibilities):
        self.arg = missing_arg
        self.possibilities = possibilities

    def __str__(self):
        return "Argument '%s' could not be found.  Possible values:\n%s" % (
            self.arg, '\n'.join(self.possibilities))

def depend_data(args, js_paths, all_files):
    """
    Takes in the command-line args and list of files to search and returns a
    list of all dependencies that the specified JS files have, such that no
    file appears before its dependencies.
    """
    js_doc = parse_all_jsdoc(all_files, js_paths)
    for arg in args[1:]:
        if arg not in js_doc:
            raise ArgNotFound(arg, js_doc.keys())
    return find_dependencies(args[1:], js_doc)

def depend_format(args, data, all_files, output_file):
    """
    Formats the list of dependencies for command-line output, i.e. full path
    names with one on each line.
    """
    file_map = get_file_map(all_files)
    return '\n'.join(file_map[script] for script in data)

def doc_data(args, js_paths, all_files):
    """
    Documents a single plugin file and returns the parsed module contents.

    Information does not include all dependencies (though it does include
    immediate dependencies) because calculating that would require loading
    every JS file on the source tree.
    """
    file_map = get_file_map(all_files)
    try:
        return map_doc_to_functions(parse_jsdoc(file_map[args[1]]))
    except KeyError:
        raise ArgNotFound(args[1], file_map.keys())

def doc_format(args, data, all_files, output_file):
    """
    Formats the parsed documentation of a single module as HTML.
    """
    return build_module_page(args[1], data)

def build_data(args, js_paths, all_files):
    """
    Returns the parsed JSDoc for all modules.
    """
    return parse_all_jsdoc(all_files, js_paths)

def build_format(args, data, all_files, output_file):
    """
    Saves the full output from all modules to the apidocs directory.
    Returns an empty string.
    """
    if not output_file:
        output_file = 'apidocs'
    save_docs(data, all_files, output_file)
    return ''

def main():
    """
    Main command-line invocation.
    """
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'p:io:j', [
            'jspath=', 'input', 'output=', 'json'])
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
