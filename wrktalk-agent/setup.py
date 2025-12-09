"""Setup script for WrkTalk Agent."""

from setuptools import find_packages, setup

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="wrktalk-agent",
    version="1.0.0",
    description="WrkTalk Deployment Agent for Kubernetes and Docker",
    author="WrkTalk Engineering",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=requirements,
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "wrktalk-agent=wrktalk_agent.__main__:main",
        ],
    },
)
