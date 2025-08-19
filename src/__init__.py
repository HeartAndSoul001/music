"""
音乐标签工具
~~~~~~~~~~~

一个用于自动获取和更新音乐文件元数据的工具。
"""

from .music_tagger import MusicTagger
from .music_metadata import MusicMetadata
from .music_sources import MusicSource, MusicBrainzSource, SpotifySource, NeteaseMusicSource, QQMusicSource
from .config import Config

__all__ = [
    'MusicTagger',
    'MusicMetadata',
    'MusicSource',
    'MusicBrainzSource',
    'SpotifySource',
    'NeteaseMusicSource',
    'QQMusicSource',
    'Config',
]
