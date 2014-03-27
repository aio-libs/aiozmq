import os
import re
import sys
from setuptools import setup, find_packages


install_requires = ['pyzmq>=13.1']

PY_VER = sys.version_info

if PY_VER >= (3, 4):
    pass
elif PY_VER >= (3, 3):
    install_requires.append('asyncio')
else:
    raise RuntimeError("aiozmq doesn't suppport Python earllier than 3.3")

tests_require = install_requires + ['nose']

extras_require = {'rpc': ['trafaret>=0.5.0', 'msgpack-python>=0.4.1']}


def read(f):
    return open(os.path.join(os.path.dirname(__file__), f)).read().strip()


def read_version():
    regexp = re.compile(r"^__version__\W*=\W*'([\d.]+)'")
    init_py = os.path.join(os.path.dirname(__file__), 'aiozmq', '__init__.py')
    with open(init_py) as f:
        for line in f:
            match = regexp.match(line)
            if match is not None:
                return match.group(1)
        else:
            raise RuntimeError('Cannot find version in aiozmq/__init__.py')


setup(name='aiozmq',
      version=read_version(),
      description=('ZeroMQ integration with asyncio.'),
      long_description='\n\n'.join((read('README.rst'), read('CHANGES.txt'))),
      classifiers=[
          'License :: OSI Approved :: BSD License',
          'Intended Audience :: Developers',
          'Programming Language :: Python',
          'Programming Language :: Python :: 3.3',
          'Programming Language :: Python :: 3.4',
          'Operating System :: POSIX',
          'Environment :: Web Environment',
          'Framework :: asyncio',
        ],
      platforms=['POSIX'],
      author='Nikolay Kim',
      author_email='fafhrd91@gmail.com',
      maintainer='Andrew Svetlov',
      maintainer_email='andrew.svetlov@gmail.com',
      url='http://aiozmq.readthedocs.org',
      license='BSD',
      packages=find_packages(),
      install_requires = install_requires,
      tests_require = tests_require,
      test_suite = 'nose.collector',
      include_package_data = True)
