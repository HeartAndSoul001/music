"""Spotify数据源模块"""
import logging
from typing import Optional, Dict, Any
import aiohttp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from fuzzywuzzy import fuzz

from .base import MusicSource
from music_metadata import MusicMetadata
from .cache_handler import MusicTaggerCacheHandler

logger = logging.getLogger(__name__)

class SpotifySource(MusicSource):
    """Spotify数据源"""
    def __init__(self, client_id: str, client_secret: str, weight: float = 1.0):
        self.weight = weight
        self.session = None
        cache_handler = MusicTaggerCacheHandler()
        self.sp = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=client_id,
                client_secret=client_secret,
                cache_handler=cache_handler
            )
        )
        
    async def _get_session(self):
        """获取或创建 aiohttp session"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
        
    async def close(self):
        """关闭会话"""
        if self.session:
            await self.session.close()
            self.session = None

    async def search(self, title: str, artist: str = None) -> Optional[MusicMetadata]:
        """搜索音乐信息"""
        try:
            query = f'track:"{title}"'
            if artist:
                query += f' artist:"{artist}"'

            results = self.sp.search(q=query, type='track', limit=5)
            
            if results and 'tracks' in results and results['tracks']['items']:
                track = results['tracks']['items'][0]
                metadata = MusicMetadata(
                    title=track['name'],
                    artist=track['artists'][0]['name'],
                    album=track['album']['name']
                )
                metadata.source = "spotify"
                metadata.source_data["spotify"] = track
                
                # 获取封面URL (Spotify提供多种尺寸)
                if track['album']['images']:
                    # 存储所有尺寸的URL
                    for image in track['album']['images']:
                        size = image['width']
                        if size >= 640:
                            metadata.cover_urls["spotify_high"] = image['url']
                        elif size >= 300:
                            metadata.cover_urls["spotify_medium"] = image['url']
                        else:
                            metadata.cover_urls["spotify_low"] = image['url']
                            
                    # 设置主封面（优先使用高质量版本）
                    if "spotify_high" in metadata.cover_urls:
                        metadata.cover_url = metadata.cover_urls["spotify_high"]
                    elif "spotify_medium" in metadata.cover_urls:
                        metadata.cover_url = metadata.cover_urls["spotify_medium"]
                
                # 计算相似度
                title_ratio = fuzz.ratio(title.lower(), metadata.title.lower())
                artist_ratio = fuzz.ratio(artist.lower(), metadata.artist.lower()) if artist else 100
                metadata.confidence = (title_ratio + artist_ratio) / 2
                
                return metadata
                
        except Exception as e:
            logger.error(f"Spotify搜索出错: {str(e)}")
        return None

    async def get_album_cover(self, metadata: MusicMetadata, quality: str = "high") -> Optional[Dict[str, Any]]:
        """获取专辑封面"""
        try:
            # 根据质量选择合适的URL
            url = None
            if quality == "high" and "spotify_high" in metadata.cover_urls:
                url = metadata.cover_urls["spotify_high"]
            elif quality == "medium" and "spotify_medium" in metadata.cover_urls:
                url = metadata.cover_urls["spotify_medium"]
            elif "spotify_low" in metadata.cover_urls:
                url = metadata.cover_urls["spotify_low"]
            
            if not url:
                return None
            
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.read()
                    return {
                        "data": data,
                        "mime_type": response.headers.get('content-type', 'image/jpeg'),
                        "size": len(data)
                    }
                    
        except Exception as e:
            logger.error(f"获取Spotify封面出错: {str(e)}")
        return None
        
    async def get_lyrics(self, metadata: MusicMetadata) -> Optional[Dict[str, Any]]:
        """
        获取歌词
        注意：Spotify的歌词API需要额外的授权，这里实现了基本结构
        要获取实际的歌词，需要更高级别的API访问权限
        """
        try:
            if "spotify" not in metadata.source_data:
                return None
                
            track = metadata.source_data["spotify"]
            track_id = track["id"]
            
            # 注意：这需要额外的API权限
            # lyrics = self.sp.track_lyrics(track_id)
            # if lyrics and "lyrics" in lyrics:
            #     return {
            #         "text": lyrics["lyrics"],
            #         "language": lyrics.get("language", "unknown"),
            #         "is_translated": False
            #     }
            
        except Exception as e:
            logger.error(f"获取Spotify歌词出错: {str(e)}")
        return None
