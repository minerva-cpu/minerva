from setuptools import setup, find_packages


setup(
    name="minerva",
    version="0.1",
    description="A 32-bit RISC-V soft processor",
    author="Jean-François Nguyen",
    author_email="jf@jfng.fr",
    license="BSD",
    python_requires=">=3.7",
    install_requires=["amaranth>=0.3,<0.5"],
    extras_require={ "debug": ["jtagtap"] },
    packages=find_packages(),
    project_urls={
        "Source Code": "https://github.com/minerva-cpu/minerva",
        "Bug Tracker": "https://github.com/minerva-cpu/minerva/issues"
    }
)
