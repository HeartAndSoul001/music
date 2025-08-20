"""文件状态追踪模块"""
import os
import json
import aiofiles
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

class FileStatus:
    """追踪音乐文件的处理状态"""
    
    def __init__(self, status_file: str = ".music_status.json"):
        self.status_file = status_file
        self.status_data: Dict[str, Dict[str, Any]] = {}
        self._load_status()
    
    def _load_status(self):
        """加载状态文件"""
        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    self.status_data = json.load(f)
        except Exception as e:
            print(f"加载状态文件失败: {e}")
            self.status_data = {}
    
    async def save_status(self):
        """保存状态文件"""
        try:
            async with aiofiles.open(self.status_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self.status_data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"保存状态文件失败: {e}")
    
    def is_file_processed(self, file_path: str) -> bool:
        """检查文件是否已处理"""
        abs_path = str(Path(file_path).resolve())
        file_stat = os.stat(file_path)
        
        if abs_path in self.status_data:
            file_info = self.status_data[abs_path]
            # 检查文件修改时间和大小是否变化
            if (file_info['mtime'] == file_stat.st_mtime and 
                file_info['size'] == file_stat.st_size):
                return True
        return False
    
    def update_file_status(self, file_path: str, metadata: Optional[Dict[str, Any]] = None):
        """更新文件状态"""
        abs_path = str(Path(file_path).resolve())
        file_stat = os.stat(file_path)
        
        self.status_data[abs_path] = {
            'mtime': file_stat.st_mtime,
            'size': file_stat.st_size,
            'processed_at': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
