import os
import re
from setuptools import setup, find_packages


install_requires = ['pyzmq']

tests_require = install_requires + ['nose']


def read(f):
    return open(os.path.join(os.path.dirname(__file__), f)).read().strip()


def read_version():
    regexp = re.compile(r"^__version__\W*=\W*'([\d.]+)'")
    init_py = os.path.join(os.path.dirname(__file__), 'zmqtulip', '__init__.py')
    with open(init_py) as f:
        for line in f:
            match = regexp.match(line)
            if match is not None:
                return match.group(1)
        else:
            raise RuntimeError('Cannot find version in zmqtulip/__init__.py')


setup(name='pyzmqtulip',
      version=read_version(),
      description=('zmq integration with tulip.'),
      long_description='\n\n'.join((read('README.rst'), read('CHANGES.txt'))),
      classifiers=[
          'License :: OSI Approved :: BSD License',
          'Intended Audience :: Developers',
          'Programming Language :: Python',
          'Programming Language :: Python :: 3.3'],
      author='Nikolay Kim',
      author_email='fafhrd91@gmail.com',
      url='https://github.com/fafhrd91/pyzmqtulip/',
      license='BSD',
      packages=find_packages(),
      install_requires = install_requires,
      tests_require = tests_require,
      test_suite = 'nose.collector',
      include_package_data = True)
