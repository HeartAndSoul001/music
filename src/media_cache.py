"""媒体缓存管理器"""
import os
import json
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Union
import aiofiles

logger = logging.getLogger(__name__)

class MediaCache:
    def __init__(self, cache_dir: str = ".cache"):
        """
        初始化媒体缓存管理器
        
        Args:
            cache_dir: 缓存根目录
        """
        self.cache_dir = Path(cache_dir)
        self.covers_dir = self.cache_dir / "covers"
        self.lyrics_dir = self.cache_dir / "lyrics"
        self._init_dirs()
        
    def _init_dirs(self):
        """初始化缓存目录"""
        self.covers_dir.mkdir(parents=True, exist_ok=True)
        self.lyrics_dir.mkdir(parents=True, exist_ok=True)
        
    def _generate_cache_key(self, artist: str, title: str, album: str = "") -> str:
        """生成缓存键"""
        key = f"{artist}_{title}"
        if album:
            key += f"_{album}"
        return hashlib.md5(key.encode()).hexdigest()
        
    async def save_cover(self, artist: str, title: str, album: str, data: bytes,
                  source: str, quality: str = "high") -> str:
        """
        保存封面图片
        
        Args:
            artist: 艺术家名
            title: 歌曲名
            album: 专辑名
            data: 图片数据
            source: 数据源名称
            quality: 图片质量（low/medium/high）
            
        Returns:
            缓存文件路径
        """
        try:
            key = self._generate_cache_key(artist, title, album)
            file_path = self.covers_dir / f"{key}_{source}_{quality}.jpg"
            
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(data)
                
            # 保存元数据
            meta_path = self.covers_dir / f"{key}.json"
            meta_data = {}
            if meta_path.exists():
                async with aiofiles.open(meta_path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    meta_data = json.loads(content)
                    
            meta_data[f"{source}_{quality}"] = {
                "path": str(file_path),
                "size": len(data),
                "source": source,
                "quality": quality
            }
            
            async with aiofiles.open(meta_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(meta_data, ensure_ascii=False, indent=2))
                
            return str(file_path)
            
        except Exception as e:
            logger.error(f"保存封面失败: {str(e)}")
            return ""
            
    async def get_cover(self, artist: str, title: str, album: str = "",
                 source: str = None, quality: str = None) -> Optional[bytes]:
        """
        获取缓存的封面
        
        Args:
            artist: 艺术家名
            title: 歌曲名
            album: 专辑名
            source: 指定数据源
            quality: 指定质量级别
            
        Returns:
            封面数据，如果不存在则返回 None
        """
        try:
            key = self._generate_cache_key(artist, title, album)
            meta_path = self.covers_dir / f"{key}.json"
            
            if not meta_path.exists():
                return None
                
            async with aiofiles.open(meta_path, "r", encoding="utf-8") as f:
                content = await f.read()
                meta_data = json.loads(content)
            
            # 根据条件选择最合适的封面
            best_cover = None
            if source and quality:
                # 精确匹配
                cover_key = f"{source}_{quality}"
                if cover_key in meta_data:
                    best_cover = meta_data[cover_key]
            else:
                # 启发式选择
                covers = []
                for k, v in meta_data.items():
                    score = 0
                    if source and v["source"] == source:
                        score += 2
                    if quality and v["quality"] == quality:
                        score += 1
                    if quality == "high":
                        score += v["size"] / 1000000  # 文件大小奖励
                    covers.append((score, v))
                
                if covers:
                    best_cover = max(covers, key=lambda x: x[0])[1]
            
            if best_cover and os.path.exists(best_cover["path"]):
                async with aiofiles.open(best_cover["path"], "rb") as f:
                    return await f.read()
                    
        except Exception as e:
            logger.error(f"获取缓存的封面失败: {str(e)}")
        return None
        
    async def save_lyrics(self, artist: str, title: str, lyrics: str,
                   source: str, language: str = "cn") -> str:
        """
        保存歌词
        
        Args:
            artist: 艺术家名
            title: 歌曲名
            lyrics: 歌词文本
            source: 数据源名称
            language: 歌词语言
            
        Returns:
            缓存文件路径
        """
        try:
            key = self._generate_cache_key(artist, title)
            file_path = self.lyrics_dir / f"{key}_{source}_{language}.txt"
            
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(lyrics)
                
            # 保存元数据
            meta_path = self.lyrics_dir / f"{key}.json"
            meta_data = {}
            if meta_path.exists():
                async with aiofiles.open(meta_path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    meta_data = json.loads(content)
                    
            meta_data[f"{source}_{language}"] = {
                "path": str(file_path),
                "source": source,
                "language": language
            }
            
            async with aiofiles.open(meta_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(meta_data, ensure_ascii=False, indent=2))
                
            return str(file_path)
            
        except Exception as e:
            logger.error(f"保存歌词失败: {str(e)}")
            return ""
            
    async def get_lyrics(self, artist: str, title: str,
                  source: str = None, language: str = None) -> Optional[str]:
        """
        获取缓存的歌词
        
        Args:
            artist: 艺术家名
            title: 歌曲名
            source: 指定数据源
            language: 指定语言
            
        Returns:
            歌词文本，如果不存在则返回 None
        """
        try:
            key = self._generate_cache_key(artist, title)
            meta_path = self.lyrics_dir / f"{key}.json"
            
            if not meta_path.exists():
                return None
                
            async with aiofiles.open(meta_path, "r", encoding="utf-8") as f:
                content = await f.read()
                meta_data = json.loads(content)
            
            # 选择最合适的歌词
            best_lyrics = None
            if source and language:
                # 精确匹配
                lyrics_key = f"{source}_{language}"
                if lyrics_key in meta_data:
                    best_lyrics = meta_data[lyrics_key]
            else:
                # 优先选择指定语言或来源的歌词
                lyrics_list = []
                for k, v in meta_data.items():
                    score = 0
                    if source and v["source"] == source:
                        score += 2
                    if language and v["language"] == language:
                        score += 2
                    lyrics_list.append((score, v))
                
                if lyrics_list:
                    best_lyrics = max(lyrics_list, key=lambda x: x[0])[1]
            
            if best_lyrics and os.path.exists(best_lyrics["path"]):
                async with aiofiles.open(best_lyrics["path"], "r", encoding="utf-8") as f:
                    return await f.read()
                    
        except Exception as e:
            logger.error(f"获取缓存的歌词失败: {str(e)}")
        return None
