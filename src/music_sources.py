"""音乐数据源模块"""
import json
import time
import hashlib
import base64
import asyncio
from typing import Optional, Dict, Any
from abc import ABC
import aiohttp
import logging
import musicbrainzngs
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from fuzzywuzzy import fuzz

from .music_metadata import MusicMetadata

logger = logging.getLogger(__name__)

class MusicSource(ABC):
    """音乐数据源基类"""
    async def search(self, title: str, artist: str = None) -> Optional[MusicMetadata]:
        """搜索音乐信息"""
        raise NotImplementedError
    
    async def get_album_cover(self, album_id: str) -> Optional[bytes]:
        """获取专辑封面"""
        raise NotImplementedError

class NeteaseMusicSource(MusicSource):
    """网易云音乐数据源"""
    def __init__(self, api_key: str = None, api_secret: str = None, weight: float = 1.0):
        self.api_key = api_key
        self.api_secret = api_secret
        self.weight = weight
        self.base_url = "https://music.163.com/api"
    
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
            
            async with aiohttp.ClientSession() as session:
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
                                metadata.cover_url = best_match["album"]["picUrl"]
                                return metadata
        except Exception as e:
            logger.error(f"网易云音乐搜索出错: {str(e)}")
        return None

    async def get_album_cover(self, album_id: str) -> Optional[bytes]:
        """获取专辑封面"""
        try:
            if not album_id:
                return None
                
            url = f"https://music.163.com/api/album/{album_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data and "album" in data and "picUrl" in data["album"]:
                            pic_url = data["album"]["picUrl"]
                            async with session.get(pic_url) as pic_response:
                                if pic_response.status == 200:
                                    return await pic_response.read()
        except Exception as e:
            logger.error(f"获取网易云音乐封面出错: {str(e)}")
        return None

class MusicBrainzSource(MusicSource):
    """MusicBrainz数据源"""
    def __init__(self, app_name: str = "MusicTagger", version: str = "1.0", contact: str = "your@email.com"):
        musicbrainzngs.set_useragent(app_name, version, contact)
        self.max_retries = 3
        self.retry_delay = 1  # 秒

    async def _retry_operation(self, operation):
        """带重试机制的操作执行器"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    await asyncio.sleep(self.retry_delay * attempt)
                return await operation()
            except Exception as e:
                last_error = e
                logger.warning(f"MusicBrainz操作失败 (尝试 {attempt + 1}/{self.max_retries}): {str(e)}")
        raise last_error

    async def search(self, title: str, artist: str = None) -> Optional[MusicMetadata]:
        try:
            async def _do_search():
                query = f'recording:"{title}"'
                if artist:
                    query += f' AND artist:"{artist}"'

                result = musicbrainzngs.search_recordings(query=query, limit=5)
                
                if result and 'recording-list' in result:
                    recordings = result['recording-list']
                    if recordings:
                        best_match = recordings[0]
                        metadata = MusicMetadata(
                            title=best_match['title'],
                            artist=best_match['artist-credit'][0]['name'],
                            album=best_match.get('release-list', [{}])[0].get('title', '')
                        )
                        metadata.release_id = best_match.get('release-list', [{}])[0].get('id', '')
                        metadata.source = "musicbrainz"
                        
                        # 计算相似度
                        title_ratio = fuzz.ratio(title.lower(), metadata.title.lower())
                        artist_ratio = fuzz.ratio(artist.lower(), metadata.artist.lower()) if artist else 100
                        metadata.confidence = (title_ratio + artist_ratio) / 2
                        
                        return metadata
                return None

            return await self._retry_operation(_do_search)
        except Exception as e:
            logger.error(f"MusicBrainz搜索出错: {str(e)}")
        return None

class SpotifySource(MusicSource):
    """Spotify数据源"""
    def __init__(self, client_id: str, client_secret: str):
        self.sp = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=client_id,
                client_secret=client_secret
            )
        )

    async def search(self, title: str, artist: str = None) -> Optional[MusicMetadata]:
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
                
                # 获取封面URL
                if track['album']['images']:
                    metadata.cover_url = track['album']['images'][0]['url']
                
                # 计算相似度
                title_ratio = fuzz.ratio(title.lower(), metadata.title.lower())
                artist_ratio = fuzz.ratio(artist.lower(), metadata.artist.lower()) if artist else 100
                metadata.confidence = (title_ratio + artist_ratio) / 2
                
                return metadata
        except Exception as e:
            logger.error(f"Spotify搜索出错: {str(e)}")
        return None

class QQMusicSource(MusicSource):
    """QQ音乐数据源"""
    def __init__(self, api_key: str = None, weight: float = 1.0):
        self.api_key = api_key
        self.weight = weight
        self.base_url = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
    
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
            
            async with aiohttp.ClientSession() as session:
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
                                # 构建封面URL
                                album_mid = best_match["album"]["mid"]
                                metadata.cover_url = f"https://y.gtimg.cn/music/photo_new/T002R800x800M000{album_mid}.jpg"
                                return metadata
        except Exception as e:
            logger.error(f"QQ音乐搜索出错: {str(e)}")
        return None

    async def get_album_cover(self, album_mid: str) -> Optional[bytes]:
        """获取专辑封面"""
        try:
            if not album_mid:
                return None
                
            url = f"https://y.gtimg.cn/music/photo_new/T002R800x800M000{album_mid}.jpg"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.read()
        except Exception as e:
            logger.error(f"获取QQ音乐封面出错: {str(e)}")
        return None
