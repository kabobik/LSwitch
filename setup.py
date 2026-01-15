#!/usr/bin/env python3
"""
Setup script для LSwitch
"""

from setuptools import setup, find_packages
import os
import sys

# Импортируем версию
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from __version__ import __version__

# Читаем README для long_description
def read_file(filename):
    with open(os.path.join(os.path.dirname(__file__), filename), encoding='utf-8') as f:
        return f.read()

setup(
    name='lswitch',
    version=__version__,
    description='Layout Switcher for Linux - переключатель раскладки по двойному Shift',
    long_description=read_file('README.md'),
    long_description_content_type='text/markdown',
    author='Anton',
    url='https://github.com/yourusername/lswitch',
    py_modules=['lswitch_control', 'dictionary', 'ngrams', 'user_dictionary', 'i18n'],
    packages=find_packages(exclude=['tests', 'docs']),
    python_requires='>=3.6',
    install_requires=[
        'evdev',
        'python-xlib'
    ],
    entry_points={
        'console_scripts': [
            'lswitch=lswitch.cli:main',
        ],
    },
    package_data={
        # Include configuration and assets with the package for easier installs
        '': ['config/*', 'assets/*'],
    },
    data_files=[
        ('/etc/lswitch', ['config/config.json.example']),
        ('/etc/systemd/user', ['config/lswitch.service']),
        ('/etc/udev/rules.d', ['config/99-lswitch.rules']),
        ('/usr/share/applications', ['config/lswitch-control.desktop']),
        ('/usr/share/pixmaps', ['assets/lswitch.svg']),
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: End Users/Desktop',
        'Topic :: Utilities',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Operating System :: POSIX :: Linux',
    ],
)
