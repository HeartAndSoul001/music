"""Spotify缓存处理器"""
import os
from pathlib import Path
from spotipy.cache_handler import CacheHandler

class MusicTaggerCacheHandler(CacheHandler):
    """自定义的 Spotify 缓存处理器"""
    def __init__(self, cache_path: str = None):
        if not cache_path:
            cache_path = os.path.expanduser("~/.music_tagger/cache/spotify_token.cache")
        self.cache_path = cache_path
        # 确保缓存目录存在
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
    
    def get_cached_token(self):
        """获取缓存的令牌"""
        try:
            if os.path.exists(self.cache_path):
                with open(self.cache_path, 'r') as f:
                    return f.read()
        except Exception:
            return None
    
    def save_token_to_cache(self, token_info):
        """保存令牌到缓存"""
        try:
            with open(self.cache_path, 'w') as f:
                f.write(token_info)
        except Exception:
            pass
