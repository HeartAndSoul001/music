"""音乐文件跟踪管理模块"""
import os
import json
import logging
import hashlib
from typing import Dict, Optional, Set
from pathlib import Path
import aiofiles

logger = logging.getLogger(__name__)

class FileTracker:
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = Path(cache_dir)
        self.track_file = self.cache_dir / "tracked_files.json"
        self.tracked_files: Dict[str, Dict] = {}
        self._load_tracked_files()
        
    def _load_tracked_files(self):
        """加载已追踪的文件记录"""
        try:
            if self.track_file.exists():
                with open(self.track_file, 'r', encoding='utf-8') as f:
                    self.tracked_files = json.load(f)
        except Exception as e:
            logger.error(f"加载文件追踪记录失败: {str(e)}")
            self.tracked_files = {}
            
    def _save_tracked_files(self):
        """保存文件追踪记录"""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self.track_file, 'w', encoding='utf-8') as f:
                json.dump(self.tracked_files, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存文件追踪记录失败: {str(e)}")
            
    async def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件的哈希值"""
        try:
            async with aiofiles.open(file_path, 'rb') as f:
                file_hash = hashlib.md5()
                chunk = await f.read(8192)
                while chunk:
                    file_hash.update(chunk)
                    chunk = await f.read(8192)
                return file_hash.hexdigest()
        except Exception as e:
            logger.error(f"计算文件哈希值失败 {file_path}: {str(e)}")
            return ""
            
    def is_file_tracked(self, file_path: str, file_hash: str) -> bool:
        """检查文件是否已被追踪且未发生变化"""
        if file_path not in self.tracked_files:
            return False
        return self.tracked_files[file_path].get('hash') == file_hash
        
    def track_file(self, file_path: str, file_hash: str, metadata: Dict):
        """记录文件追踪状态"""
        self.tracked_files[file_path] = {
            'hash': file_hash,
            'metadata': metadata
        }
        self._save_tracked_files()
        
    def get_tracked_metadata(self, file_path: str) -> Optional[Dict]:
        """获取已追踪文件的元数据"""
        if file_path in self.tracked_files:
            return self.tracked_files[file_path].get('metadata')
        return None
        
    def remove_missing_files(self, existing_files: Set[str]):
        """移除不存在的文件记录"""
        missing_files = set(self.tracked_files.keys()) - existing_files
        for file in missing_files:
            del self.tracked_files[file]
        if missing_files:
            self._save_tracked_files()
            
class LibraryOrganizer:
    def __init__(self, library_root: str, format_pattern: str):
        self.library_root = Path(library_root)
        self.format_pattern = format_pattern
        
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        # 替换 Windows 和 Unix 系统中的非法字符
        illegal_chars = '<>:"/\\|?*'
        for char in illegal_chars:
            filename = filename.replace(char, '_')
        return filename.strip()
        
    def get_organized_path(self, metadata: Dict) -> Path:
        """根据元数据生成组织后的路径"""
        try:
            # 获取并清理各个组件
            artist = self._sanitize_filename(metadata.get('artist', 'Unknown Artist'))
            album = self._sanitize_filename(metadata.get('album', 'Unknown Album'))
            title = self._sanitize_filename(metadata.get('title', 'Unknown Title'))
            
            # 使用格式模板生成路径
            path = self.format_pattern.format(
                artist=artist,
                album=album,
                title=title
            )
            
            return self.library_root / path
            
        except Exception as e:
            logger.error(f"生成组织路径失败: {str(e)}")
            return None
            
    async def organize_file(self, src_path: Path, metadata: Dict) -> Optional[Path]:
        """组织单个音乐文件"""
        try:
            # 获取目标路径
            dest_dir = self.get_organized_path(metadata)
            if not dest_dir:
                return None
                
            # 确保目标目录存在
            dest_dir.mkdir(parents=True, exist_ok=True)
            
            # 构建完整的目标路径（保持原始扩展名）
            if isinstance(src_path, str):
                src_path = Path(src_path)
            
            dest_path = dest_dir / src_path.name
            
            # 如果目标文件已存在，添加序号
            counter = 1
            while dest_path.exists():
                stem = dest_path.stem
                if " (" in stem:
                    stem = stem[:stem.rindex(" (")]
                dest_path = dest_dir / f"{stem} ({counter}){src_path.suffix}"
                counter += 1
                
            # 移动文件
            src_path.rename(dest_path)
            logger.info(f"已移动文件到: {dest_path}")
            return dest_path
            
        except Exception as e:
            logger.error(f"组织文件失败 {src_path}: {str(e)}")
            return None
