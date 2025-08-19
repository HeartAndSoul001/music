"""音乐数据源基类模块"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from music_metadata import MusicMetadata

class MusicSource(ABC):
    """音乐数据源基类"""
    
    @abstractmethod
    async def search(self, title: str, artist: str = None) -> Optional[MusicMetadata]:
        """
        搜索音乐信息
        
        Args:
            title: 歌曲标题
            artist: 艺术家名称
            
        Returns:
            匹配的音乐元数据，如果未找到则返回 None
        """
        pass
        
    @abstractmethod
    async def get_album_cover(self, metadata: MusicMetadata, quality: str = "high") -> Optional[Dict[str, Any]]:
        """
        获取专辑封面
        
        Args:
            metadata: 音乐元数据
            quality: 图片质量 (low/medium/high)
            
        Returns:
            包含以下字段的字典：
            - data: 图片数据（bytes）
            - mime_type: 图片MIME类型
            - size: 图片大小（字节）
            - width: 图片宽度（如果可用）
            - height: 图片高度（如果可用）
        """
        pass
        
    @abstractmethod
    async def get_lyrics(self, metadata: MusicMetadata) -> Optional[Dict[str, Any]]:
        """
        获取歌词
        
        Args:
            metadata: 音乐元数据
            
        Returns:
            包含以下字段的字典：
            - text: 歌词文本
            - language: 歌词语言
            - is_translated: 是否为翻译版本
            - source_language: 原始语言（如果是翻译版本）
        """
        pass
        
    def _normalize_url(self, url: str) -> str:
        """标准化URL，确保使用HTTPS"""
        if url.startswith("http://"):
            return "https://" + url[7:]
        return url
