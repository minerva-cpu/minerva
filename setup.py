from setuptools import setup, find_packages


setup(
    name="minerva",
    version="0.1",
    description="A 32-bit RISC-V soft processor",
    author="Jean-François Nguyen",
    author_email="jf@lambdaconcept.com",
    license="BSD",
    python_requires=">=3.6",
    install_requires=["amaranth>=0.2,<0.5"],
    extras_require={ "debug": ["jtagtap"] },
    packages=find_packages(),
    project_urls={
        "Source Code": "https://github.com/lambdaconcept/minerva",
        "Bug Tracker": "https://github.com/lambdaconcept/minerva/issues"
    }
)
