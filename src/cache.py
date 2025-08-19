"""缓存模块，用于缓存API请求结果"""
import json
import logging

logger = logging.getLogger(__name__)
import os
from pathlib import Path
import time
from typing import Optional, Dict, Any

class Cache:
    def __init__(self, cache_dir: str = ".cache", expire_days: int = 30):
        """
        初始化缓存
        
        Args:
            cache_dir: 缓存目录路径
            expire_days: 缓存过期天数
        """
        self.cache_dir = Path(cache_dir)
        self.expire_days = expire_days
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_file(self, key: str) -> Path:
        """获取缓存文件路径"""
        # 使用 key 的 hash 作为文件名以避免文件名过长或包含非法字符
        from hashlib import md5
        filename = md5(key.encode()).hexdigest() + ".json"
        return self.cache_dir / filename
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的数据
        
        Args:
            key: 缓存键
            
        Returns:
            缓存的数据，如果不存在或已过期则返回 None
        """
        cache_file = self._get_cache_file(key)
        if not cache_file.exists():
            return None
            
        try:
            with cache_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 检查是否过期
            if time.time() - data["timestamp"] > self.expire_days * 24 * 3600:
                cache_file.unlink()
                return None
                
            return data["content"]
        except Exception:
            if cache_file.exists():
                cache_file.unlink()
            return None
    
    def set(self, key: str, value: Dict[str, Any]):
        """
        设置缓存数据
        
        Args:
            key: 缓存键
            value: 要缓存的数据
        """
        cache_file = self._get_cache_file(key)
        data = {
            "timestamp": time.time(),
            "content": value
        }
        
        try:
            with cache_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"写入缓存失败: {str(e)}")
