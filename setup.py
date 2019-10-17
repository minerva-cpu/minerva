import sys
from setuptools import setup, find_packages


if sys.version_info[:3] < (3, 6):
    raise SystemExit("Minerva requires Python 3.6+")


setup(
    name="minerva",
    version="0.1",
    description="A 32-bit RISC-V soft processor",
    author="Jean-François Nguyen",
    author_email="jf@lambdaconcept.fr",
    license="BSD",
    install_requires=["nmigen>=0.1rc1"],
    extras_require={ "debug": ["jtagtap"] },
    packages=find_packages(),
    project_urls={
        "Source Code": "https://github.com/lambdaconcept/minerva",
        "Bug Tracker": "https://github.com/lambdaconcept/minerva/issues"
    }
)
