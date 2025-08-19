"""音乐标签器配置管理模块"""
import os
import yaml
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class Config:
    def __init__(self, config_path: str = None):
        """初始化配置管理器"""
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        default_config = {
            'global': {
                'min_confidence': 50,
                'require_confirmation': True,
                'search_timeout': 30,
                'source_weights': {
                    'musicbrainz': 1.0,
                    'spotify': 1.0,
                    'netease': 0.8,
                    'qqmusic': 0.8
                }
            },
            'musicbrainz': {
                'enabled': True,
                'app_name': 'MusicTagger',
                'version': '1.0',
                'contact': 'your@email.com',
                'weight': 1.0
            },
            'spotify': {
                'enabled': False,
                'client_id': '',
                'client_secret': '',
                'weight': 1.0
            },
            'netease': {
                'enabled': True,
                'api_key': '',
                'api_secret': '',
                'weight': 0.8
            },
            'qqmusic': {
                'enabled': True,
                'api_key': '',
                'weight': 0.8
            }
        }

        try:
            # 确保配置文件目录存在
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            # 如果配置文件不存在，创建默认配置文件
            if not os.path.exists(self.config_path):
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(default_config, f, allow_unicode=True, default_flow_style=False)
                return default_config
                
            # 读取现有配置文件
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            if not config:
                return default_config
                
            # 合并默认配置和用户配置
            merged_config = default_config.copy()
            for key, value in config.items():
                if isinstance(value, dict) and key in merged_config:
                    merged_config[key].update(value)
                else:
                    merged_config[key] = value
                    
            return merged_config
            
        except Exception as e:
            logger.error(f"加载配置文件失败: {str(e)}")
            logger.info("使用默认配置")
            return default_config

    def get_source_config(self, source_name: str) -> Optional[Dict[str, Any]]:
        """获取指定数据源的配置"""
        return self.config.get(source_name)

    def is_source_enabled(self, source_name: str) -> bool:
        """检查数据源是否启用"""
        source_config = self.get_source_config(source_name)
        return source_config is not None and source_config.get('enabled', False)

    @property
    def min_confidence(self) -> float:
        """获取最小置信度阈值"""
        return self.config.get('global', {}).get('min_confidence', 50)

    @property
    def require_confirmation(self) -> bool:
        """是否需要用户确认"""
        return self.config.get('global', {}).get('require_confirmation', True)

    def get_enabled_sources(self) -> Dict[str, Dict[str, Any]]:
        """获取所有启用的数据源配置"""
        return {name: config for name, config in self.config.items()
                if name != 'global' and config.get('enabled', False)}

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项值
        
        Args:
            key: 配置项键名
            default: 默认值
            
        Returns:
            配置项值，如果不存在则返回默认值
        """
        # 支持嵌套键，如 "global.timeout"
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value
