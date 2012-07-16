# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
import pypdfml

f = open('requirements.txt', 'r')
lines = f.readlines()
requirements = [l.strip().strip('\n') for l in lines if l.strip() and not l.strip().startswith('#')]
readme = open('README.md').read()

setup(name=pypdfml.__title__,
      version=pypdfml.__version__,
      description=pypdfml.__description__,
      author=pypdfml.__author__,
      author_email=pypdfml.__author_email__,
      url='https://github.com/badzong/pypdfml',
      packages=find_packages(),
      zip_save=False,
      include_package_data=True,
      license=pypdfml.__license__,
      keywords='pdf generating reportlab report xml jinja',
      long_description=readme,
      install_requires=requirements,
)
