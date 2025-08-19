"""QQ音乐数据源模块"""
import logging
from typing import Optional, Dict, Any
import aiohttp

from .base import MusicSource
from music_metadata import MusicMetadata

logger = logging.getLogger(__name__)

class QQMusicSource(MusicSource):
    """QQ音乐数据源"""
    def __init__(self, api_key: str = None, weight: float = 1.0):
        self.api_key = api_key
        self.weight = weight
        self.base_url = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
        self.session = None
        
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
            query = f"{title}"
            if artist:
                query = f"{artist} {title}"
            
            params = {
                "w": query,
                "format": "json",
                "p": 1,
                "n": 5,
                "ct": 24,
                "new_json": 1,
                "remoteplace": "txt.yqq.center",
                "t": 0,  # 0: 单曲
                "aggr": 1,
                "cr": 1,
                "lossless": 0,
                "flag_qc": 0
            }
            
            session = await self._get_session()
            async with session.get(self.base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and "data" in data and "song" in data["data"] and "list" in data["data"]["song"]:
                        songs = data["data"]["song"]["list"]
                        if songs:
                            best_match = songs[0]
                            metadata = MusicMetadata(
                                title=best_match["title"],
                                artist=best_match["singer"][0]["name"],
                                album=best_match["album"]["title"]
                            )
                            metadata.source = "qqmusic"
                            metadata.source_data["qqmusic"] = best_match
                            
                            # 构建封面URL
                            album_mid = best_match["album"]["mid"]
                            cover_url = self._normalize_url(
                                f"https://y.gtimg.cn/music/photo_new/T002R800x800M000{album_mid}.jpg"
                            )
                            metadata.cover_urls["qqmusic"] = cover_url
                            if not metadata.cover_url:  # 如果还没有主封面，设置为主封面
                                metadata.cover_url = cover_url
                                
                            return metadata
                            
        except Exception as e:
            logger.error(f"QQ音乐搜索出错: {str(e)}")
        return None

    async def get_album_cover(self, metadata: MusicMetadata, quality: str = "high") -> Optional[Dict[str, Any]]:
        """获取专辑封面"""
        try:
            if "qqmusic" not in metadata.cover_urls:
                return None
                
            # QQ音乐的封面URL支持不同尺寸
            quality_sizes = {
                "low": "300x300",
                "medium": "500x500",
                "high": "800x800"
            }
            
            base_url = metadata.cover_urls["qqmusic"]
            size = quality_sizes.get(quality, quality_sizes["medium"])
            url = base_url.replace("800x800", size)
            
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
            logger.error(f"获取QQ音乐封面出错: {str(e)}")
        return None
        
    async def get_lyrics(self, metadata: MusicMetadata) -> Optional[Dict[str, Any]]:
        """获取歌词"""
        try:
            if "qqmusic" not in metadata.source_data:
                return None
                
            song_mid = metadata.source_data["qqmusic"].get("mid")
            if not song_mid:
                return None
                
            lyrics_url = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
            headers = {
                "Referer": "https://y.qq.com",
                "User-Agent": "Mozilla/5.0"
            }
            params = {
                "songmid": song_mid,
                "format": "json",
                "nobase64": 1
            }
            
            session = await self._get_session()
            async with session.get(lyrics_url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("retcode") == 0 and "lyric" in data:
                        lyric = data["lyric"]
                        trans_lyric = data.get("trans", "")
                        
                        result = lyric
                        if trans_lyric:
                            result += "\n[翻译歌词]\n" + trans_lyric
                            
                        return {
                            "text": result,
                            "language": "zh-CN",
                            "is_translated": bool(trans_lyric),
                            "source_language": "zh-CN"
                        }
                            
        except Exception as e:
            logger.error(f"获取QQ音乐歌词出错: {str(e)}")
        return None
