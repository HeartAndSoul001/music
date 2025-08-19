#!/usr/bin/env python3

import asyncio
from src.music_tagger import MusicTagger

async def main():
    tagger = MusicTagger()
    music_dir = "/Users/wzq/Downloads/2004-七里香"  # 替换为您的音乐文件夹路径
    await tagger.process_directory(music_dir)

if __name__ == "__main__":
    asyncio.run(main())
