#!/usr/bin/env python
"""
Python library & command-line tool for documentation and dependency analysis
of JavaScript files.

Some of the features this offers:

List all dependencies of a file or files:

>>> CodeBaseDoc(['examples'])['subclass.js'].module.all_dependencies
['module.js', 'module_closure.js', 'class.js', 'subclass.js']

Programmatically access properties of the documentation:

>>> CodeBaseDoc(['examples'])['subclass.js']['public_method'].doc
'A public method.'
>>> CodeBaseDoc(['examples'])['subclass.js']['public_method'].is_private
False

Generate documentation for a set of files:

>>> CodeBaseDoc(['examples']).save_docs(None, 'js_apidocs')

Tag reference is similar to JSDoc: http://jsdoc.sourceforge.net/#tagref.  See usage() for command line options.

"""

import os, re, sys, getopt, cgi

try:
    import cjson
    encode_json = lambda val: cjson.encode(val)
except ImportError:
    try:
        import simplejson
        encode_json = lambda val: simplejson.dumps(val)
    except ImportError:
        def encode_json(val):
            raise ImportError(
                    "Either cjson or simplejson is required for JSON encoding")

##### INPUT/OUTPUT #####

def warn(format, *args):
    """
    Print out a warning on STDERR.
    """
    sys.stderr.write(format % args + '\n')

def flatten(iter_of_iters):
    """
    Flatten an iterator of iterators into a single, long iterator, exhausting
    each subiterator in turn.

    >>> flatten([[1, 2], [3, 4]])
    [1, 2, 3, 4]

    """
    retval = []
    for val in iter_of_iters:
        retval.extend(val)
    return retval

def any(iter):
    """ For < Python2.5 compatibility. """
    for elem in iter:
        if elem:
            return True
    return False

def is_js_file(filename):
    """
    Return true if the filename ends in .js and is not a packed or
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

def trim_js_ext(filename):
    """
    If `filename` ends with .js, trims the extension off.

    >>> trim_js_ext('foo.js')
    'foo'
    >>> trim_js_ext('something_else.html')
    'something_else.html'

    """
    if filename.endswith('.js'):
        return filename[:-3]
    else:
        return filename

def list_js_files(dir):
    """
    Generator for all JavaScript files in the directory, recursively

    >>> 'examples/module.js' in list(list_js_files('examples'))
    True

    """
    for dirpath, dirnames, filenames in os.walk(dir):
        for filename in filenames:
            if is_js_file(filename):
                yield os.path.join(dirpath, filename)

def get_file_list(paths):
    """
    Return a list of all JS files, given the root paths.
    """
    return flatten(list_js_files(path) for path in paths)

def read_file(path):
    """
    Open a file, reads it into a string, closes the file, and returns
    the file text.
    """
    fd = open(path)
    try:
        return fd.read()
    finally:
        fd.close()

def save_file(path, text):
    """
    Save a string to a file.  If the containing directory(ies) doesn't exist,
    this creates it.
    """
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)

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
    Return a list of all documentation comments in the file text.  Each
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
    Strip leading stars from a doc comment.  

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
    Split the JSDoc tag text (everything following the @) at the first
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
    Attempt to determine the function name from the first code line
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
    Attempt to guess parameters based on the presence of a parenthesized
    group of identifiers.  If successful, returns a list of parameter names;
    otherwise, returns None.
    """
    match = re.search('\(([\w\s,]+)\)', next_line)
    if match:
        return [arg.strip() for arg in match.group(1).split(',')]
    else:
        return None

def parse_comment(doc_comment, next_line):
    r"""
    Split the raw comment text into a dictionary of tags.  The main comment
    body is included as 'doc'.

    >>> comment = get_doc_comments(read_file('examples/module.js'))[4][0]
    >>> parse_comment(strip_stars(comment), '')['doc']
    'This is the documentation for the fourth function.\n\n Since the function being documented is itself generated from another\n function, its name needs to be specified explicitly. using the @function tag'
    >>> parse_comment(strip_stars(comment), '')['function']
    'not_auto_discovered'

    If there are multiple tags with the same name, they're included as a list:

    >>> parse_comment(strip_stars(comment), '')['param']
    ['{String} arg1 The first argument.', '{Int} arg2 The second argument.']

    """
    sections = re.split('\n\s*@', doc_comment)
    tags = { 
        'doc': sections[0].strip(),
        'guessed_function': guess_function_name(next_line),
        'guessed_params': guess_parameters(next_line)
    }
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

def parse_comments_for_file(filename):
    """
    Return a list of all parsed comments in a file.  Mostly for testing &
    interactive use.
    """
    return [parse_comment(strip_stars(comment), next_line)
            for comment, next_line in get_doc_comments(read_file(filename))]


#### Classes #####

class CodeBaseDoc(dict):
    """
    Represents the documentation for an entire codebase.

    This takes a list of root paths.  The resulting object acts like a
    dictionary of FileDoc objects, keyed by the filename of the file (relative
    to the source root).
    
    >>> CodeBaseDoc(['examples'])['class.js'].name
    'class.js'

    It also handles dependency & subclass analysis, setting the appropriate
    fields on the contained objects.  Note that the keys (after prefix
    chopping) should match the names declared in @dependency or @see tags;
    otherwise, you may get MissingDependencyErrors.

    """

    def __init__(self, root_paths, include_private=False):
        """
        Create a new `CodeBaseDoc`.  `root_paths` is a list of directories
        where JavaScript files can be found.  @see and @dependency tags
        are relative to these paths.

        By default, private methods are not included.  Pass True to
        `include_private` to include them.
        """
        self.include_private = include_private
        self._populate_files(root_paths, root_paths)
        self._build_dependencies()
        self._build_superclass_lists()

    def _populate_files(self, root_paths, prefix):
        files = get_file_list(root_paths)
        def key_name(file_name):
            if prefix is None:
                return os.path.basename(file_name)
            for pre in prefix:
                if not pre.endswith('/'):
                    pre = pre + '/'
                if file_name.startswith(pre):
                    return file_name[len(pre):]
            return file_name

        for file in files:
            name = key_name(file)
            self[name] = FileDoc(name, read_file(file))

    def _build_dependencies(self):
        """
        >>> CodeBaseDoc(['examples'])['subclass.js'].module.all_dependencies
        ['module.js', 'module_closure.js', 'class.js', 'subclass.js']
        """
        for module in self.values():
            module.set_all_dependencies(find_dependencies([module.name], self))

    def _build_superclass_lists(self):
        """
        >>> CodeBaseDoc(['examples']).all_classes['MySubClass'].all_superclasses[0].name
        'MyClass'
        """
        cls_dict = self.all_classes
        for cls in cls_dict.values():
            cls.all_superclasses = []
            superclass = cls.superclass
            try:
                while superclass:
                    superclass_obj = cls_dict[superclass]
                    cls.all_superclasses.append(superclass_obj)
                    superclass = superclass_obj.superclass
            except KeyError:
                print "Missing superclass: " + superclass

    def _module_index(self, attr):
        return dict((obj.name, obj) for module in self.values()
                                    for obj in getattr(module, attr))

    @property
    def all_functions(self):
        """
        Returns a dict of all functions in all modules of the codebase,
        keyed by their name.
        """
        return self._module_index('functions')

    @property
    def all_methods(self):
        """
        Returns a dict of all methods in all modules.
        """
        return self._module_index('methods')

    @property
    def all_classes(self):
        """
        Returns a dict of all classes in all modules.
        """
        return self._module_index('classes')

    def translate_ref_to_url(self, ref, in_comment=None):
        """
        Translates an @see or @link reference to a URL.  If the ref is of the 
        form #methodName, it looks for a method of that name on the class
        `in_comment` or parent class of method `in_comment`.  In this case, it
        returns a local hash URL, since the method is guaranteed to be on the
        same page:

        >>> doc = CodeBaseDoc(['examples'])
        >>> doc.translate_ref_to_url('#public_method', doc.all_methods['private_method'])
        '#public_method'
        >>> doc.translate_ref_to_url('#public_method', doc.all_classes['MySubClass'])
        '#public_method'

        If it doesn't find it there, it looks for a global function:

        >>> doc.translate_ref_to_url('#make_class')
        'module_closure.html#make_class'

        A reference of the form ClassName#method_name looks up a specific method:

        >>> doc.translate_ref_to_url('MyClass#first_method')
        'class.html#first_method'

        Finally, a reference of the form ClassName looks up a specific class:

        >>> doc.translate_ref_to_url('MyClass')
        'class.html#MyClass'

        """
        if ref.startswith('#'):
            method_name = ref[1:]
            if isinstance(in_comment, FunctionDoc) and in_comment.member:
                search_in = self.all_classes[in_comment.member]
            elif isinstance(in_comment, ClassDoc):
                search_in = in_comment
            else:
                search_in = None

            try:
                return search_in.get_method(method_name).url
            except AttributeError:
                pass

            def lookup_ref(file_doc):
                for fn in file_doc.functions:
                    if fn.name == method_name:
                        return fn.url
                return None
        elif '#' in ref:
            class_name, method_name = ref.split('#')
            def lookup_ref(file_doc):
                for cls in file_doc.classes:
                    if cls.name == class_name:
                        try:
                            return cls.get_method(method_name).url
                        except AttributeError:
                            pass
                return None
        else:
            class_name = ref
            def lookup_ref(file_doc):
                for cls in file_doc.classes:
                    if cls.name == class_name:
                        return cls.url
                return None

        for file_doc in self.values():
            url = lookup_ref(file_doc)
            if url:
                return file_doc.url + url
        return ''

    def build_see_html(self, see_tags, header_tag, in_comment=None):
        def list_tag(see_tag):
            return '<li><a href = "%s">%s</a></li>' % (
                    self.translate_ref_to_url(see_tag, in_comment), see_tag)
        if see_tags:
            return '<%s>See Also:</%s>\n<ul>\n' % (header_tag, header_tag) + \
                   '\n'.join(list_tag(tag) for tag in see_tags) + '</ul>'
        else:
            return ''

    def translate_links(self, text, in_comment=None):
        """
        Turn all @link tags in `text` into HTML anchor tags.

        `in_comment` is the `CommentDoc` that contains the text, for
        relative method lookups.
        """
        def replace_link(matchobj):
            ref = matchobj.group(1)
            return '<a href = "%s">%s</a>' % (
                    self.translate_ref_to_url(ref, in_comment), ref)
        return re.sub('{@link ([\w#]+)}', replace_link, text)

    def to_json(self, files=None):
        """
        Converts the full CodeBaseDoc into JSON text.  The optional `files`
        list lets you restrict the JSON dict to include only specific files.
        """
        return encode_json(self.to_dict(files))

    def to_dict(self, files=None):
        """
        Converts the CodeBaseDoc into a dictionary containing the to_dict()
        representations of each contained file.  The optional `files` list
        lets you restrict the dict to include only specific files.

        >>> CodeBaseDoc(['examples']).to_dict(['class.js']).get('module.js')
        >>> CodeBaseDoc(['examples']).to_dict(['class.js'])['class.js'][0]['name']
        'MyClass'

        """
        keys = files or self.keys()
        return dict((key, self[key].to_dict()) for key in keys)

    def to_html(self):
        """
        Builds basic HTML for the full module index.
        """
        return '<h1>Module index</h1>\n' + \
                make_index('all_modules', self.values())

    def save_docs(self, files=None, output_dir=None):
        """
        Save documentation files for codebase into `output_dir`.  If output
        dir is None, it'll refrain from building the index page and build
        the file(s) in the current directory.

        If `files` is None, it'll build all files in the codebase.
        """
        if output_dir:
            try:
                os.mkdir(output_dir)
            except OSError:
                pass

            try:
                import pkg_resources
                save_file(os.path.join(output_dir, 'jsdoc.css'),
                    pkg_resources.resource_string(__name__, 'static/jsdoc.css'))
            except (ImportError, IOError):
                try:
                    import shutil
                    base_dir = os.path.dirname(os.path.realpath(__file__))
                    css_file = os.path.join(base_dir, 'jsdoc.css')
                    shutil.copy(css_file, output_dir)
                except IOError:
                    print 'jsdoc.css not found.  HTML will not be styled.'

            save_file('%s/index.html' % output_dir, 
                    build_html_page('Module index', self.to_html()))
        else:
            output_dir = '.'

        if files is None:
            files = self.keys()

        for filename in files:
            try:
                doc = self[filename]
                save_file('%s/%s.html' % (output_dir, trim_js_ext(doc.name)), 
                        build_html_page(doc.name, doc.to_html(self)))
            except KeyError:
                warn('File %s does not exist', filename)

class FileDoc(object):
    """
    Represents documentaion for an entire file.  The constructor takes the
    source text for file, parses it, then provides a class wrapper around
    the parsed text.
    """

    def __init__(self, file_name, file_text):
        """
        Construct a FileDoc.  `file_name` is the name of the JavaScript file,
        `file_text` is its text.
        """
        self.name = file_name
        self.order = []
        self.comments = { 'file_overview': ModuleDoc({}) }
        is_first = True
        for comment, next_line in get_doc_comments(file_text):
            raw = parse_comment(strip_stars(comment), next_line)

            if 'fileoverview' in raw:
                obj = ModuleDoc(raw)
            elif raw.get('function') or raw.get('guessed_function'):
                obj = FunctionDoc(raw)
            elif raw.get('class'):
                obj = ClassDoc(raw)
            elif is_first:
                obj = ModuleDoc(raw)
            else:
                continue

            self.order.append(obj.name)
            self.comments[obj.name] = obj
            is_first = False

        for method in self.methods:
            try:
                self.comments[method.member].add_method(method)
            except AttributeError:
                warn('member %s of %s is not a class', 
                            method.member, method.name)
            except KeyError:
                pass

    def __str__(self):
        return "Docs for file " + self.name

    def keys(self):
        """
        Returns all legal names for doc comments.

        >>> file = FileDoc('module.js', read_file('examples/module.js'))
        >>> file.keys()[1]
        'the_first_function'
        >>> file.keys()[4]
        'not_auto_discovered'

        """
        return self.order

    def values(self):
        """
        Same as list(file_doc).

        >>> file = FileDoc('module.js', read_file('examples/module.js'))
        >>> file.values()[0].doc[:30]
        'This is the module documentati'

        """
        return list(self)

    def __iter__(self):
        """
        Returns all comments from the file, in the order they appear.
        """
        return (self.comments[name] for name in self.order)

    def __contains__(self, name):
        """
        Returns True if the specified function or class name is in this file.
        """
        return name in self.comments

    def __getitem__(self, index):
        """
        If `index` is a string, returns the named method/function/class 
        from the file.

        >>> file = FileDoc('module.js', read_file('examples/module.js'))
        >>> file['the_second_function'].doc
        'This is the documentation for the second function.'

        If `index` is an integer, returns the ordered comment from the file.

        >>> file[0].name
        'file_overview'
        >>> file[0].doc[:30]
        'This is the module documentati'

        """
        if isinstance(index, int):
            return self.comments[self.order[index]]
        else:
            return self.comments[index]

    def set_all_dependencies(self, dependencies):
        """
        Sets the `all_dependencies` property on the module documentation.
        """
        self.comments['file_overview'].all_dependencies = dependencies

    @property
    def module(self):
        """
        Return the `ModuleDoc` comment for this file.
        """
        return self.comments['file_overview']

    @property
    def doc(self):
        """
        Shortcut for ``self.module.doc``.
        """
        return self.module.doc

    @property
    def url(self):
        return trim_js_ext(self.name) + '.html'

    def _filtered_iter(self, pred):
        return (self.comments[name] for name in self.order 
                if pred(self.comments[name]))

    @property
    def functions(self):
        """
        Returns a generator of all standalone functions in the file, in textual
        order.

        >>> file = FileDoc('module.js', read_file('examples/module.js'))
        >>> list(file.functions)[0].name
        'the_first_function'
        >>> list(file.functions)[3].name
        'not_auto_discovered'

        """
        def is_function(comment):
            return isinstance(comment, FunctionDoc) and not comment.member
        return self._filtered_iter(is_function)

    @property
    def methods(self):
        """
        Returns a generator of all member functions in the file, in textual
        order.  

        >>> file = FileDoc('class.js', read_file('examples/class.js'))
        >>> file.methods.next().name
        'first_method'

        """
        def is_method(comment):
            return isinstance(comment, FunctionDoc) and comment.member
        return self._filtered_iter(is_method)

    @property
    def classes(self):
        """
        Returns a generator of all classes in the file, in textual order.

        >>> file = FileDoc('class.js', read_file('examples/class.js'))
        >>> cls = file.classes.next()
        >>> cls.name
        'MyClass'
        >>> cls.methods[0].name
        'first_method'

        """
        return self._filtered_iter(lambda c: isinstance(c, ClassDoc))

    def to_dict(self):
        return [comment.to_dict() for comment in self]

    def to_html(self, codebase):
        if codebase.include_private:
            def visible(fns): return fns
        else:
            def visible(fns): 
                return filter(lambda fn: not fn.is_private, fns)

        vars = [
            ('module', self.module.to_html(codebase)),
            ('function_index', make_index('functions', visible(self.functions))),
            ('class_index', make_index('classes', self.classes)),
            ('functions', '\n'.join(fn.to_html(codebase) 
                                    for fn in visible(self.functions))),
            ('classes', '\n'.join(cls.to_html(codebase) for cls in self.classes))
        ]
        html = '<h1>Module documentation for %s</h1>\n%s' % (self.name, 
                htmlize_paragraphs(codebase.translate_links(self.module.doc)))
        for key, html_text in vars:
            if html_text:
                html += '<h2>%s</h2>\n%s' % (printable(key), html_text)
        return html

class CommentDoc(object):
    """
    Base class for all classes that represent a parsed comment of some sort.
    """
    def __init__(self, parsed_comment):
        self.parsed = parsed_comment

    def __str__(self):
        return "Docs for " + self.name

    def __repr__(self):
        return str(self)

    def __contains__(self, tag_name):
        return tag_name in self.parsed

    def __getitem__(self, tag_name):
        return self.get(tag_name)

    def get(self, tag_name, default=''):
        """
        Return the value of a particular tag, or None if that tag doesn't
        exist.  Use 'doc' for the comment body itself.
        """
        return self.parsed.get(tag_name, default)

    def get_as_list(self, tag_name):
        """
        Return the value of a tag, making sure that it's a list.  Absent
        tags are returned as an empty-list; single tags are returned as a
        one-element list.

        The returned list is a copy, and modifications do not affect the
        original object.
        """
        val = self.get(tag_name, [])
        if isinstance(val, list):
            return val[:]
        else:
            return [val]

    @property
    def doc(self):
        """
        Return the comment body.
        """
        return self.get('doc')

    @property
    def url(self):
        """
        Return a URL for the comment, within the page.
        """
        return '#' + self.name

    @property
    def see(self):
        """
        Return a list of all @see tags on the comment.
        """
        return self.get_as_list('see')

    def to_json(self):
        """
        Return a JSON representation of the CommentDoc.  Keys are as per
        to_dict.
        """
        return encode_json(self.to_dict())

    def to_dict(self):
        """
        Return a dictionary representation of the CommentDoc.  The keys of
        this correspond to the tags in the comment, with the comment body in
        `doc`.
        """
        return self.parsed.copy()


class ModuleDoc(CommentDoc):
    """
    Represents the top-level fileoverview documentation.
    """

    @property
    def name(self): 
        """
        Always return 'file_overview'.
        """
        return 'file_overview'

    @property
    def author(self): 
        """
        Return the author of this module, as a string.
        """
        return self.get('author')

    @property
    def organization(self): 
        """
        Return the organization that developed this, as as string.
        """
        return self.get('organization')

    @property
    def license(self): 
        """
        Return the license of this module, as as string.
        """
        return self.get('license')

    @property
    def version(self): 
        """
        Return the version of this module, as as string.
        """
        return self.get('version')

    @property
    def dependencies(self): 
        """
        Returns the immediate dependencies of a module (only those that are
        explicitly declared).  Use the `all_dependencies` field for transitive
        dependencies - the FileDoc must have been created by a CodeBaseDoc for
        this field to exist.

        >>> FileDoc('', read_file('examples/module_closure.js')).module.dependencies
        ['module.js']
        >>> FileDoc('subclass.js', read_file('examples/subclass.js')).module.dependencies
        ['module_closure.js', 'class.js']

        """
        return self.get_as_list('dependency')

    def to_dict(self):
        """
        Return this ModuleDoc as a dict.  In addition to `CommentDoc` defaults,
        this has:

            - **name**: The module name.
            - **dependencies**: A list of immediate dependencies.
            - **all_dependencies**: A list of all dependencies.
        """
        vars = super(ModuleDoc, self).to_dict()
        vars['dependencies'] = self.dependencies
        vars['name'] = self.name
        try:
            vars['all_dependencies'] = self.all_dependencies[:]
        except AttributeError:
            vars['all_dependencies'] = []
        return vars

    def to_html(self, codebase):
        """
        Convert this to HTML.
        """
        html = ''
        def build_line(key, include_pred, format_fn):
            val = getattr(self, key)
            if include_pred(val):
                return '<dt>%s</dt><dd>%s</dd>\n' % (printable(key), format_fn(val))
            else:
                return ''
        def build_dependency(val):
            return ', '.join('<a href = "%s.html">%s</a>' % (trim_js_ext(name), name)
                             for name in val)
        for key in ('author', 'organization', 'version', 'license'):
            html += build_line(key, lambda val: val, lambda val: val)
        html += build_line('dependencies', lambda val: val, build_dependency)
        html += build_line('all_dependencies', lambda val: len(val) > 1, 
                                                build_dependency)
        html += codebase.build_see_html(self.see, 'h3')
        
        if html:
            return '<dl class = "module">\n%s\n</dl>\n' % html
        else:
            return ''

class FunctionDoc(CommentDoc):
    r"""
    Documentation for a single function or method.  Takes a parsed
    comment and provides accessors for accessing the various fields.

    >>> comments = parse_comments_for_file('examples/module_closure.js')
    >>> fn1 = FunctionDoc(comments[1])
    >>> fn1.name
    'the_first_function'
    >>> fn1.doc
    'The auto-naming can pick up functions defined as fields of an object,\n as is common with classes and the module pattern.'

    """
    def __init__(self, parsed_comment):
        super(FunctionDoc, self).__init__(parsed_comment)
    
    @property
    def name(self): 
        return self.get('guessed_function') or self.get('function')

    @property
    def params(self):
        """
        Returns a ParamDoc for each parameter of the function, picking up
        the order from the actual parameter list.

        >>> comments = parse_comments_for_file('examples/module_closure.js')
        >>> fn2 = FunctionDoc(comments[2])
        >>> fn2.params[0].name
        'elem'
        >>> fn2.params[1].type
        'Function(DOM)'
        >>> fn2.params[2].doc
        'The Options array.'

        """
        tag_texts = self.get_as_list('param') + self.get_as_list('argument')
        if self.get('guessed_params') is None:
            return [ParamDoc(text) for text in tag_texts]
        else:
            param_dict = {}
            for text in tag_texts:
                param = ParamDoc(text)
                param_dict[param.name] = param
            return [param_dict.get(name) or ParamDoc('{} ' + name)
                    for name in self.get('guessed_params')]

    @property
    def options(self):
        """
        Return the options for this function, as a list of ParamDocs.  This is
        a common pattern for emulating keyword arguments.

        >>> comments = parse_comments_for_file('examples/module_closure.js')
        >>> fn2 = FunctionDoc(comments[2])
        >>> fn2.options[0].name
        'foo'
        >>> fn2.options[1].type
        'Int'
        >>> fn2.options[1].doc
        'Some other option'

        """
        return [ParamDoc(text) for text in self.get_as_list('option')]

    @property
    def return_val(self):
        """
        Returns the return value of the function, as a ParamDoc with an
        empty name:

        >>> comments = parse_comments_for_file('examples/module_closure.js')
        >>> fn1 = FunctionDoc(comments[1])
        >>> fn1.return_val.name
        ''
        >>> fn1.return_val.doc
        'Some value'
        >>> fn1.return_val.type
        'String'

        >>> fn2 = FunctionDoc(comments[2])
        >>> fn2.return_val.doc
        'Some property of the elements.'
        >>> fn2.return_val.type
        'Array<String>'

        """
        ret = self.get('return') or self.get('returns')
        type = self.get('type')
        if '{' in ret and '}' in ret:
            if not '}  ' in ret:
                # Ensure that name is empty
                ret = ret.replace('} ', '}  ')
            return ParamDoc(ret)
        if ret and type:
            return ParamDoc('{%s}  %s' % (type, ret))
        return ParamDoc(ret)

    @property
    def exceptions(self):
        """
        Returns a list of ParamDoc objects (with empty names) of the
        exception tags for the function.

        >>> comments = parse_comments_for_file('examples/module_closure.js')
        >>> fn1 = FunctionDoc(comments[1])
        >>> fn1.exceptions[0].doc
        'Another exception'
        >>> fn1.exceptions[1].doc
        'A fake exception'
        >>> fn1.exceptions[1].type
        'String'

        """
        def make_param(text):
            if '{' in text and '}' in text:
                # Make sure param name is blank:
                word_split = list(split_delimited('{}', ' ', text))
                if word_split[1] != '':
                    text = ' '.join([word_split[0], ''] + word_split[1:])
            else:
                # Handle old JSDoc format
                word_split = text.split()
                text = '{%s}  %s' % (word_split[0], ' '.join(word_split[1:]))
            return ParamDoc(text)
        return [make_param(text) for text in 
                self.get_as_list('throws') + self.get_as_list('exception')]

    @property
    def is_private(self):
        """
        Return True if this is a private function or method.
        """
        return 'private' in self.parsed

    @property
    def member(self):
        """
        Return the raw text of the @member tag, a reference to a method's
        containing class, or None if this is a standalone function.
        """
        return self.get('member')

    @property
    def is_constructor(self):
        """
        Return True if this function is a constructor.
        """
        return 'constructor' in self.parsed

    def to_dict(self):
        """
        Convert this FunctionDoc to a dictionary.  In addition to `CommentDoc`
        keys, this adds:

            - **name**: The function name
            - **params**: A list of parameter dictionaries
            - **options**: A list of option dictionaries
            - **exceptions**: A list of exception dictionaries
            - **return_val**: A dictionary describing the return type, as per `ParamDoc`
            - **is_private**: True if private
            - **is_constructor**: True if a constructor
            - **member**: The raw text of the member property.
        """
        vars = super(FunctionDoc, self).to_dict()
        vars.update({
            'name': self.name,
            'params': [param.to_dict() for param in self.params],
            'options': [option.to_dict() for option in self.options],
            'exceptions': [exc.to_dict() for exc in self.exceptions],
            'return_val': self.return_val.to_dict(),
            'is_private': self.is_private,
            'is_constructor': self.is_constructor,
            'member': self.member
        })
        return vars

    def to_html(self, codebase):
        """
        Convert this `FunctionDoc` to HTML.
        """
        body = ''
        for section in ('params', 'options', 'exceptions'):
            val = getattr(self, section)
            if val:
                body += '<h5>%s</h5>\n<dl class = "%s">%s</dl>' % (
                        printable(section), section, 
                        '\n'.join(param.to_html() for param in val))

        body += codebase.build_see_html(self.see, 'h5', self)
        return ('<a name = "%s" />\n<div class = "function">\n' + 
                '<h4>%s</h4>\n%s\n%s\n</div>\n') % (self.name, self.name, 
                    htmlize_paragraphs(codebase.translate_links(self.doc, self)), body)

class ClassDoc(CommentDoc):
    """
    Documentation for a single class.
    """
    def __init__(self, parsed_comment):
        """
        Initialize this object from a parsed comment dictionary.  `add_method`
        must be called later to populate the `methods` property with
        `FunctionDoc`.
        """
        super(ClassDoc, self).__init__(parsed_comment)
        self.methods = []
        # Methods are added externally with add_method, after construction

    @property
    def name(self):
        return self.get('class') or self.get('constructor')

    @property
    def superclass(self):
        """
        Return the immediate superclass name of the class, as a string.  For
        the full inheritance chain, use the `all_superclasses` property, which
        returns a list of objects and only works if this ClassDoc was created
        from a `CodeBaseDoc`.
        """
        return self.get('extends') or self.get('base')

    @property
    def constructors(self):
        """
        Return all methods labeled with the @constructor tag.
        """
        return [fn for fn in self.methods if fn.is_constructor]

    def add_method(self, method):
        """
        Add a `FunctionDoc` method to this class.  Called automatically if this
        ClassDoc was constructed from a CodeBaseDoc.
        """
        self.methods.append(method)

    def has_method(self, method_name):
        """
        Returns True if this class contains the specified method.
        """
        return self.get_method(method_name) is not None

    def get_method(self, method_name, default=None):
        """
        Returns the contained method of the specified name, or `default` if
        not found.
        """
        for method in self.methods:
            if method.name == method_name:
                return method
        return default

    def to_dict(self):
        """
        Convert this ClassDoc to a dict, such as if you want to use it in a
        template or string interpolation.  Aside from the basic `CommentDoc`
        fields, this also contains:

            - **name**: The class name
            - **method**: A list of methods, in their dictionary form.
        """
        vars = super(ClassDoc, self).to_dict()
        vars.update({
            'name': self.name,
            'method': [method.to_dict() for method in self.methods]
        })
        return vars

    def to_html(self, codebase):
        """
        Convert this ClassDoc to HTML.  This returns the default long-form
        HTML description that's used when the full docs are built.
        """
        return ('<a name = "%s" />\n<div class = "jsclass">\n' + 
                '<h3>%s</h3>\n%s\n<h4>Methods</h4>\n%s</div>') % (
                self.name, self.name, 
                htmlize_paragraphs(codebase.translate_links(self.doc, self)) +
                codebase.build_see_html(self.see, 'h4', self),
                '\n'.join(method.to_html(codebase) for method in self.methods
                        if codebase.include_private or not method.is_private))

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

    def to_dict(self):
        """
        Convert this to a dict.  Keys (all strings) are:
            
            - **name**: Parameter name
            - **type**: Parameter type
            - **doc**: Parameter description
        """
        return {
            'name': self.name,
            'type': self.type,
            'doc': self.doc
        }

    def to_html(self, css_class=''):
        """
        Returns the parameter as a dt/dd pair.
        """
        if self.name and self.type:
            header_text = '%s (%s)' % (self.name, self.type)
        elif self.type:
            header_text = self.type
        else:
            header_text = self.name
        return '<dt>%s</dt><dd>%s</dd>' % (header_text, self.doc)

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
    Build a graph where nodes are filenames and edges are reverse dependencies
    (so an edge from jquery.js to jquery.dimensions.js indicates that jquery.js
    must be included before jquery.dimensions.js).  The graph is represented
    as a dictionary from filename to (in-degree, edges) pair, for ease of
    topological sorting.  Also returns a list of nodes of degree zero.
    """
    queue = []
    dependencies = {}
    start_sort = []
    def add_vertex(file):
        in_degree = len(js_doc[file].module.dependencies)
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
        for dependency in js_doc[file].module.dependencies:
            if dependency not in js_doc:
                raise MissingDependency(file, dependency)
            if not is_in_graph(dependency):
                add_vertex(dependency)
            add_edge(dependency, file)
    return dependencies, start_sort 

def topological_sort(dependencies, start_nodes):
    """
    Perform a topological sort on the dependency graph `dependencies`, starting
    from list `start_nodes`.
    """
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
    Sort the dependency graph, taking in a list of starting module names and a
    CodeBaseDoc (or equivalent dictionary).  Returns an ordered list of
    transitive dependencies such that no module appears before its
    dependencies.
    """
    return topological_sort(*build_dependency_graph(start_nodes, js_doc))

##### HTML utilities #####
def build_html_page(title, body):
    """
    Build the simple tag skeleton for a title and body.
    """
    return """<html>
    <head>
        <title>%s</title>
        <link rel = "stylesheet" type = "text/css" href = "jsdoc.css" />
    </head>
    <body>
        %s
    </body>
</html>""" % (title, body)

def make_index(css_class, entities):
    """
    Generate the HTML index (a short description and a link to the full
    documentation) for a list of FunctionDocs or ClassDocs.
    """
    def make_entry(entity):
        return ('<dt><a href = "%(url)s">%(name)s</a></dt>\n' +
                '<dd>%(doc)s</dd>') % {
            'name': entity.name,
            'url': entity.url,
            'doc': first_sentence(entity.doc)
        }
    entry_text = '\n'.join(make_entry(val) for val in entities)
    if entry_text:
        return '<dl class = "%s">\n%s\n</dl>' % (css_class, entry_text)
    else:
        return ''

def first_sentence(str):
    """
    Return the first sentence of a string - everything up to the period,
    or the whole text if there is no period.

    >>> first_sentence('')
    ''
    >>> first_sentence('Incomplete')
    ''
    >>> first_sentence('The first sentence.  This is ignored.')
    'The first sentence.'

    """
    return str[0:str.find('.') + 1]

def htmlize_paragraphs(text):
    """
    Convert paragraphs delimited by blank lines into HTML text enclosed
    in <p> tags.
    """
    paragraphs = re.split('(\r?\n)\s*(\r?\n)', text)
    return '\n'.join('<p>%s</p>' % paragraph for paragraph in paragraphs)

def printable(id):
    """
    Turn a Python identifier into something fit for human consumption.

    >>> printable('author')
    'Author'
    >>> printable('all_dependencies')
    'All Dependencies'

    """
    return ' '.join(word.capitalize() for word in id.split('_'))


##### Command-line functions #####

def usage():
    command_name = sys.argv[0]
    print """
Usage: %(name)s [options] file1.js file2.js ...

By default, this tool recursively searches the current directory for .js files
to build up its dependency database.  This can be changed with the --jspath option (see below).  It then outputs the JSDoc for the files on the command-line (if no files are listed, it generates the docs for the whole sourcebase).  If only a single file is listed and no output directory is specified, the HTML page is placed in the current directory; otherwise, all pages and a module index are placed in the output directory.

Available options:

  -p, --jspath  Directory to search for JS libraries (multiple allowed)
  -o, --output  Output directory for building full documentation (default: apidocs)
  --private     Include private functions & methods in output
  --help        Print usage information and exit
  --test        Run PyJSDoc unit tests
  -j, --json    Output doc parse tree in JSON instead of building HTML
  -d, --dependencies    Output dependencies for file(s) only

Cookbook of common tasks:

  Find dependencies of the Dimensions plugin in the jQuery CVS repository, 
  filtering out packed files from the search path:

  $ %(name)s -d -p trunk/plugins jquery.dimensions.js

  Concatenate dependent plugins into a single file for web page:

  $ %(name)s -d rootfile1.js rootfile2.js | xargs cat > scripts.js

  Read documentation information for form plugin (including full dependencies),
  and include on a PHP web page using the PHP Services_JSON module:

  <?php
  $json = new Services_JSON();
  $jsdoc = $json->decode(`%(name)s jquery.form.js -j -p trunk/plugins`);
  ?>

  Build documentation for all modules on your system:

  $ %(name)s -p ~/svn/js -o /var/www/htdocs/jqdocs
""" % {'name': os.path.basename(command_name) }

def get_path_list(opts):
    """
    Return a list of all root paths where JS files can be found, given the
    command line options (in dict form) for this script.
    """
    paths = []
    for opt, arg in opts.items():
        if opt in ('-p', '--jspath'):
            paths.append(arg)
    return paths or [os.getcwd()]

def run_and_exit_if(opts, action, *names):
    """
    Run the no-arg function `action` if any of `names` appears in the
    option dict `opts`.
    """
    for name in names:
        if name in opts:
            action()
            sys.exit(0)

def run_doctests():
    import doctest
    doctest.testmod()

def main(args=sys.argv):
    """
    Main command-line invocation.
    """
    try:
        opts, args = getopt.gnu_getopt(args[1:], 'p:o:jdt', [
            'jspath=', 'output=', 'private', 'json', 'dependencies', 
            'test', 'help'])
        opts = dict(opts)
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    run_and_exit_if(opts, run_doctests, '--test')
    run_and_exit_if(opts, usage, '--help')

    js_paths = get_path_list(opts)
    docs = CodeBaseDoc(js_paths, '--private' in opts)
    if args:
        selected_files = set(docs.keys()) & set(args)
    else:
        selected_files = docs.keys()

    def print_json():
        print docs.to_json(selected_files)
    run_and_exit_if(opts, print_json, '--json', '-j')

    def print_dependencies():
        for dependency in find_dependencies(selected_files, docs):
            print dependency
    run_and_exit_if(opts, print_dependencies, '--dependencies', '-d')

    output = opts.get('--output') or opts.get('-o')
    if output is None and len(args) != 1:
        output = 'apidocs'
    docs.save_docs(selected_files, output)

if __name__ == '__main__':
    main()
