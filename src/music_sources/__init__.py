"""音乐数据源模块"""
from .base import MusicSource
from .netease import NeteaseMusicSource
from .qq import QQMusicSource
from .musicbrainz import MusicBrainzSource
from .spotify import SpotifySource

__all__ = [
    'MusicSource',
    'NeteaseMusicSource',
    'QQMusicSource',
    'MusicBrainzSource',
    'SpotifySource'
]
