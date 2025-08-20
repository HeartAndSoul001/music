"""文字格式转换工具"""
import os
from typing import Optional
from opencc import OpenCC

class TextConverter:
    """文字格式转换器"""
    
    def __init__(self, config_name: str = "s2t"):
        """
        初始化转换器
        
        Args:
            config_name: OpenCC 配置名称
                s2t: 简体到繁体
                t2s: 繁体到简体
                s2tw: 简体到繁体（台湾）
                tw2s: 繁体（台湾）到简体
                s2hk: 简体到繁体（香港）
                hk2s: 繁体（香港）到简体
        """
        self.converter = OpenCC(config_name)
        
    def convert(self, text: Optional[str]) -> Optional[str]:
        """转换文字"""
        if not text:
            return text
        return self.converter.convert(text)
