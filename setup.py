from setuptools import setup, find_packages

setup(
    name="arg_bot",
    version="0.1.0",
    description="Telegram bot for Hardweb community",
    author="e11sy",
    author_email="egoramurin@gmail.com",
    python_requires=">=3.8",
    install_requires=[
        "python-telegram-bot>=22.1",
        "pillow>=11.2.1",
        "requests>=2.32.4",
        "aiohttp>=3.12.13",
        "redis>=5.0.4",
    ],
    package_dir={"": "src"},
    packages=find_packages(where="src"),
)
