from setuptools import find_namespace_packages, setup

setup(
    name="rovo-relay", version="0.1.0a1",
    description="Experimental Rovo browser harness built using CLI-Anything",
    packages=find_namespace_packages(include=["cli_anything.*"], exclude=["*.tests"]),
    package_data={"cli_anything.rovo": ["skills/*.md", "README.md"]},
    install_requires=["click==8.5.0", "playwright==1.64.0", "prompt-toolkit==3.0.53"],
    python_requires=">=3.11",
    entry_points={"console_scripts": ["rovo-relay=cli_anything.rovo.rovo_cli:main"]},
    license_files=["LICENSE", "NOTICE"],
)
