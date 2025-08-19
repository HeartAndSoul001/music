"""网易云音乐数据源模块"""
import logging
import json
import base64
import hashlib
import time
from typing import Optional, Dict, Any
import aiohttp

from music_metadata import MusicMetadata
from .base import MusicSource

logger = logging.getLogger(__name__)

class NeteaseMusicSource(MusicSource):
    """网易云音乐数据源"""
    def __init__(self, api_key: str = None, api_secret: str = None, weight: float = 1.0):
        self.api_key = api_key
        self.api_secret = api_secret
        self.weight = weight
        self.base_url = "https://music.163.com/api"
        self.session = None
        
    def _generate_params(self, data: Dict[str, Any]) -> Dict[str, str]:
        """生成API调用参数"""
        text = json.dumps(data)
        params = {
            "params": base64.b64encode(text.encode()).decode(),
            "timestamp": str(int(time.time() * 1000))
        }
        if self.api_secret:
            raw = params["params"] + params["timestamp"] + (self.api_secret or "")
            params["sign"] = hashlib.md5(raw.encode()).hexdigest()
        return params
        
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
            search_url = f"{self.base_url}/search/get"
            query = f"{title}"
            if artist:
                query = f"{artist} {title}"
            
            params = self._generate_params({
                "s": query,
                "type": 1,  # 1: 单曲
                "offset": 0,
                "limit": 5
            })
            
            session = await self._get_session()
            async with session.post(search_url, data=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and "result" in data and "songs" in data["result"]:
                        songs = data["result"]["songs"]
                        if songs:
                            best_match = songs[0]
                            metadata = MusicMetadata(
                                title=best_match["name"],
                                artist=best_match["artists"][0]["name"],
                                album=best_match["album"]["name"]
                            )
                            metadata.source = "netease"
                            metadata.source_data["netease"] = best_match
                            if "album" in best_match and "picUrl" in best_match["album"]:
                                cover_url = self._normalize_url(best_match["album"]["picUrl"])
                                metadata.cover_urls["netease"] = cover_url
                                metadata.cover_url = cover_url  # 设置为主封面
                            return metadata
        except Exception as e:
            logger.error(f"网易云音乐搜索出错: {str(e)}")
        return None

    async def get_album_cover(self, metadata: MusicMetadata, quality: str = "high") -> Optional[Dict[str, Any]]:
        """获取专辑封面"""
        try:
            if "netease" not in metadata.cover_urls:
                return None
                
            # 网易云音乐的封面URL支持不同尺寸
            # 通过修改URL参数来获取不同质量的图片
            quality_params = {
                "low": "?param=200y200",
                "medium": "?param=400y400",
                "high": "?param=1000y1000"
            }
            
            base_url = metadata.cover_urls["netease"].split("?")[0]
            url = base_url + quality_params.get(quality, quality_params["medium"])
            
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
            logger.error(f"获取网易云音乐封面出错: {str(e)}")
        return None
        
    async def get_lyrics(self, metadata: MusicMetadata) -> Optional[Dict[str, Any]]:
        """获取歌词"""
        try:
            if "netease" not in metadata.source_data:
                return None
                
            song_id = metadata.source_data["netease"].get("id")
            if not song_id:
                return None
                
            lyrics_url = f"{self.base_url}/lyric"
            params = self._generate_params({
                "id": song_id,
                "lv": 1,
                "kv": 1,
                "tv": -1
            })
            
            session = await self._get_session()
            async with session.post(lyrics_url, data=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if not data:
                        return None
                            
                    lyrics = []
                    # 原文歌词
                    if "lrc" in data and "lyric" in data["lrc"]:
                        lyrics.append(data["lrc"]["lyric"])
                            
                    # 翻译歌词（如果有）
                    if "tlyric" in data and "lyric" in data["tlyric"]:
                        lyrics.append("\n[翻译歌词]\n" + data["tlyric"]["lyric"])
                            
                    if lyrics:
                        return {
                            "text": "\n".join(lyrics),
                            "language": "zh-CN",
                            "is_translated": len(lyrics) > 1,
                            "source_language": "zh-CN" if len(lyrics) == 1 else "en"
                        }
                            
        except Exception as e:
            logger.error(f"获取网易云音乐歌词出错: {str(e)}")
        return None
