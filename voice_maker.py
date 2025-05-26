#!/usr/bin/env python3
import os
import argparse
from loguru import logger
from app.services import voice
from app.utils import utils
from app.config import config

def get_default_voice():
    """从配置文件获取默认语音设置"""
    # 优先使用配置文件中的ui.voice_name
    if config.ui.get("voice_name"):
        return config.ui.get("voice_name")
    # 其次使用Azure语音
    if config.azure.get("speech_key") and config.azure.get("speech_region"):
        return "zh-CN-XiaoyiNeural-Female"
    # 最后使用硅基流动语音
    elif config.siliconflow.get("api_key"):
        return "siliconflow:FunAudioLLM/CosyVoice2-0.5B:alex-Male"
    return None

def main():
    parser = argparse.ArgumentParser(description='生成配音文件')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--text', type=str, help='要转换为语音的文本')
    group.add_argument('--file', type=str, help='包含要转换文本的文件路径')
    
    parser.add_argument('--voice-name', type=str, help='语音名称，例如：zh-CN-XiaoyiNeural-Female')
    parser.add_argument('--voice-rate', type=float, default=1.0, help='语音速度，范围[0.25, 4.0]，默认1.0')
    parser.add_argument('--voice-volume', type=float, default=1.0, help='语音音量，范围[0.6, 5.0]，默认1.0')
    parser.add_argument('--output', type=str, help='输出的音频文件路径')
    
    args = parser.parse_args()
    
    # 获取文本内容
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                text = f.read().strip()
        except Exception as e:
            logger.error(f"读取文件失败：{str(e)}")
            return
    else:
        text = args.text.strip()
    
    # 如果没有指定语音，使用配置文件中的默认语音
    if not args.voice_name:
        args.voice_name = get_default_voice()
        if not args.voice_name:
            logger.error("未指定语音名称，且配置文件中未设置默认语音")
            return
    
    # 设置输出文件路径
    if not args.output:
        if args.file:
            # 如果是文件输入，在同目录下生成同名mp3文件
            output_dir = os.path.dirname(args.file)
            base_name = os.path.splitext(os.path.basename(args.file))[0]
            args.output = os.path.join(output_dir, f"{base_name}.mp3")
        else:
            # 如果是文本输入，在当前目录生成output.mp3
            args.output = "output.mp3"
    
    # 确保输出目录存在
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # 生成配音
    logger.info(f"开始生成配音，使用语音：{args.voice_name}")
    sub_maker = voice.tts(
        text=text,
        voice_name=args.voice_name,
        voice_rate=args.voice_rate,
        voice_file=args.output,
        voice_volume=args.voice_volume
    )
    
    if not sub_maker:
        logger.error("配音生成失败")
        return
    
    # 获取音频时长
    audio_duration = voice.get_audio_duration(sub_maker)
    logger.info(f"配音生成完成，输出文件：{args.output}，时长：{audio_duration}秒")

if __name__ == '__main__':
    main()