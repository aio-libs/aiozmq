import os
import re
import sys
from setuptools import setup, find_packages


install_requires = ['pyzmq>=13.1,!=17.1.2']

tests_require = install_requires + ['msgpack>=0.5.0']

extras_require = {'rpc': ['msgpack>=0.5.0']}


if sys.version_info < (3, 5):
    raise RuntimeError("aiozmq requires Python 3.5 or higher")


def read(f):
    return open(os.path.join(os.path.dirname(__file__), f)).read().strip()


def read_version():
    regexp = re.compile(r"^__version__\W*=\W*'([\d.abrc]+)'")
    init_py = os.path.join(os.path.dirname(__file__), 'aiozmq', '__init__.py')
    with open(init_py) as f:
        for line in f:
            match = regexp.match(line)
            if match is not None:
                return match.group(1)
        else:
            raise RuntimeError('Cannot find version in aiozmq/__init__.py')


classifiers = [
    'License :: OSI Approved :: BSD License',
    'Intended Audience :: Developers',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
    'Programming Language :: Python :: 3.7',
    'Programming Language :: Python :: 3.8',
    'Operating System :: POSIX',
    'Operating System :: MacOS :: MacOS X',
    'Operating System :: Microsoft :: Windows',
    'Environment :: Web Environment',
    'Development Status :: 4 - Beta',
    'Framework :: AsyncIO',
]


setup(name='aiozmq',
      version=read_version(),
      description=('ZeroMQ integration with asyncio.'),
      long_description='\n\n'.join((read('README.rst'), read('CHANGES.txt'))),
      classifiers=classifiers,
      platforms=['POSIX', 'Windows', 'MacOS X'],
      author='Nikolay Kim',
      author_email='fafhrd91@gmail.com',
      maintainer='Jelle Zijlstra',
      maintainer_email='jelle.zijlstra@gmail.com',
      url='http://aiozmq.readthedocs.org',
      download_url='https://pypi.python.org/pypi/aiozmq',
      license='BSD',
      packages=find_packages(),
      install_requires=install_requires,
      tests_require=tests_require,
      extras_require=extras_require,
      entry_points={
          'console_scripts': [
              'aiozmq-proxy = aiozmq.cli.proxy:main',
              ],
          },
      include_package_data=True)
