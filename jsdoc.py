#!/usr/bin/env python

# Copyright (c) 2007/08 by Jonathan Tang
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

def parse_all_files(files, prefix=None):
    """
    Returns the parsed JSDoc for all files in the input list, as a dictionary
    mapping module names to FileDoc objects.

    The dictionary may either be keyed by the basename of the file (the default)
    or by having ``prefix`` chopped off the beginning of each full filename.
    You may pass multiple prefixes as a list; the full filename is tested
    against each and chopped if it matches.
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
