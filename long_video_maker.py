#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Long Video Maker Script

这个脚本专门用于制作长视频，使用本地视频素材，并针对长视频特别优化了处理参数。
默认情况下，视频素材应放在 storage/long/video_materials 目录下。

Usage:
    python long_video_maker.py --task-path /path/to/task --title "视频标题" [options]

Options:
    --task-path TEXT           指定任务路径，该路径下需要有 script.txt 文件（纯文案内容），生成的视频也会保存在这里
    --title TEXT               指定视频标题，将显示在视频开头2秒
    --materials TEXT           指定视频素材文件夹路径 [default: storage/long/video_materials]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Union

from loguru import logger

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import config
from app.models.schema import VideoParams, VideoConcatMode, VideoAspect, VideoTransitionMode
from app.services import task as tm
from app.utils import utils


def setup_logger():
    """配置日志记录器"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
    )
    log_file = utils.storage_dir("logs", create=True)
    logger.add(
        os.path.join(log_file, "long_video_maker_{time}.log"),
        rotation="100 MB",
        level="DEBUG",
    )


def create_video_params(title: str, materials_path: Optional[str] = None) -> VideoParams:
    """创建针对长视频优化的VideoParams对象"""
    # 视频设置 - 使用本地视频源
    video_source = "local"
    
    # 从配置文件读取语音设置
    voice_name = config.ui.get("voice_name", "zh-CN-XiaoyiNeural-Female")
    voice_rate = float(config.ui.get("voice_rate", 1.0))  # 降低语速

    # 字幕设置
    subtitle_position = config.ui.get("subtitle_position", "bottom")
    custom_position = float(config.ui.get("custom_position", 70.0))
    font_name = config.ui.get("font_name", "STHeitiMedium.ttc")
    font_size = int(config.ui.get("font_size", 60))
    text_fore_color = config.ui.get("text_fore_color", "#FFFFFF")

    # 视频格式设置 - 默认使用横屏16:9
    video_aspect = VideoAspect.landscape.value

    # 其他设置
    video_language = config.ui.get("video_language", "")
    paragraph_number = int(config.ui.get("paragraph_number", 1))

    # 获取本地视频素材路径列表
    video_dir = materials_path if materials_path else utils.storage_dir(os.path.join("long", "video_materials"))
    video_files = []
    if os.path.exists(video_dir):
        for file in os.listdir(video_dir):
            if file.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
                video_files.append({
                    "url": os.path.join(video_dir, file)
                })

    if not video_files:
        logger.warning(f"没有在 {video_dir} 找到视频文件")

    logger.info(f"使用配置:")
    logger.info(f"  - 视频源: 本地文件")
    logger.info(f"  - 语音: {voice_name} (语速: {voice_rate})")
    logger.info(f"  - 字幕位置: {subtitle_position} (距顶部 {custom_position}%)")
    logger.info(f"  - 视频比例: {video_aspect}")

    return VideoParams(
        video_subject=title,
        video_script="",  # 将由LLM生成
        video_aspect=video_aspect,
        video_source=video_source,
        video_materials=video_files,  # 使用本地视频文件
        voice_name=voice_name,
        voice_rate=voice_rate,
        video_language=video_language,
        paragraph_number=paragraph_number,
        video_count=1,  # 只生成一个视频
        video_concat_mode=VideoConcatMode.sequential.value,  # 使用顺序拼接
        video_transition_mode=VideoTransitionMode.fade_in.value,
        video_clip_duration=10,  # 增加片段时长到10秒
        n_threads=8,  # 增加处理线程数
        bgm_type="random",
        bgm_volume=0.1,  # 降低背景音乐音量
        # 字幕设置
        subtitle_enabled=True,
        subtitle_position=subtitle_position,
        custom_position=custom_position,
        font_name=font_name,
        font_size=font_size,
        text_fore_color=text_fore_color,
    )


def split_script(script: str, max_chars: int = 1000) -> List[str]:
    """将文案分割成多个小段"""
    # 按句号分割文本
    sentences = script.split('。')
    segments = []
    current_segment = ''
    
    for sentence in sentences:
        if not sentence.strip():
            continue
        # 确保句子以句号结尾
        sentence = sentence.strip() + '。'
        
        if len(current_segment) + len(sentence) <= max_chars:
            current_segment += sentence
        else:
            if current_segment:
                segments.append(current_segment)
            current_segment = sentence
    
    if current_segment:
        segments.append(current_segment)
    
    return segments

def process_title(
    index: int,
    total: int,
    params: VideoParams,
    task_path: Optional[str] = None,
) -> Dict:
    """处理单个标题生成视频，采用分段处理策略"""
    task_id = utils.get_uuid()
    logger.info(f"任务ID: {task_id}")

    task_dir = task_path if task_path else utils.task_dir(task_id)
    os.makedirs(task_dir, exist_ok=True)

    # 读取文案
    script_file = os.path.join(task_dir, "script.txt")
    if not os.path.exists(script_file):
        logger.error(f"文案文件不存在: {script_file}")
        return {"success": False, "task_id": task_id, "error": "文案文件不存在"}

    try:
        with open(script_file, "r", encoding="utf-8") as f:
            script = f.read().strip()
            if not script:
                logger.error(f"文案文件为空: {script_file}")
                return {"success": False, "task_id": task_id, "error": "文案文件为空"}
            
            logger.info(f"[{index+1}/{total}] 处理标题: {params.video_subject}")
    except Exception as e:
        logger.error(f"读取文案文件失败: {e}")
        return {"success": False, "task_id": task_id, "error": f"读取文案文件失败: {e}"}

    # 分割文案成多个小段
    script_segments = split_script(script)
    logger.info(f"文案已分割为 {len(script_segments)} 个片段")

    # 分段处理视频
    segment_results = []
    for i, segment_script in enumerate(script_segments):
        logger.info(f"处理第 {i+1}/{len(script_segments)} 个片段")
        
        # 创建片段参数
        segment_params = VideoParams(**params.dict())
        segment_params.video_script = segment_script
        segment_params.show_title = True if i == 0 else False  # 只在第一个片段显示标题
        segment_params.title_duration = 2 if i == 0 else 0

        try:
            # 处理当前片段
            result = tm.start(task_id=f"{task_id}_segment_{i}", params=segment_params, stop_at="video")

            if not result or "videos" not in result:
                logger.error(f"生成片段 {i+1} 失败")
                continue

            segment_results.append(result)
            
            # 清理临时文件以释放内存
            for temp_file in result.get("temp_files", []):
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception as e:
                    logger.warning(f"清理临时文件失败: {e}")

        except Exception as e:
            logger.error(f"处理片段 {i+1} 时出错: {e}")
            continue

        # 强制垃圾回收
        import gc
        gc.collect()

    if not segment_results:
        logger.error("所有片段处理失败")
        return {"success": False, "task_id": task_id, "title": params.video_subject, "error": "视频生成失败"}

    # 合并所有片段的结果
    final_result = {
        "success": True,
        "task_id": task_id,
        "title": params.video_subject,
        "videos": [],
    }

    for result in segment_results:
        final_result["videos"].extend(result.get("videos", []))

    # 保存最终结果
    with open(os.path.join(task_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(final_result, f, ensure_ascii=False, indent=2)

    logger.success(f"成功生成视频: {params.video_subject}")
    logger.info(f"视频保存在: {task_dir}")

    return final_result


def main():
    """主函数，处理所有标题"""
    parser = argparse.ArgumentParser(description="长视频制作器")
    parser.add_argument("--task-path", required=True, help="指定任务路径，该路径下需要有 script.txt 文件，生成的视频也会保存在这里")
    parser.add_argument("--title", required=True, help="指定视频标题，将显示在视频开头2秒")
    parser.add_argument("--materials", type=str, help="指定视频素材文件夹路径，默认为 storage/long/video_materials")

    args = parser.parse_args()

    # 设置日志记录器
    setup_logger()

    # 处理视频
    params = create_video_params(title=args.title, materials_path=args.materials)
    result = process_title(0, 1, params, task_path=args.task_path)

    # 保存结果
    batch_dir = utils.storage_dir("batch", create=True)
    batch_results_file = os.path.join(batch_dir, "long_video_results.json")
    with open(batch_results_file, "w", encoding="utf-8") as f:
        json.dump([result], f, ensure_ascii=False, indent=2)

    # 打印结果
    if result.get("success", False):
        logger.success("视频生成成功")
    else:
        logger.error(f"视频生成失败: {result.get('error', '未知错误')}")
    logger.info(f"结果保存在 {batch_results_file}")


if __name__ == "__main__":
    main()