from setuptools import setup, find_packages

setup(
    name="ticket-miner",
    version="0.3.0",
    description="A Python library for mining and analyzing ticket content and references from various knowledge base platforms",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Your Organization",
    author_email="maintainers@example.com",
    url="https://github.com/yourusername/ticket-miner",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "atlassian-python-api>=3.41.0",
        "python-dotenv>=1.0.0",
        "html2text>=2020.1.16",
        "urllib3>=2.0.0",
        "requests>=2.31.0",
        "psutil>=5.9.0",
        "aiohttp>=3.9.0"
    ],
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords="ticket mining, knowledge base, jira, confluence, documentation"
) 