#!/usr/bin/env python3
"""
Setup script для LSwitch 2.0
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
    description='Layout Switcher for Linux — переключатель раскладки с авто-конвертацией',
    long_description=read_file('README.md'),
    long_description_content_type='text/markdown',
    author='Anton',
    url='https://github.com/kabobik/lswitch',
    packages=find_packages(exclude=['tests', 'docs', 'archive']),
    python_requires='>=3.10',
    install_requires=[
        'evdev',         # Чтение событий клавиатуры из /dev/input
        'python-xlib',   # Определение раскладки и работа с X11
        'pyudev>=0.24',  # Мониторинг hot-plug устройств ввода
    ],
    extras_require={
        'gui': ['PyQt5'],  # GUI панель управления
        'dev': [
            'pytest>=7.0',
            'pytest-cov',
        ],
    },
    entry_points={
        'console_scripts': [
            'lswitch=lswitch.cli:main',
        ],
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: End Users/Desktop',
        'Topic :: Utilities',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Operating System :: POSIX :: Linux',
        'Environment :: X11 Applications',
        'Topic :: Desktop Environment',
    ],
)
