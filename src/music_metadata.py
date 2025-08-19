"""音乐元数据模块"""
from typing import Optional

class MusicMetadata:
    """音乐元数据类"""
    def __init__(self, title: str, artist: str, album: str, confidence: float = 0.0):
        self.title = title
        self.artist = artist
        self.album = album
        self.confidence = confidence
        self.cover_url: Optional[str] = None
        self.release_id: Optional[str] = None
        self.source: Optional[str] = None
        
    def __str__(self):
        source_info = f" [{self.source}]" if self.source else ""
        return f"{self.artist} - {self.title} ({self.album}) [置信度: {self.confidence:.2f}]{source_info}"
