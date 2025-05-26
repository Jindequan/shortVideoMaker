# 命令行工具使用说明

## 批量制作短视频

批量生成多个短视频，支持从文件读取标题列表。

### 使用方法

1. 准备标题文件（一行一个标题，空行会被忽略）：

```text
如何提高工作效率
健康饮食的重要性
每天锻炼的好处
```

2. 运行命令：

```bash
python batch_video_maker.py --file your_titles.txt
```

### 参数说明

- `--file`：标题文件路径（必需）
- `--max-titles`：最多处理的标题数量（可选，默认全部处理）
- `--start-index`：从第几个标题开始处理（可选，默认0）

## 制作长视频

将多个短视频片段合并成一个长视频，支持添加片头和转场效果。

### 使用方法

1. 准备任务目录，包含：
   - `script.txt`：视频文案
   - `materials/`：素材目录（可选）

2. 运行命令：

```bash
python long_video_maker.py --task-path /path/to/task --title "视频标题"
```

### 参数说明

- `--task-path`：任务目录路径（必需）
- `--title`：视频标题（必需）
- `--materials`：自定义素材目录路径（可选）

### 视频参数

- 视频分辨率：1920x1080（16:9）
- 片段时长：10秒
- 转场效果：渐变过渡
- 标题显示：2秒开场

## 生成配音文件

将文本转换为语音文件，支持多种TTS服务（Azure、SiliconFlow）。

### 使用方法

1. 直接转换文本：

```bash
python voice_maker.py --text "要转换的文本内容"
```

2. 从文件读取文本：

```bash
python voice_maker.py --file /path/to/text/file.txt
```

### 参数说明

- `--text`：要转换为语音的文本（与--file互斥，必选其一）
- `--file`：包含要转换文本的文件路径（与--text互斥，必选其一）
- `--voice-name`：语音名称，例如：zh-CN-XiaoyiNeural-Female（可选，默认使用配置文件中的设置）
- `--voice-rate`：语音速度，范围[0.25, 4.0]，默认1.0
- `--voice-volume`：语音音量，范围[0.6, 5.0]，默认1.0
- `--output`：输出的音频文件路径（可选，默认在当前目录或输入文件同目录）

### 配置说明

在`config.toml`中可以设置默认语音：

```toml
[ui]
voice_name = "zh-CN-YunyangNeural-Male"
```

## 注意事项

1. 确保已正确配置 `config.toml`
2. 检查 API 密钥设置（OpenAI、视频源等）
3. 确保网络连接正常
4. 建议使用 SSD 存储以提高处理速度
