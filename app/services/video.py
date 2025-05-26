import glob
import itertools
import os
import random
import gc
import shutil
from typing import List
from loguru import logger
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    afx,
    concatenate_videoclips,
)
from moviepy.video.tools.subtitles import SubtitlesClip
from PIL import ImageFont

from app.models import const
from app.models.schema import (
    MaterialInfo,
    VideoAspect,
    VideoConcatMode,
    VideoParams,
    VideoTransitionMode,
)
from app.services.utils import video_effects
from app.utils import utils

class SubClippedVideoClip:
    def __init__(self, file_path, start_time=None, end_time=None, width=None, height=None, duration=None):
        self.file_path = file_path
        self.start_time = start_time
        self.end_time = end_time
        self.width = width
        self.height = height
        if duration is None:
            self.duration = end_time - start_time
        else:
            self.duration = duration

    def __str__(self):
        return f"SubClippedVideoClip(file_path={self.file_path}, start_time={self.start_time}, end_time={self.end_time}, duration={self.duration}, width={self.width}, height={self.height})"


audio_codec = "aac"
video_codec = "libx264"
fps = 30

def close_clip(clip):
    if clip is None:
        return
        
    try:
        # close main resources
        if hasattr(clip, 'reader') and clip.reader is not None:
            clip.reader.close()
            
        # close audio resources
        if hasattr(clip, 'audio') and clip.audio is not None:
            if hasattr(clip.audio, 'reader') and clip.audio.reader is not None:
                clip.audio.reader.close()
            del clip.audio
            
        # close mask resources
        if hasattr(clip, 'mask') and clip.mask is not None:
            if hasattr(clip.mask, 'reader') and clip.mask.reader is not None:
                clip.mask.reader.close()
            del clip.mask
            
        # handle child clips in composite clips
        if hasattr(clip, 'clips') and clip.clips:
            for child_clip in clip.clips:
                if child_clip is not clip:  # avoid possible circular references
                    close_clip(child_clip)
            
        # clear clip list
        if hasattr(clip, 'clips'):
            clip.clips = []
            
    except Exception as e:
        logger.error(f"failed to close clip: {str(e)}")
    
    del clip
    gc.collect()

def delete_files(files: List[str] | str):
    if isinstance(files, str):
        files = [files]
        
    for file in files:
        try:
            os.remove(file)
        except:
            pass

def get_bgm_file(bgm_type: str = "random", bgm_file: str = ""):
    if not bgm_type:
        return ""

    if bgm_file and os.path.exists(bgm_file):
        return bgm_file

    if bgm_type == "random":
        suffix = "*.mp3"
        song_dir = utils.song_dir()
        files = glob.glob(os.path.join(song_dir, suffix))
        return random.choice(files)

    return ""


def combine_videos(
    combined_video_path: str,
    video_paths: List[str],
    audio_file: str,
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_concat_mode: VideoConcatMode = VideoConcatMode.random,
    video_transition_mode: VideoTransitionMode = None,
    max_clip_duration: int = 5,
    threads: int = 2,
) -> str:
    audio_clip = AudioFileClip(audio_file)
    audio_duration = audio_clip.duration
    logger.info(f"audio duration: {audio_duration} seconds")
    # Required duration of each clip
    req_dur = audio_duration / len(video_paths)
    req_dur = max_clip_duration
    logger.info(f"maximum clip duration: {req_dur} seconds")
    output_dir = os.path.dirname(combined_video_path)

    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()

    # 创建临时目录存储处理后的视频片段
    temp_dir = os.path.join(output_dir, "temp_clips")
    os.makedirs(temp_dir, exist_ok=True)
    
    processed_clip_paths = []
    video_duration = 0
    
    # 逐个处理视频文件
    for i, video_path in enumerate(video_paths):
        try:
            # 加载视频并获取基本信息
            clip = VideoFileClip(video_path)
            clip_duration = clip.duration
            clip_w, clip_h = clip.size
            
            # 计算调整后的尺寸
            if clip_w / clip_h > video_width / video_height:
                new_width = video_width
                new_height = int(clip_h * (video_width / clip_w))
            else:
                new_height = video_height
                new_width = int(clip_w * (video_height / clip_h))
            
            # 处理视频片段
            start_time = 0
            while start_time < clip_duration:
                end_time = min(start_time + max_clip_duration, clip_duration)
                
                # 创建子片段
                subclip = clip.subclip(start_time, end_time)
                resized_clip = subclip.resize((new_width, new_height))
                
                # 创建背景并合成
                color_clip = ColorClip(size=(video_width, video_height), color=(0, 0, 0))
                color_clip = color_clip.set_duration(resized_clip.duration)
                
                # 计算居中位置
                x_offset = (video_width - new_width) // 2
                y_offset = (video_height - new_height) // 2
                
                # 合成视频
                composite_clip = CompositeVideoClip(
                    [color_clip, resized_clip.set_position((x_offset, y_offset))]
                )
                
                # 保存处理后的片段
                temp_clip_path = os.path.join(temp_dir, f"clip_{i}_{start_time}.mp4")
                composite_clip.write_videofile(
                    temp_clip_path,
                    codec='libx264',
                    audio=False,
                    threads=threads,
                    preset='ultrafast',
                    logger=None
                )
                
                processed_clip_paths.append(temp_clip_path)
                video_duration += composite_clip.duration
                
                # 释放内存
                close_clip(subclip)
                close_clip(resized_clip)
                close_clip(color_clip)
                close_clip(composite_clip)
                
                start_time = end_time
                if video_concat_mode.value == VideoConcatMode.sequential.value:
                    break
            
            # 释放原始视频内存
            close_clip(clip)
            
            # 强制垃圾回收
            gc.collect()
            
        except Exception as e:
            logger.error(f"处理视频文件失败: {video_path}, 错误: {str(e)}")
            continue

    # 随机打乱处理后的片段顺序，并确保相邻片段不重复
    if video_concat_mode.value == VideoConcatMode.random.value:
        # 如果片段数量大于1，确保相邻片段不重复
        if len(processed_clip_paths) > 1:
            shuffled_paths = []
            available_paths = processed_clip_paths.copy()
            
            # 选择第一个片段
            first_clip = random.choice(available_paths)
            shuffled_paths.append(first_clip)
            available_paths.remove(first_clip)
            
            # 选择剩余片段，避免相邻重复
            while available_paths:
                # 如果只剩最后一个片段，且它与第一个片段相同，则与倒数第二个交换
                if len(available_paths) == 1 and available_paths[0] == shuffled_paths[0]:
                    shuffled_paths[-1], available_paths[0] = available_paths[0], shuffled_paths[-1]
                
                # 从可用片段中随机选择一个不同于前一个的片段
                candidates = [p for p in available_paths if p != shuffled_paths[-1]]
                if not candidates:  # 如果没有其他选择，就用剩下的任意一个
                    candidates = available_paths
                
                next_clip = random.choice(candidates)
                shuffled_paths.append(next_clip)
                available_paths.remove(next_clip)
            
            processed_clip_paths = shuffled_paths
        else:
            random.shuffle(processed_clip_paths)
        
    logger.debug(f"总共处理的视频片段数: {len(processed_clip_paths)}")
    
    # 合并视频片段
    logger.info("开始合并视频片段")
    if not processed_clip_paths:
        logger.warning("没有可用的视频片段")
        return combined_video_path
    
    # 如果只有一个片段，直接使用
    if len(processed_clip_paths) == 1:
        logger.info("只有一个视频片段，直接使用")
        shutil.copy(processed_clip_paths[0], combined_video_path)
        # 清理临时文件
        delete_files(processed_clip_paths)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return combined_video_path
    
    # 使用分批合并策略减少内存占用
    temp_merged_video = os.path.join(output_dir, "temp_merged.mp4")
    temp_merged_next = os.path.join(output_dir, "temp_merged_next.mp4")
    
    # 复制第一个片段作为初始合并视频
    shutil.copy(processed_clip_paths[0], temp_merged_video)
    
    # 分批合并视频片段，每次只处理两个片段
    batch_size = 2
    for i in range(1, len(processed_clip_paths), batch_size):
        logger.info(f"合并片段 {i}/{len(processed_clip_paths)-1}")
        
        try:
            # 加载当前基础视频
            base_clip = VideoFileClip(temp_merged_video)
            
            # 加载并处理当前批次的片段
            batch_clips = []
            for j in range(i, min(i + batch_size, len(processed_clip_paths))):
                next_clip = VideoFileClip(processed_clip_paths[j])
            
                # 添加转场效果
                if video_transition_mode and video_transition_mode.value != VideoTransitionMode.none.value:
                    shuffle_side = random.choice(["left", "right", "top", "bottom"])
                    if video_transition_mode.value == VideoTransitionMode.fade_in.value:
                        next_clip = video_effects.fadein_transition(next_clip, 1)
                    elif video_transition_mode.value == VideoTransitionMode.fade_out.value:
                        next_clip = video_effects.fadeout_transition(next_clip, 1)
                    elif video_transition_mode.value == VideoTransitionMode.slide_in.value:
                        next_clip = video_effects.slidein_transition(next_clip, 1, shuffle_side)
                    elif video_transition_mode.value == VideoTransitionMode.slide_out.value:
                        next_clip = video_effects.slideout_transition(next_clip, 1, shuffle_side)
                    elif video_transition_mode.value == VideoTransitionMode.shuffle.value:
                        transition_funcs = [
                            lambda c: video_effects.fadein_transition(c, 1),
                            lambda c: video_effects.fadeout_transition(c, 1),
                            lambda c: video_effects.slidein_transition(c, 1, shuffle_side),
                            lambda c: video_effects.slideout_transition(c, 1, shuffle_side),
                        ]
                        next_clip = random.choice(transition_funcs)(next_clip)
                
                batch_clips.append(next_clip)
            
            # 合并当前批次的片段
            if batch_clips:
                clips_to_merge = [base_clip] + batch_clips
                merged_clip = concatenate_videoclips(clips_to_merge)
                
                # 保存合并结果
                merged_clip.write_videofile(
                    temp_merged_next,
                    codec='libx264',
                    audio=False,
                    threads=threads,
                    preset='ultrafast',
                    logger=None
                )
                
                # 释放内存
                close_clip(base_clip)
                for clip in batch_clips:
                    close_clip(clip)
                close_clip(merged_clip)
                
                # 更新基础文件
                os.remove(temp_merged_video)
                os.rename(temp_merged_next, temp_merged_video)
                
                # 强制垃圾回收
                gc.collect()
                
                # 清空当前批次
                batch_clips = []
            
        except Exception as e:
            logger.error(f"合并视频片段失败: {str(e)}")
            continue
    
    # 完成合并，移动到最终位置
    if os.path.exists(temp_merged_video):
        shutil.move(temp_merged_video, combined_video_path)
    
    # 清理临时文件
    delete_files(processed_clip_paths)
    shutil.rmtree(temp_dir, ignore_errors=True)
    
    # 添加音频
    try:
        logger.info("添加音频到视频")
        video_clip = VideoFileClip(combined_video_path)
        
        # 如果视频时长小于音频时长，循环视频直到匹配音频时长
        if video_duration < audio_duration:
            logger.warning(f"视频时长 ({video_duration:.2f}s) 小于音频时长 ({audio_duration:.2f}s)，循环视频以匹配音频长度")
            repeat_times = int(audio_duration / video_duration) + 1
            video_clip = concatenate_videoclips([video_clip] * repeat_times)
        
        # 裁剪视频以匹配音频时长
        if video_clip.duration > audio_duration:
            video_clip = video_clip.subclip(0, audio_duration)
        
        # 裁剪音频以匹配视频时长
        if audio_clip.duration > video_clip.duration:
            audio_clip = audio_clip.subclip(0, video_clip.duration)
        
        # 合成音视频
        final_clip = video_clip.set_audio(audio_clip)
        
        # 保存最终结果
        temp_final = os.path.join(output_dir, "temp_final.mp4")
        final_clip.write_videofile(
            temp_final,
            codec='libx264',
            audio_codec='aac',
            threads=threads,
            preset='ultrafast',
            logger=None
        )
        
        # 释放内存
        close_clip(video_clip)
        close_clip(audio_clip)
        close_clip(final_clip)
        
        # 更新最终文件
        os.remove(combined_video_path)
        os.rename(temp_final, combined_video_path)
        
        # 强制垃圾回收
        gc.collect()
        
    except Exception as e:
        logger.error(f"添加音频失败: {str(e)}")
    
    logger.info("视频合成完成")
    return combined_video_path


def wrap_text(text, max_width, font="Arial", fontsize=60):
    # Create ImageFont
    font = ImageFont.truetype(font, fontsize)

    def get_text_size(inner_text):
        inner_text = inner_text.strip()
        left, top, right, bottom = font.getbbox(inner_text)
        return right - left, bottom - top

    width, height = get_text_size(text)
    if width <= max_width:
        return text, height

    processed = True

    _wrapped_lines_ = []
    words = text.split(" ")
    _txt_ = ""
    for word in words:
        _before = _txt_
        _txt_ += f"{word} "
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            if _txt_.strip() == word.strip():
                processed = False
                break
            _wrapped_lines_.append(_before)
            _txt_ = f"{word} "
    _wrapped_lines_.append(_txt_)
    if processed:
        _wrapped_lines_ = [line.strip() for line in _wrapped_lines_]
        result = "\n".join(_wrapped_lines_).strip()
        height = len(_wrapped_lines_) * height
        return result, height

    _wrapped_lines_ = []
    chars = list(text)
    _txt_ = ""
    for word in chars:
        _txt_ += word
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            _wrapped_lines_.append(_txt_)
            _txt_ = ""
    _wrapped_lines_.append(_txt_)
    result = "\n".join(_wrapped_lines_).strip()
    height = len(_wrapped_lines_) * height
    return result, height


def generate_video(
    video_path: str,
    audio_path: str,
    subtitle_path: str,
    output_file: str,
    params: VideoParams,
):
    aspect = VideoAspect(params.video_aspect)
    video_width, video_height = aspect.to_resolution()

    logger.info(f"generating video: {video_width} x {video_height}")
    logger.info(f"  ① video: {video_path}")
    logger.info(f"  ② audio: {audio_path}")
    logger.info(f"  ③ subtitle: {subtitle_path}")
    logger.info(f"  ④ output: {output_file}")

    # https://github.com/harry0703/MoneyPrinterTurbo/issues/217
    # PermissionError: [WinError 32] The process cannot access the file because it is being used by another process: 'final-1.mp4.tempTEMP_MPY_wvf_snd.mp3'
    # write into the same directory as the output file
    output_dir = os.path.dirname(output_file)

    font_path = ""
    if params.subtitle_enabled:
        if not params.font_name:
            params.font_name = "STHeitiMedium.ttc"
        font_path = os.path.join(utils.font_dir(), params.font_name)
        if os.name == "nt":
            font_path = font_path.replace("\\", "/")

        logger.info(f"  ⑤ font: {font_path}")

    def create_text_clip(subtitle_item):
        params.font_size = int(params.font_size)
        params.stroke_width = int(params.stroke_width)
        phrase = subtitle_item[1]
        max_width = video_width * 0.9
        wrapped_txt, txt_height = wrap_text(
            phrase, max_width=max_width, font=font_path, fontsize=params.font_size
        )
        interline = int(params.font_size * 0.25)
        size=(int(max_width), int(txt_height + params.font_size * 0.25 + (interline * (wrapped_txt.count("\n") + 1))))

        _clip = TextClip(
            text=wrapped_txt,
            font=font_path,
            font_size=params.font_size,
            color=params.text_fore_color,
            bg_color=params.text_background_color,
            stroke_color=params.stroke_color,
            stroke_width=params.stroke_width,
            # interline=interline,
            # size=size,
        )
        duration = subtitle_item[0][1] - subtitle_item[0][0]
        _clip = _clip.with_start(subtitle_item[0][0])
        _clip = _clip.with_end(subtitle_item[0][1])
        _clip = _clip.with_duration(duration)
        if params.subtitle_position == "bottom":
            _clip = _clip.with_position(("center", video_height * 0.95 - _clip.h))
        elif params.subtitle_position == "top":
            _clip = _clip.with_position(("center", video_height * 0.05))
        elif params.subtitle_position == "custom":
            # Ensure the subtitle is fully within the screen bounds
            margin = 10  # Additional margin, in pixels
            max_y = video_height - _clip.h - margin
            min_y = margin
            custom_y = (video_height - _clip.h) * (params.custom_position / 100)
            custom_y = max(
                min_y, min(custom_y, max_y)
            )  # Constrain the y value within the valid range
            _clip = _clip.with_position(("center", custom_y))
        else:  # center
            _clip = _clip.with_position(("center", "center"))
        return _clip

    video_clip = VideoFileClip(video_path).without_audio()
    audio_clip = AudioFileClip(audio_path).with_effects(
        [afx.MultiplyVolume(params.voice_volume)]
    )

    def make_textclip(text):
        return TextClip(
            text=text,
            font=font_path,
            font_size=params.font_size,
        )

    if subtitle_path and os.path.exists(subtitle_path):
        sub = SubtitlesClip(
            subtitles=subtitle_path, encoding="utf-8", make_textclip=make_textclip
        )
        text_clips = []
        for item in sub.subtitles:
            clip = create_text_clip(subtitle_item=item)
            text_clips.append(clip)
        video_clip = CompositeVideoClip([video_clip, *text_clips])

    bgm_file = get_bgm_file(bgm_type=params.bgm_type, bgm_file=params.bgm_file)
    if bgm_file:
        try:
            bgm_clip = AudioFileClip(bgm_file).with_effects(
                [
                    afx.MultiplyVolume(params.bgm_volume),
                    afx.AudioFadeOut(3),
                    afx.AudioLoop(duration=video_clip.duration),
                ]
            )
            audio_clip = CompositeAudioClip([audio_clip, bgm_clip])
        except Exception as e:
            logger.error(f"failed to add bgm: {str(e)}")

    video_clip = video_clip.with_audio(audio_clip)
    video_clip.write_videofile(
        output_file,
        audio_codec=audio_codec,
        temp_audiofile_path=output_dir,
        threads=params.n_threads or 2,
        logger=None,
        fps=fps,
    )
    video_clip.close()
    del video_clip


def preprocess_video(materials: List[MaterialInfo], clip_duration=4):
    for material in materials:
        if not material.url:
            continue

        ext = utils.parse_extension(material.url)
        try:
            clip = VideoFileClip(material.url)
        except Exception:
            clip = ImageClip(material.url)

        width = clip.size[0]
        height = clip.size[1]
        if width < 480 or height < 480:
            logger.warning(f"low resolution material: {width}x{height}, minimum 480x480 required")
            continue

        if ext in const.FILE_TYPE_IMAGES:
            logger.info(f"processing image: {material.url}")
            # Create an image clip and set its duration to 3 seconds
            clip = (
                ImageClip(material.url)
                .with_duration(clip_duration)
                .with_position("center")
            )
            # Apply a zoom effect using the resize method.
            # A lambda function is used to make the zoom effect dynamic over time.
            # The zoom effect starts from the original size and gradually scales up to 120%.
            # t represents the current time, and clip.duration is the total duration of the clip (3 seconds).
            # Note: 1 represents 100% size, so 1.2 represents 120% size.
            zoom_clip = clip.resized(
                lambda t: 1 + (clip_duration * 0.03) * (t / clip.duration)
            )

            # Optionally, create a composite video clip containing the zoomed clip.
            # This is useful when you want to add other elements to the video.
            final_clip = CompositeVideoClip([zoom_clip])

            # Output the video to a file.
            video_file = f"{material.url}.mp4"
            final_clip.write_videofile(video_file, fps=30, logger=None)
            close_clip(clip)
            material.url = video_file
            logger.success(f"image processed: {video_file}")
    return materials