#!/usr/bin/env python2.5
from setuptools import setup, find_packages

setup(
    name='PyJSDoc',
    version='0.9.0',
    py_modules=['pyjsdoc'],
    packages=['static'],
    include_package_data=True,
    zip_safe=False,

    author='Jonathan Tang',
    author_email='jonathan.d.tang@gmail.com',
    license="MIT License",
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
    description='Python port of JSDoc, including documentation generation, JSON dumps, and dependency analysis.',
    entry_points = {
        'console_scripts': [
            'pyjsdoc = pyjsdoc:main',
            'jsdoc = pyjsdoc:main'
        ]
    }
)
