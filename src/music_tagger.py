import os
import logging
import asyncio
import nest_asyncio
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import musicbrainzngs
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from mutagen.flac import FLAC, Picture
from mutagen import File
from mutagen.easyid3 import EasyID3
from fuzzywuzzy import fuzz
from tqdm import tqdm
import aiohttp
import json
from concurrent.futures import ThreadPoolExecutor

from .config import Config
from .music_metadata import MusicMetadata
from .music_sources import (
    MusicSource,
    NeteaseMusicSource,
    QQMusicSource,
    MusicBrainzSource,
    SpotifySource
)

# 启用嵌套异步循环支持
nest_asyncio.apply()

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from .config import Config
from .cache import Cache

class MusicTagger:
    def __init__(self, config_path: str = None):
        """初始化音乐标签器"""
        self.config = Config(config_path)
        self.sources = self._initialize_sources()
        self.session = None
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.cache = Cache()
    
    def _initialize_sources(self) -> List[MusicSource]:
        """初始化已启用的数据源"""
        sources = []
        enabled_sources = self.config.get_enabled_sources()
        
        # 初始化 MusicBrainz 数据源
        if self.config.is_source_enabled('musicbrainz'):
            mb_config = self.config.get_source_config('musicbrainz')
            source = MusicBrainzSource(
                app_name=mb_config.get('app_name', 'MusicTagger'),
                version=mb_config.get('version', '1.0'),
                contact=mb_config.get('contact', 'your@email.com')
            )
            sources.append(source)
        
        # 初始化 Spotify 数据源
        if self.config.is_source_enabled('spotify'):
            spotify_config = self.config.get_source_config('spotify')
            if spotify_config.get('client_id') and spotify_config.get('client_secret'):
                source = SpotifySource(
                    client_id=spotify_config['client_id'],
                    client_secret=spotify_config['client_secret']
                )
                sources.append(source)
            else:
                logger.warning("Spotify 配置不完整，已禁用 Spotify 数据源")
        
        # 初始化网易云音乐数据源
        if self.config.is_source_enabled('netease'):
            netease_config = self.config.get_source_config('netease')
            source = NeteaseMusicSource(
                api_key=netease_config.get('api_key'),
                api_secret=netease_config.get('api_secret'),
                weight=netease_config.get('weight', 1.0)
            )
            sources.append(source)
        
        # 初始化 QQ 音乐数据源
        if self.config.is_source_enabled('qqmusic'):
            qq_config = self.config.get_source_config('qqmusic')
            source = QQMusicSource(
                api_key=qq_config.get('api_key'),
                weight=qq_config.get('weight', 1.0)
            )
            sources.append(source)
        
        return sources
        
    async def initialize(self):
        """初始化异步会话"""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """关闭异步会话"""
        if self.session:
            await self.session.close()
            self.session = None

    def parse_filename(self, filename: str) -> Tuple[str, str]:
        """从文件名解析艺术家和标题信息"""
        # 移除序号
        filename = re.sub(r'^\d+\.\s*', '', filename)
        # 尝试分割艺术家和标题
        parts = filename.split(' - ', 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        return None, filename.strip()

    def _create_cache_key(self, title: str, artist: str = None) -> str:
        """创建缓存键"""
        return f"search_{title}_{artist if artist else 'unknown'}"

    async def search_track_info(self, title: str, artist: str = None) -> Optional[MusicMetadata]:
        """
        从多个来源搜索音乐信息
        使用异步并发、缓存和模糊匹配
        """
        if not title:
            return None

        # 检查缓存
        cache_key = self._create_cache_key(title, artist)
        cached_result = self.cache.get(cache_key)
        if cached_result:
            # 如果有缓存结果，还原为 MusicMetadata 对象
            try:
                metadata = MusicMetadata(
                    title=cached_result["title"],
                    artist=cached_result["artist"],
                    album=cached_result["album"]
                )
                metadata.confidence = cached_result["confidence"]
                metadata.source = cached_result["source"]
                metadata.release_id = cached_result.get("release_id")
                metadata.cover_url = cached_result.get("cover_url")
                return metadata
            except Exception as e:
                logger.warning(f"还原缓存数据失败: {str(e)}")

        try:
            # 并发搜索所有启用的源，带错误处理
            results = []
            tasks = []

            # 创建所有搜索任务
            for source in self.sources:
                task = asyncio.create_task(self._safe_search(source, title, artist))
                tasks.append(task)

            # 等待所有任务完成或超时
            try:
                completed_tasks = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=self.config.get("search_timeout", 30)  # 默认30秒超时
                )
                
                # 处理结果
                for result in completed_tasks:
                    if isinstance(result, Exception):
                        logger.warning(f"搜索时出错: {str(result)}")
                    elif result is not None:
                        results.append(result)
            
            except asyncio.TimeoutError:
                logger.warning("搜索操作超时")
                # 取消未完成的任务
                for task in tasks:
                    if not task.done():
                        task.cancel()
            
            if not results:
                return None
            
            # 选择最佳结果
            best_result = self._select_best_result(results)
            if not best_result or best_result.confidence < self.config.min_confidence:
                return None
            
            # 缓存结果
            self.cache.set(cache_key, {
                "title": best_result.title,
                "artist": best_result.artist,
                "album": best_result.album,
                "confidence": best_result.confidence,
                "source": best_result.source,
                "release_id": best_result.release_id,
                "cover_url": best_result.cover_url
            })
            
            return best_result
            
        except Exception as e:
            logger.error(f"搜索音乐信息时出错: {str(e)}")
            return None

    async def _safe_search(self, source: MusicSource, title: str, artist: str = None) -> Optional[MusicMetadata]:
        """带错误处理的安全搜索"""
        try:
            return await source.search(title, artist)
        except Exception as e:
            logger.error(f"数据源 {source.__class__.__name__} 搜索失败: {str(e)}")
            return None

    def _select_best_result(self, results: List[MusicMetadata]) -> Optional[MusicMetadata]:
        """
        智能选择最佳结果
        
        考虑因素：
        1. 置信度
        2. 源的权重
        3. 是否有完整信息（专辑、封面等）
        """
        if not results:
            return None
            
        # 计算加权得分
        for result in results:
            # 基础分数是置信度
            score = result.confidence
            
            # 来源权重
            source_weights = self.config.get("source_weights", {})
            source_weight = source_weights.get(result.source, 1.0)
            score *= source_weight
            
            # 完整性奖励
            if result.album:
                score *= 1.1
            if result.cover_url or result.release_id:
                score *= 1.1
                
            # 保存计算的得分
            result.weighted_score = score
            
        # 返回得分最高的结果
        return max(results, key=lambda x: getattr(x, 'weighted_score', 0))

    async def download_cover_art(self, metadata: MusicMetadata) -> Optional[bytes]:
        """下载专辑封面，带重试机制"""
        max_retries = 3
        retry_delay = 1  # 秒
        
        for attempt in range(max_retries):
            try:
                if metadata.cover_url:
                    async with self.session.get(metadata.cover_url) as response:
                        if response.status == 200:
                            return await response.read()
                elif metadata.release_id:
                    # 检查缓存
                    cache_key = f"cover_{metadata.release_id}"
                    cached_cover = self.cache.get(cache_key)
                    if cached_cover and "url" in cached_cover:
                        async with self.session.get(cached_cover["url"]) as response:
                            if response.status == 200:
                                return await response.read()
                    
                    # 如果缓存不存在或失效，重新获取
                    cover_art = musicbrainzngs.get_image_list(metadata.release_id)
                    if cover_art and 'images' in cover_art:
                        image_url = cover_art['images'][0]['image']
                        # 缓存封面URL
                        self.cache.set(cache_key, {"url": image_url})
                        async with self.session.get(image_url) as response:
                            if response.status == 200:
                                return await response.read()
                            
            except aiohttp.ClientError as e:
                if attempt < max_retries - 1:
                    delay = retry_delay * (attempt + 1)
                    logger.warning(f"下载封面失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"下载封面失败，已达最大重试次数: {str(e)}")
            except Exception as e:
                logger.error(f"下载封面时出错: {str(e)}")
                break
                
        return None

    async def process_file(self, file_path: str) -> bool:
        """处理单个音乐文件"""
        try:
            # 获取文件名作为搜索依据
            filename = Path(file_path).stem
            artist, title = self.parse_filename(filename)
            
            # 搜索音乐信息
            metadata = await self.search_track_info(title, artist)
            if not metadata:
                logger.warning(f"未找到音乐信息: {filename}")
                return False

            # 根据配置决定是否需要用户确认
            if self.config.require_confirmation:
                print(f"\n找到匹配: {metadata}")
                response = input("是否接受这个匹配? [Y/n] ").lower()
                if response and response != 'y':
                    return False

            # 根据文件类型处理
            if file_path.lower().endswith('.flac'):
                audio = FLAC(file_path)
                
                # 更新 FLAC 标签
                audio['TITLE'] = metadata.title
                audio['ARTIST'] = metadata.artist
                audio['ALBUM'] = metadata.album

                # 下载并添加封面
                cover_data = await self.download_cover_art(metadata)
                if cover_data:
                    image = Picture()
                    image.type = 3  # 封面图片
                    image.mime = "image/jpeg"
                    image.desc = "Cover"
                    image.data = cover_data
                    audio.add_picture(image)

            else:  # MP3 或其他格式
                audio = File(file_path, easy=True)
                if audio is None:
                    logger.warning(f"不支持的文件格式: {file_path}")
                    return False

                # 如果文件没有 ID3 标签，添加一个
                if not isinstance(audio, EasyID3):
                    audio = EasyID3()
                    audio.save(file_path)

                # 更新标签
                audio['title'] = metadata.title
                audio['artist'] = metadata.artist
                audio['album'] = metadata.album

            # 保存更改
            audio.save()
            logger.info(f"成功更新文件: {file_path}")
            return True

        except Exception as e:
            logger.error(f"处理文件时出错 {file_path}: {str(e)}")
            return False

    async def process_directory(self, directory_path: str):
        """处理整个目录的音乐文件"""
        await self.initialize()
        try:
            directory = Path(directory_path)
            music_files = list(directory.glob('*.mp3')) + list(directory.glob('*.m4a')) + list(directory.glob('*.flac'))
            
            logger.info(f"找到 {len(music_files)} 个音乐文件")
            
            # 使用异步进度条
            for file_path in tqdm(music_files, desc="处理音乐文件"):
                await self.process_file(str(file_path))
        finally:
            await self.close()

if __name__ == "__main__":
    # 使用示例
    tagger = MusicTagger()
    music_dir = "/Users/wzq/Downloads/2004-七里香"  # 替换为您的音乐文件夹路径
    
    # 运行异步主函数
    asyncio.run(tagger.process_directory(music_dir))
