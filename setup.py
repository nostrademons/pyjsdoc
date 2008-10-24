#!/usr/bin/env python2.5
from setuptools import setup, find_packages

setup(
    name='PyJSDoc',
    version='0.9.0',
    py_modules=['pyjsdoc'],
    packages=['static'],
    include_package_data=True,
    zip_safe=True,

    author='Jonathan Tang',
    author_email='jonathan.d.tang@gmail.com',
    license="MIT License",
    platforms="Any",
    url='http://jonathan.tang.name/code/pyjsdoc',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Environment :: Console',
        'Topic :: Software Development :: Documentation',
        'Topic :: Internet :: WWW/HTTP'
    ],
    description='Python port of JSDoc.',
    long_description='Provides a programmatic API to access JSDoc comments and their associated @tags, along with tools for documentation generation, JSON output, and dependency analysis.',
    entry_points = {
        'console_scripts': [
            'pyjsdoc = pyjsdoc:main',
            'jsdoc = pyjsdoc:main'
        ]
    }
)
