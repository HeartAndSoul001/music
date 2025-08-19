from setuptools import setup, find_packages

setup(
    name="music-tagger",
    version="0.1",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "aiohttp",
        "spotipy",
        "musicbrainzngs",
        "mutagen",
        "fuzzywuzzy",
        "python-Levenshtein",
        "tqdm",
        "nest-asyncio",
        "pillow",
        "pyyaml"
    ],
    python_requires=">=3.10",
)
