"""MusicBrainz数据源模块"""
import logging
from typing import Optional, Dict, Any
import asyncio
import aiohttp
import musicbrainzngs

from .base import MusicSource
from music_metadata import MusicMetadata

logger = logging.getLogger(__name__)

class MusicBrainzSource(MusicSource):
    """MusicBrainz数据源"""
    def __init__(self, app_name: str = "MusicTagger", version: str = "1.0", 
                 contact: str = "your@email.com", weight: float = 1.0):
        self.weight = weight
        self.max_retries = 3
        self.retry_delay = 1  # 秒
        self.session = None
        musicbrainzngs.set_useragent(app_name, version, contact)
        
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
        """搜索音乐信息"""
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
                        metadata.source_data["musicbrainz"] = best_match
                        
                        # 尝试获取发行信息中的封面链接
                        if metadata.release_id:
                            try:
                                release_info = musicbrainzngs.get_image_list(metadata.release_id)
                                if release_info and 'images' in release_info:
                                    image = release_info['images'][0]
                                    metadata.cover_urls["musicbrainz"] = self._normalize_url(image['image'])
                                    if not metadata.cover_url:  # 如果还没有主封面
                                        metadata.cover_url = metadata.cover_urls["musicbrainz"]
                            except Exception as e:
                                logger.warning(f"获取MusicBrainz封面URL失败: {str(e)}")
                        
                        return metadata
                return None

            return await self._retry_operation(_do_search)
        except Exception as e:
            logger.error(f"MusicBrainz搜索出错: {str(e)}")
        return None

    async def get_album_cover(self, metadata: MusicMetadata, quality: str = "high") -> Optional[Dict[str, Any]]:
        """获取专辑封面"""
        try:
            if metadata.release_id:
                # 尝试从缓存的 URL 获取
                if "musicbrainz" in metadata.cover_urls:
                    url = metadata.cover_urls["musicbrainz"]
                else:
                    # 重新获取封面列表
                    cover_art = await self._retry_operation(
                        lambda: musicbrainzngs.get_image_list(metadata.release_id)
                    )
                    if not cover_art or 'images' not in cover_art:
                        return None
                    
                    # 选择最佳质量的图片
                    best_image = None
                    if quality == "high":
                        # 选择最大尺寸的前视图
                        best_image = max(
                            (img for img in cover_art['images'] if 'Front' in img.get('types', [])),
                            key=lambda x: int(x.get('thumbnails', {}).get('large', '0')),
                            default=cover_art['images'][0]
                        )
                    else:
                        # 选择中等或小尺寸的图片
                        best_image = next(
                            (img for img in cover_art['images'] if 'Front' in img.get('types', [])),
                            cover_art['images'][0]
                        )
                    
                    url = self._normalize_url(best_image['image'])
                    metadata.cover_urls["musicbrainz"] = url
                
                # 下载图片
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
            logger.error(f"获取MusicBrainz封面出错: {str(e)}")
        return None
        
    async def get_lyrics(self, metadata: MusicMetadata) -> Optional[Dict[str, Any]]:
        """获取歌词（MusicBrainz本身不提供歌词，但会尝试从关联的外部链接获取）"""
        try:
            if "musicbrainz" not in metadata.source_data:
                return None
                
            # MusicBrainz 通过 relationships 提供歌词链接
            recording_data = metadata.source_data["musicbrainz"]
            if "relations" in recording_data:
                for relation in recording_data["relations"]:
                    if relation["type"] == "lyrics":
                        url = relation.get("url", {}).get("resource")
                        if url:
                            session = await self._get_session()
                            async with session.get(url) as response:
                                if response.status == 200:
                                    text = await response.text()
                                    return {
                                        "text": text,
                                        "language": "unknown",
                                        "is_translated": False,
                                        "source": "musicbrainz_related"
                                    }
                                    
        except Exception as e:
            logger.error(f"获取MusicBrainz歌词出错: {str(e)}")
        return None
