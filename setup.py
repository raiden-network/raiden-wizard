from pathlib import Path
from setuptools import setup, find_packages


with open("README.md") as f:
    long_description = f.read()


def list_requirements(req_file: str) -> list:
    """
    Get all dependency names and versions from
    requirements.txt and append them to a list.
    """
    req_file = Path(req_file)
    req_list = []

    try:
        with open(req_file, "r") as requirements:
            for requirement in requirements:
                requirement = requirement.strip()
                req_list.append(requirement)

        return req_list
    except OSError:
        print("Not a valid requirements file")


setup(
    name="raiden-installer",
    version="0.1",
    license="MIT",
    description="Onboarding installer for Raiden",
    long_description=long_description,
    author="Brainbot Labs Est.",
    author_email="contact@brainbot.li",
    url="https://github.com/raiden-network/raiden-installer",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "License :: OSI Approved :: MIT License",
    ],
    packages=find_packages(exclude=["tests"]),
    install_requires=list_requirements("requirements.txt"),
    entry_point={
        "console_scripts": [
            "raiden_web_installer=raiden_installer.web.app:main",
            "raiden_cli_installer=raiden_installer.cli.app:main",
        ]
    },
)
