from setuptools import setup

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="sslh-cli",
    packages=['sslh-cli'],
    package_dir={'sslh-cli': 'sslh-cli'},
    version="0.4.0",
    author="rth",
    author_email="rath@gwu.edu",
    description="Command line interface for user friendly spikesorting",
    url="https://github.com/UserFriendlySpikesorting/SpikesortingLabHub-CLI",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GPL 3",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.13",
    install_requires=requirements,
    scripts=["sslh-cli/sslh-cli"],
)
