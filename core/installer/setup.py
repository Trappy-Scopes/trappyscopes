import setuptools

# Load the long_description from README.md
with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="Trappy-Scopes scope-cli",
    version="0.0.1",
    author="Yatharth Bhasin",
    author_email="yatharth1997@gmail.com",
    description="Scope Control Layer Interface for Trappy-Scopes microscopy system.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Trappy-Scopes/scope-cli",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Linux and Mac Os",
    ],
    python_requires='>=3.6',
)