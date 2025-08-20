import os
import sys
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
import shutil

from music_metadata import MusicMetadata
from file_status import FileStatus
from music_sources.base import MusicSource
from music_sources.netease import NeteaseMusicSource
from music_sources.qq import QQMusicSource
from music_sources.musicbrainz import MusicBrainzSource
from music_sources.spotify import SpotifySource
from text_converter import TextConverter

# 启用嵌套异步循环支持
nest_asyncio.apply()

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from config import Config
from cache import Cache
from media_cache import MediaCache

class MusicTagger:
    def __init__(self, config_path: str = None):
        """初始化音乐标签器"""
        self.config = Config(config_path)
        self.sources = self._initialize_sources()
        self.session = None
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.cache = Cache()
        self.media_cache = MediaCache()
        self.file_status = FileStatus()
        
        # 创建文字转换器
        text_format = self.config.get("global.text_format", "simplified")
        if text_format == "traditional":
            self.text_converter = TextConverter("s2t")  # 简体转繁体
        else:
            self.text_converter = TextConverter("t2s")  # 繁体转简体
    
    def _initialize_sources(self) -> List[MusicSource]:
        """初始化已启用的数据源"""
        sources = []
        enabled_sources = self.config.get_enabled_sources()
        
        # 获取全局源权重配置
        source_weights = self.config.get("global.source_weights", {})
        
        # 初始化 MusicBrainz 数据源
        if self.config.is_source_enabled('musicbrainz'):
            mb_config = self.config.get_source_config('musicbrainz')
            if mb_config.get('app_name') and mb_config.get('contact'):
                source = MusicBrainzSource(
                    app_name=mb_config['app_name'],
                    version=mb_config.get('version', '1.0'),
                    contact=mb_config['contact'],
                    weight=source_weights.get('musicbrainz', 1.0)  # 使用全局权重
                )
                sources.append(source)
                logger.info("MusicBrainz 数据源已启用")
            else:
                logger.warning("MusicBrainz 配置不完整，已禁用")
        
        # 初始化 Spotify 数据源
        if self.config.is_source_enabled('spotify'):
            spotify_config = self.config.get_source_config('spotify')
            if spotify_config.get('client_id') and spotify_config.get('client_secret'):
                source = SpotifySource(
                    client_id=spotify_config['client_id'],
                    client_secret=spotify_config['client_secret'],
                    weight=source_weights.get('spotify', 1.0)  # 使用全局权重
                )
                sources.append(source)
                logger.info("Spotify 数据源已启用")
            else:
                logger.warning("Spotify 配置不完整，已禁用")
        
        # 初始化网易云音乐数据源
        if self.config.is_source_enabled('netease'):
            netease_config = self.config.get_source_config('netease')
            if netease_config.get('api_key') and netease_config.get('api_secret'):
                source = NeteaseMusicSource(
                    api_key=netease_config['api_key'],
                    api_secret=netease_config['api_secret'],
                    weight=source_weights.get('netease', 1.0)  # 使用全局权重
                )
                sources.append(source)
                logger.info("网易云音乐数据源已启用")
            else:
                logger.warning("网易云音乐配置不完整，已禁用")
        
        # 初始化 QQ 音乐数据源
        if self.config.is_source_enabled('qqmusic'):
            qq_config = self.config.get_source_config('qqmusic')
            if qq_config.get('api_key'):
                source = QQMusicSource(
                    api_key=qq_config['api_key'],
                    weight=source_weights.get('qqmusic', 1.0)  # 使用全局权重
                )
                sources.append(source)
                logger.info("QQ音乐数据源已启用")
            else:
                logger.warning("QQ音乐配置不完整，已禁用")
        
        if not sources:
            logger.warning("没有可用的数据源，请检查配置")
            
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
        # 移除序号前缀（如 "0013-"）
        filename = re.sub(r'^\d+-', '', filename)
        # 移除扩展名
        filename = os.path.splitext(filename)[0]
        # 尝试分割艺术家和标题
        parts = filename.split('-', 1)
        if len(parts) == 2:
            return parts[1].strip(), parts[0].strip()
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

    async def download_cover_art(self, metadata: MusicMetadata, quality: str = None) -> Optional[bytes]:
        """从多个数据源下载专辑封面，支持质量选择和本地缓存"""
        try:
            # 获取配置
            quality = quality or self.config.get("cover_art.quality", "high")
            save_to_directory = self.config.get("cover_art.save_to_directory", True)
            preferred_format = self.config.get("cover_art.preferred_format", "jpg")
            
            # 首先检查本地缓存
            cached_cover = await self.media_cache.get_cover(
                artist=metadata.artist,
                title=metadata.title,
                album=metadata.album,
                quality=quality
            )
            if cached_cover:
                logger.info("使用缓存的封面图片")
                if save_to_directory:
                    await self._save_cover_to_directory(metadata, cached_cover, preferred_format)
                return cached_cover

            # 尝试从主要数据源获取封面
            cover_data = await self._try_get_cover_from_sources(self.sources, metadata, quality)
            
            # 如果主要数据源都失败了，尝试备用数据源
            if not cover_data:
                additional_sources = self.config.get("cover_art.additional_sources", [])
                for source_name in additional_sources:
                    try:
                        source = self._get_additional_source(source_name)
                        if source:
                            cover_data = await source.get_album_cover(metadata, quality)
                            if cover_data and cover_data.get("data"):
                                break
                    except Exception as e:
                        logger.warning(f"从备用数据源 {source_name} 获取封面失败: {str(e)}")
            
            if cover_data and cover_data.get("data"):
                # 保存到缓存
                await self.media_cache.save_cover(
                    artist=metadata.artist,
                    title=metadata.title,
                    album=metadata.album,
                    data=cover_data["data"],
                    source=cover_data.get("source", "unknown"),
                    quality=quality
                )
                
                # 如果配置了保存到目录，则保存
                if save_to_directory:
                    await self._save_cover_to_directory(metadata, cover_data["data"], preferred_format)
                
                return cover_data["data"]
            
            logger.warning("无法从任何数据源获取封面")
            return None

        except Exception as e:
            logger.error(f"下载封面时出错: {str(e)}")
            return None

    async def _try_get_cover_from_sources(self, sources, metadata: MusicMetadata, quality: str) -> Optional[Dict]:
        """从多个数据源尝试获取封面"""
        for source in sources:
            try:
                cover_data = await source.get_album_cover(metadata, quality)
                if cover_data and cover_data.get("data"):
                    logger.info(f"成功从 {source.__class__.__name__} 获取封面")
                    return cover_data
            except Exception as e:
                logger.warning(f"从 {source.__class__.__name__} 获取封面失败: {str(e)}")
        return None

    def _get_additional_source(self, source_name: str) -> Optional[MusicSource]:
        """获取额外的音乐数据源实例"""
        # 这里可以根据需要添加更多的数据源
        sources = {
            "QQ音乐": QQMusicSource,
            "网易云音乐": NeteaseMusicSource,
            # 可以添加更多数据源
        }
        source_class = sources.get(source_name)
        if source_class:
            try:
                # 获取对应的配置
                config = self.config.get_source_config(source_name.lower().replace("音乐", ""))
                if config:
                    return source_class(**config)
            except Exception as e:
                logger.warning(f"创建数据源 {source_name} 失败: {str(e)}")
        return None

    async def _save_cover_to_directory(self, metadata: MusicMetadata, cover_data: bytes, format: str = "jpg") -> None:
        """将封面保存到专辑目录"""
        try:
            # 构建目标目录路径
            target_dir = Path(self.config.get("directories.target"))
            album_dir = target_dir / self._clean_name(metadata.artist) / self._clean_name(metadata.album)
            
            # 确保目录存在
            album_dir.mkdir(parents=True, exist_ok=True)
            
            # 确定文件名
            cover_filename = self.config.get("cover_art.filename", "cover")
            cover_path = album_dir / f"{cover_filename}.{format.lower()}"
            
            # 保存封面文件
            with open(cover_path, "wb") as f:
                f.write(cover_data)
            logger.info(f"封面已保存到: {cover_path}")
            
        except Exception as e:
            logger.error(f"保存封面到目录失败: {str(e)}")
            
    async def get_lyrics(self, metadata: MusicMetadata) -> Optional[str]:
        """获取歌词，支持多数据源和本地缓存"""
        try:
            # 首先检查本地缓存
            cached_lyrics = await self.media_cache.get_lyrics(
                artist=metadata.artist,
                title=metadata.title
            )
            if cached_lyrics:
                logger.info("使用缓存的歌词")
                # 进行文字转换
                return self.text_converter.convert(cached_lyrics)

            # 从各个数据源获取歌词
            for source in self.sources:
                try:
                    lyrics_data = await source.get_lyrics(metadata)
                    if lyrics_data and lyrics_data.get("text"):
                        lyrics_text = lyrics_data["text"]
                        # 进行文字转换
                        converted_lyrics = self.text_converter.convert(lyrics_text)
                        # 保存到缓存
                        await self.media_cache.save_lyrics(
                            artist=metadata.artist,
                            title=metadata.title,
                            lyrics=converted_lyrics,
                            source=source.__class__.__name__.lower(),
                            language=lyrics_data.get("language", "unknown")
                        )
                        logger.info(f"成功从 {source.__class__.__name__} 获取歌词")
                        return converted_lyrics
                except Exception as e:
                    logger.warning(f"从 {source.__class__.__name__} 获取歌词失败: {str(e)}")
                    continue

            logger.warning("无法从任何数据源获取歌词")
            return None

        except Exception as e:
            logger.error(f"获取歌词时出错: {str(e)}")
            return None
                
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

            # 进行文字格式转换
            metadata.title = self.text_converter.convert(metadata.title)
            metadata.artist = self.text_converter.convert(metadata.artist)
            metadata.album = self.text_converter.convert(metadata.album)

            # 获取封面和歌词
            cover_data = await self.download_cover_art(metadata)
            lyrics = await self.get_lyrics(metadata)

            # 根据文件类型处理
            if file_path.lower().endswith('.flac'):
                audio = FLAC(file_path)
                
                # 更新 FLAC 标签
                audio['TITLE'] = metadata.title
                audio['ARTIST'] = metadata.artist
                audio['ALBUM'] = metadata.album
                
                if lyrics:
                    audio['LYRICS'] = lyrics

                # 添加封面
                if cover_data:
                    image = Picture()
                    image.type = 3  # 封面图片
                    image.mime = "image/jpeg"
                    image.desc = "Cover"
                    image.data = cover_data
                    audio.add_picture(image)

            elif file_path.lower().endswith('.wav'):
                # WAV 文件使用 ID3 标签
                from mutagen.wave import WAVE
                audio = WAVE(file_path)
                
                # 如果文件没有 ID3 标签，添加一个
                if not audio.tags:
                    from mutagen.id3 import ID3, TIT2, TPE1, TALB, USLT
                    audio.tags = ID3()
                
                # 更新标签
                audio.tags.add(TIT2(encoding=3, text=metadata.title))
                audio.tags.add(TPE1(encoding=3, text=metadata.artist))
                audio.tags.add(TALB(encoding=3, text=metadata.album))
                
                # 添加歌词
                if lyrics:
                    audio.tags.add(USLT(encoding=3, lang='eng', desc='', text=lyrics))
                
                # 添加封面
                if cover_data:
                    from mutagen.id3 import APIC
                    audio.tags.add(APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,  # 封面图片
                        desc='Cover',
                        data=cover_data
                    ))

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
                
                # 添加歌词
                if lyrics:
                    try:
                        audio['lyrics'] = lyrics
                    except Exception as e:
                        logger.warning(f"添加歌词失败: {str(e)}")

            # 保存更改
            audio.save()
            logger.info(f"成功更新文件: {file_path}")
            return True

        except Exception as e:
            logger.error(f"处理文件时出错 {file_path}: {str(e)}")
            return False

    def _get_music_files(self, directory: Path) -> List[Path]:
        """递归获取所有音乐文件"""
        music_files = []
        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in [".mp3", ".m4a", ".flac", ".wav"]:
                music_files.append(file_path)
        return music_files

    async def _organize_file(self, file_path: str, metadata: MusicMetadata) -> None:
        """根据元数据整理文件"""
        try:
            logger.info(f"开始整理文件: {file_path}")
            logger.info(f"元数据信息: {metadata}")
            
            source_path = Path(file_path)
            if not source_path.exists():
                logger.error(f"源文件不存在: {source_path}")
                return
                
            # 从配置文件获取目标目录
            root_dir = Path(self.config.get("directories.target"))
            # 确保目标目录存在
            root_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"使用目标目录: {root_dir}")
            
            # 从配置文件获取目录结构模式
            dir_pattern = self.config.get("directories.directory_pattern",
                                      "{artist}/{album}/{track_number}. {title}")
            logger.info(f"使用目录模式: {dir_pattern}")
            
            # 将元数据应用到目录模式
            dir_parts = {}
            dir_parts["artist"] = metadata.artist or "Unknown Artist"
            dir_parts["album"] = metadata.album or "Unknown Album"
            dir_parts["title"] = metadata.title or os.path.splitext(source_path.name)[0]
            dir_parts["year"] = getattr(metadata, 'year', '')
            dir_parts["track_number"] = str(getattr(metadata, 'track_number', '00')).zfill(2)
            
            logger.info(f"目录部分信息: {dir_parts}")
            
            # 净化文件名中的非法字符
            def clean_name(name: str) -> str:
                return re.sub(r'[<>:"/\\|?*]', '_', name)
            
            # 净化并替换路径中的变量
            for key, value in dir_parts.items():
                dir_parts[key] = self._clean_name(str(value))
            
            try:
                # 应用目录结构模式
                relative_path = dir_pattern.format(**dir_parts)
                logger.info(f"生成的相对路径: {relative_path}")
                
                # 添加原始文件扩展名
                relative_path = relative_path + source_path.suffix
                target_path = root_dir / relative_path
                logger.info(f"完整目标路径: {target_path}")
                
                # 创建必要的目录
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 如果目标文件已存在，添加序号
                counter = 1
                original_target_path = target_path
                while target_path.exists():
                    stem = original_target_path.stem
                    new_filename = f"{stem}_{counter}{source_path.suffix}"
                    target_path = original_target_path.parent / new_filename
                    counter += 1
                
                # 移动文件
                logger.info(f"移动文件:\n  从: {source_path}\n  到: {target_path}")
                shutil.move(str(source_path), str(target_path))
                logger.info(f"文件移动成功")
                
                # 检查并删除空的源目录
                source_dir = source_path.parent
                if source_dir.exists() and not any(source_dir.iterdir()):
                    source_dir.rmdir()
                    logger.info(f"删除空目录: {source_dir}")
                    
            except KeyError as e:
                logger.error(f"目录结构模式中包含未知变量: {e}")
            except FileNotFoundError as e:
                logger.error(f"文件不存在: {e}")
            except PermissionError as e:
                logger.error(f"没有足够的权限: {e}")
            except Exception as e:
                logger.error(f"移动文件时发生错误: {e}")
            
        except Exception as e:
            logger.error(f"整理文件时出错 {file_path}: {str(e)}")

    async def process_directory(self, directory_path: str, organize_files: bool = True):
        """处理整个目录的音乐文件，支持递归和文件整理"""
        await self.initialize()
        try:
            # 设置日志级别
            if '--debug' in sys.argv:
                logging.getLogger().setLevel(logging.DEBUG)
                
            root_dir = Path(directory_path)
            music_files = self._get_music_files(root_dir)
            logger.debug(f"Found music files: {[str(f) for f in music_files]}")
            
            if not music_files:
                logger.warning(f"在目录 {directory_path} 中未找到音乐文件")
                return
            
            logger.info(f"找到 {len(music_files)} 个音乐文件")
            
            # 使用异步进度条
            for file_path in tqdm(music_files, desc="处理音乐文件"):
                file_path_str = str(file_path)
                
                # 检查文件是否已处理
                if self.file_status.is_file_processed(file_path_str):
                    logger.info(f"跳过已处理的文件: {file_path_str}")
                    continue
                
                # 处理文件
                artist, title = self.parse_filename(file_path.stem)
                if not title:
                    logger.warning(f"无法从文件名解析音乐信息: {file_path.name}")
                    continue
                
                metadata = await self.search_track_info(title, artist)
                if metadata:
                    if await self.process_file(file_path_str):
                        # 更新文件状态
                        self.file_status.update_file_status(file_path_str, {
                            "title": metadata.title,
                            "artist": metadata.artist,
                            "album": metadata.album,
                            "source": metadata.source
                        })
                        
                        # 如果需要整理文件
                        if organize_files:
                            await self._organize_file(file_path_str, metadata)
            
            # 保存文件状态
            await self.file_status.save_status()
            
            # 保存状态后完成
            if organize_files:
                logger.info("文件整理完成")
            
        finally:
            await self.close()
            
    def _clean_name(self, name: str) -> str:
        """净化文件名中的非法字符"""
        # 移除或替换非法字符
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        # 移除首尾空白字符
        name = name.strip()
        # 确保名称非空
        return name if name else "Unknown"

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="音乐文件自动刮削工具")
    parser.add_argument("--no-organize", action="store_true", help="不整理文件夹结构")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    args = parser.parse_args()
    
    # 设置日志级别
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Debug mode enabled")
    
    # 创建标签处理器
    tagger = MusicTagger(config_path=args.config)
    
    # 从配置文件获取源目录
    source_dir = tagger.config.get("directories.source")
    if not source_dir:
        logger.error("配置文件中未设置源目录路径 (directories.source)")
        sys.exit(1)
    
    # 确保源目录存在
    if not os.path.exists(source_dir):
        logger.error(f"源目录不存在: {source_dir}")
        sys.exit(1)
    
    # 运行异步主函数，默认启用文件整理
    organize = not args.no_organize
    logging.debug(f"File organization is {'enabled' if organize else 'disabled'}")
    asyncio.run(tagger.process_directory(source_dir, organize_files=organize))
