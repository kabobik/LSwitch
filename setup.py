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
    url='https://github.com/kabobik/lswitch',
    py_modules=['lswitch_control'],  # Top-level modules only
    packages=find_packages(exclude=['tests', 'docs']),
    python_requires='>=3.8',
    install_requires=[
        'evdev',         # Чтение событий клавиатуры из /dev/input
        'python-xlib',   # Определение раскладки и работа с X11
    ],
    extras_require={
        'gui': ['PyQt5'],  # GUI панель управления (lswitch-control)
        'dev': [
            'pytest>=7.0',
            'pytest-cov',
            'pytest-timeout',
        ],
    },
    entry_points={
        'console_scripts': [
            'lswitch=lswitch.cli:main',
            'lswitch-control=lswitch_control:main',
        ],
    },
    data_files=[
        # systemd user service
        ('/etc/systemd/user', ['config/lswitch.service']),
        # udev rules for input device access
        ('/etc/udev/rules.d', ['config/99-lswitch.rules']),
        # Desktop entry for GUI (menu + autostart)
        ('/usr/share/applications', ['config/lswitch-control.desktop']),
        ('/etc/xdg/autostart', ['config/lswitch-control.desktop']),
        # Icon
        ('/usr/share/pixmaps', ['assets/lswitch.png']),
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: End Users/Desktop',
        'Topic :: Utilities',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Operating System :: POSIX :: Linux',
        'Environment :: X11 Applications',
        'Topic :: Desktop Environment',
    ],
)
