"""使用 Groq 的语音转写提供商。"""

import os
from pathlib import Path

import httpx
from loguru import logger


class GroqTranscriptionProvider:
    """
    使用 Groq 的 Whisper API 的语音转写提供商。

    Groq 提供极其快速的转写和慷慨的免费层级。
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.api_url = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def transcribe(self, file_path: str | Path) -> str:
        """
        使用 Groq 转写音频文件。

        Args:
            file_path: 音频文件的路径。

        Returns:
            转写的文本。
        """
        if not self.api_key:
            logger.warning("未配置 Groq API 密钥用于语音转写")
            return ""

        path = Path(file_path)
        if not path.exists():
            logger.error("音频文件未找到: {}", file_path)
            return ""

        try:
            async with httpx.AsyncClient() as client:
                with open(path, "rb") as f:
                    files = {
                        "file": (path.name, f),
                        "model": (None, "whisper-large-v3"),
                    }
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                    }

                    response = await client.post(
                        self.api_url,
                        headers=headers,
                        files=files,
                        timeout=60.0
                    )

                    response.raise_for_status()
                    data = response.json()
                    return data.get("text", "")

        except Exception as e:
            logger.error("Groq 语音转写错误: {}", e)
            return ""
