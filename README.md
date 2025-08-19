# Music Tagger

一个自动音乐标签管理工具，支持从多个数据源获取音乐元数据并更新音频文件标签。

## 特性

- 支持多个音乐数据源：
  - MusicBrainz
  - Spotify
  - 网易云音乐
  - QQ音乐
- 支持的音频格式：
  - FLAC
  - MP3
  - M4A
- 自动下载专辑封面
- 智能匹配算法
- 缓存机制减少API请求
- 异步处理提高性能
- 可配置的数据源权重
- 错误重试机制

## 安装

1. 克隆仓库：
```bash
git clone https://github.com/yourusername/music-tagger.git
cd music-tagger
```

2. 创建虚拟环境：
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate  # Windows
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

## 配置

1. 复制示例配置文件：
```bash
cp config.yaml.example config.yaml
```

2. 编辑 `config.yaml` 文件，配置数据源：
```yaml
global:
  min_confidence: 50
  require_confirmation: true
  search_timeout: 30
  source_weights:
    musicbrainz: 1.0
    spotify: 1.0
    netease: 0.8
    qqmusic: 0.8

musicbrainz:
  enabled: true
  app_name: YourAppName
  version: "1.0"
  contact: your@email.com
  weight: 1.0

# 其他数据源配置...
```

## 使用方法

处理单个目录：

```bash
python main.py
```

## 功能说明

1. **多数据源支持**：
   - 支持从多个数据源获取音乐信息
   - 智能合并和权重计算
   - 可自定义数据源优先级

2. **智能匹配**：
   - 使用模糊匹配算法
   - 考虑标题和艺术家相似度
   - 支持不同的匹配策略

3. **性能优化**：
   - 异步并发请求
   - 本地缓存机制
   - 错误重试和超时处理

4. **标签管理**：
   - 支持主流音频格式
   - 保留原有标签信息
   - 专辑封面下载和嵌入

## 开发

添加新的数据源：

1. 在 `music_sources.py` 中实现 `MusicSource` 接口
2. 在 `config.yaml` 中添加相应配置
3. 在 `music_tagger.py` 中注册新数据源

## 贡献

欢迎提交 Pull Request 或创建 Issue！

## 许可证

MIT License
