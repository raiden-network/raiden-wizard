"""A setuptools based setup module.

See:
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""

from setuptools import setup, find_packages
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()


setup(
    name='raideninstaller',
    version='0.0.1',
    description='One-click installer for the Raiden Network Stack.',
    long_description=long_description,
    long_description_content_type='text/rst',
    url='https://github.com/raiden-network/raideninstaller',
    author='Raiden Network Dev Team',
    author_email='',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',

        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',

        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    keywords='sample setuptools development',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    python_requires='>=3.6',
    install_requires=['requests'],

    extras_require={
        'dev': ['robotframework'],
    },

    package_data={},
    data_files=[],

    entry_points={
        'console_scripts': [
            'install-raiden=raiden_installer:main',
        ],
    },

    project_urls={
        'Bug Reports': 'https://github.com/raiden-network/raideninstaller/issues',
        'Source': 'https://github.com/raiden-network/raideninstaller/',
    },
)
