"""使用 lark-oapi SDK 和 WebSocket 长连接的 Feishu/Lark 频道实现。"""

import asyncio
import json
import os
import re
import threading
import requests
from collections import OrderedDict
from pathlib import Path
from typing import Any

from loguru import logger

from dbot.bus.events import OutboundMessage
from dbot.bus.queue import MessageBus
from dbot.channels.base import BaseChannel
from dbot.config.schema import FeishuConfig

import importlib.util

FEISHU_AVAILABLE = importlib.util.find_spec("lark_oapi") is not None

# 消息类型显示映射
MSG_TYPE_MAP = {
    "image": "[image]",
    "audio": "[audio]",
    "file": "[file]",
    "sticker": "[sticker]",
}


def _extract_share_card_content(content_json: dict, msg_type: str) -> str:
    """从分享卡片和交互式消息中提取文本表示。"""
    parts = []

    if msg_type == "share_chat":
        parts.append(f"[shared chat: {content_json.get('chat_id', '')}]")
    elif msg_type == "share_user":
        parts.append(f"[shared user: {content_json.get('user_id', '')}]")
    elif msg_type == "interactive":
        parts.extend(_extract_interactive_content(content_json))
    elif msg_type == "share_calendar_event":
        parts.append(f"[shared calendar event: {content_json.get('event_key', '')}]")
    elif msg_type == "system":
        parts.append("[system message]")
    elif msg_type == "merge_forward":
        parts.append("[merged forward messages]")

    return "\n".join(parts) if parts else f"[{msg_type}]"


def _extract_interactive_content(content: dict) -> list[str]:
    """从交互式卡片内容中递归提取文本和链接。"""
    parts = []

    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return [content] if content.strip() else []

    if not isinstance(content, dict):
        return parts

    if "title" in content:
        title = content["title"]
        if isinstance(title, dict):
            title_content = title.get("content", "") or title.get("text", "")
            if title_content:
                parts.append(f"title: {title_content}")
        elif isinstance(title, str):
            parts.append(f"title: {title}")

    for elements in content.get("elements", []) if isinstance(content.get("elements"), list) else []:
        for element in elements:
            parts.extend(_extract_element_content(element))

    card = content.get("card", {})
    if card:
        parts.extend(_extract_interactive_content(card))

    header = content.get("header", {})
    if header:
        header_title = header.get("title", {})
        if isinstance(header_title, dict):
            header_text = header_title.get("content", "") or header_title.get("text", "")
            if header_text:
                parts.append(f"title: {header_text}")

    return parts


def _extract_element_content(element: dict) -> list[str]:
    """从单个卡片元素中提取内容。"""
    parts = []

    if not isinstance(element, dict):
        return parts

    tag = element.get("tag", "")

    if tag in ("markdown", "lark_md"):
        content = element.get("content", "")
        if content:
            parts.append(content)

    elif tag == "div":
        text = element.get("text", {})
        if isinstance(text, dict):
            text_content = text.get("content", "") or text.get("text", "")
            if text_content:
                parts.append(text_content)
        elif isinstance(text, str):
            parts.append(text)
        for field in element.get("fields", []):
            if isinstance(field, dict):
                field_text = field.get("text", {})
                if isinstance(field_text, dict):
                    c = field_text.get("content", "")
                    if c:
                        parts.append(c)

    elif tag == "a":
        href = element.get("href", "")
        text = element.get("text", "")
        if href:
            parts.append(f"link: {href}")
        if text:
            parts.append(text)

    elif tag == "button":
        text = element.get("text", {})
        if isinstance(text, dict):
            c = text.get("content", "")
            if c:
                parts.append(c)
        url = element.get("url", "") or element.get("multi_url", {}).get("url", "")
        if url:
            parts.append(f"link: {url}")

    elif tag == "img":
        alt = element.get("alt", {})
        parts.append(alt.get("content", "[image]") if isinstance(alt, dict) else "[image]")

    elif tag == "note":
        for ne in element.get("elements", []):
            parts.extend(_extract_element_content(ne))

    elif tag == "column_set":
        for col in element.get("columns", []):
            for ce in col.get("elements", []):
                parts.extend(_extract_element_content(ce))

    elif tag == "plain_text":
        content = element.get("content", "")
        if content:
            parts.append(content)

    else:
        for ne in element.get("elements", []):
            parts.extend(_extract_element_content(ne))

    return parts


def _extract_post_content(content_json: dict) -> tuple[str, list[str]]:
    """从 Feishu post（富文本）消息中提取文本和图像键。

    处理三种负载形状：
    - 直接：    {"title": "...", "content": [[...]]}
    - 本地化： {"zh_cn": {"title": "...", "content": [...]}}
    - 包装：   {"post": {"zh_cn": {"title": "...", "content": [...]}}}
    """

    def _parse_block(block: dict) -> tuple[str | None, list[str]]:
        if not isinstance(block, dict) or not isinstance(block.get("content"), list):
            return None, []
        texts, images = [], []
        if title := block.get("title"):
            texts.append(title)
        for row in block["content"]:
            if not isinstance(row, list):
                continue
            for el in row:
                if not isinstance(el, dict):
                    continue
                tag = el.get("tag")
                if tag in ("text", "a"):
                    texts.append(el.get("text", ""))
                elif tag == "at":
                    texts.append(f"@{el.get('user_name', 'user')}")
                elif tag == "img" and (key := el.get("image_key")):
                    images.append(key)
        return (" ".join(texts).strip() or None), images

    # 展开可选的 {"post": ...} 包络
    root = content_json
    if isinstance(root, dict) and isinstance(root.get("post"), dict):
        root = root["post"]
    if not isinstance(root, dict):
        return "", []

    # Direct format
    if "content" in root:
        text, imgs = _parse_block(root)
        if text or imgs:
            return text or "", imgs

    # 本地化：优先使用已知语言环境，然后回退到任何字典子项
    for key in ("zh_cn", "en_us", "ja_jp"):
        if key in root:
            text, imgs = _parse_block(root[key])
            if text or imgs:
                return text or "", imgs
    for val in root.values():
        if isinstance(val, dict):
            text, imgs = _parse_block(val)
            if text or imgs:
                return text or "", imgs

    return "", []


def _extract_post_text(content_json: dict) -> str:
    """从 Feishu post（富文本）消息内容中提取纯文本。

    _extract_post_content 的传统包装器，仅返回文本。
    """
    text, _ = _extract_post_content(content_json)
    return text


class FeishuChannel(BaseChannel):
    """
    使用 WebSocket 长连接的 Feishu/Lark 频道。

    使用 WebSocket 接收事件 - 无需公网 IP 或 webhook。

    需要：
    - 来自 Feishu 开放平台的 App ID 和 App Secret
    - 启用机器人能力
    - 启用事件订阅 (im.message.receive_v1)
    """

    name = "feishu"

    def __init__(self, config: FeishuConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: FeishuConfig = config
        self._client: Any = None
        self._ws_client: Any = None
        self._ws_thread: threading.Thread | None = None
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()  # 有序去重缓存
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        """使用 WebSocket 长连接启动 Feishu 机器人。"""
        if not FEISHU_AVAILABLE:
            logger.error("飞书 SDK 未安装。请运行: pip install lark-oapi")
            return

        if not self.config.app_id or not self.config.app_secret:
            logger.error("飞书 app_id 和 app_secret 未配置")
            return

        import lark_oapi as lark
        self._running = True
        self._loop = asyncio.get_running_loop()

        # 创建 Lark 客户端用于发送消息
        self._client = lark.Client.builder() \
            .app_id(self.config.app_id) \
            .app_secret(self.config.app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

        # 创建事件处理器（仅注册消息接收，忽略其他事件）
        event_handler = lark.EventDispatcherHandler.builder(
            self.config.encrypt_key or "",
            self.config.verification_token or "",
        ).register_p2_im_message_receive_v1(
            self._on_message_sync
        ).build()

        # 创建 WebSocket 客户端用于长连接
        self._ws_client = lark.ws.Client(
            self.config.app_id,
            self.config.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO
        )

        # 在单独的线程中启动 WebSocket 客户端，带有重新连接循环。
        # 为此线程创建一个专用的事件循环，以便 lark_oapi 的
        # 模块级 `loop = asyncio.get_event_loop()` 获取一个空闲循环
        # 而不是已经运行的主 asyncio 循环，这会导致
        # "This event loop is already running" 错误。
        def run_ws():
            import time
            import lark_oapi.ws.client as _lark_ws_client
            ws_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(ws_loop)
            # 修补 lark 的 ws Client.start() 使用的模块级循环
            _lark_ws_client.loop = ws_loop
            try:
                while self._running:
                    try:
                        self._ws_client.start()
                    except Exception as e:
                        logger.warning("飞书 WebSocket 错误: {}", e)
                    if self._running:
                        time.sleep(5)
            finally:
                ws_loop.close()

        self._ws_thread = threading.Thread(target=run_ws, daemon=True)
        self._ws_thread.start()

        logger.info("飞书机器人已通过 WebSocket 长连接启动")
        logger.info("无需公网 IP - 使用 WebSocket 接收事件")

        # 持续运行直到停止
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """
        停止 Feishu 机器人。

        注意：lark.ws.Client 不暴露 stop 方法，只需退出程序即可关闭客户端。

        参考：https://github.com/larksuite/oapi-sdk-python/blob/v2_main/lark_oapi/ws/client.py#L86
        """
        self._running = False
        logger.info("飞书机器人已停止")

    def _add_reaction_sync(self, message_id: str, emoji_type: str) -> None:
        """添加反应的同步助手（在线程池中运行）。"""
        from lark_oapi.api.im.v1 import CreateMessageReactionRequest, CreateMessageReactionRequestBody, Emoji
        try:
            request = CreateMessageReactionRequest.builder() \
                .message_id(message_id) \
                .request_body(
                    CreateMessageReactionRequestBody.builder()
                    .reaction_type(Emoji.builder().emoji_type(emoji_type).build())
                    .build()
                ).build()

            response = self._client.im.v1.message_reaction.create(request)

            if not response.success():
                logger.warning("添加反应失败: code={}, msg={}", response.code, response.msg)
            else:
                logger.debug("已添加 {} 反应到消息 {}", emoji_type, message_id)
        except Exception as e:
            logger.warning("添加反应时出错: {}", e)

    async def _add_reaction(self, message_id: str, emoji_type: str = "THUMBSUP") -> None:
        """
        向消息添加反应表情符号（非阻塞）。

        常见的表情符号类型：THUMBSUP、OK、EYES、DONE、OnIt、HEART
        """
        if not self._client:
            return

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._add_reaction_sync, message_id, emoji_type)

    # 用于匹配 markdown 表格的正则表达式（标题 + 分隔符 + 数据行）
    _TABLE_RE = re.compile(
        r"((?:^[ \t]*\|.+\|[ \t]*\n)(?:^[ \t]*\|[-:\s|]+\|[ \t]*\n)(?:^[ \t]*\|.+\|[ \t]*\n?)+)",
        re.MULTILINE,
    )

    _HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

    _CODE_BLOCK_RE = re.compile(r"(```[\s\S]*?```)", re.MULTILINE)

    @staticmethod
    def _parse_md_table(table_text: str) -> dict | None:
        """将 markdown 表格解析为 Feishu 表格元素。"""
        lines = [_line.strip() for _line in table_text.strip().split("\n") if _line.strip()]
        if len(lines) < 3:
            return None
        def split(_line: str) -> list[str]:
            return [c.strip() for c in _line.strip("|").split("|")]
        headers = split(lines[0])
        rows = [split(_line) for _line in lines[2:]]
        columns = [{"tag": "column", "name": f"c{i}", "display_name": h, "width": "auto"}
                   for i, h in enumerate(headers)]
        return {
            "tag": "table",
            "page_size": len(rows) + 1,
            "columns": columns,
            "rows": [{f"c{i}": r[i] if i < len(r) else "" for i in range(len(headers))} for r in rows],
        }

    def _build_card_elements(self, content: str) -> list[dict]:
        """将内容分割为 Feishu 卡片的 div/markdown + 表格元素。"""
        elements, last_end = [], 0
        for m in self._TABLE_RE.finditer(content):
            before = content[last_end:m.start()]
            if before.strip():
                elements.extend(self._split_headings(before))
            elements.append(self._parse_md_table(m.group(1)) or {"tag": "markdown", "content": m.group(1)})
            last_end = m.end()
        remaining = content[last_end:]
        if remaining.strip():
            elements.extend(self._split_headings(remaining))
        return elements or [{"tag": "markdown", "content": content}]

    @staticmethod
    def _split_elements_by_table_limit(elements: list[dict], max_tables: int = 1) -> list[list[dict]]:
        """将卡片元素分割为每组最多包含 *max_tables* 个表格元素的组。

        Feishu 卡片每个卡片有严格的限制（API 错误 11310）。
        当渲染的内容包含多个 markdown 表格时，每个表格都
        放在单独的卡片消息中，以便每个表格都能到达用户。
        """
        if not elements:
            return [[]]
        groups: list[list[dict]] = []
        current: list[dict] = []
        table_count = 0
        for el in elements:
            if el.get("tag") == "table":
                if table_count >= max_tables:
                    if current:
                        groups.append(current)
                    current = []
                    table_count = 0
                current.append(el)
                table_count += 1
            else:
                current.append(el)
        if current:
            groups.append(current)
        return groups or [[]]

    def _split_headings(self, content: str) -> list[dict]:
        """按标题分割内容，将标题转换为 div 元素。"""
        protected = content
        code_blocks = []
        for m in self._CODE_BLOCK_RE.finditer(content):
            code_blocks.append(m.group(1))
            protected = protected.replace(m.group(1), f"\x00CODE{len(code_blocks)-1}\x00", 1)

        elements = []
        last_end = 0
        for m in self._HEADING_RE.finditer(protected):
            before = protected[last_end:m.start()].strip()
            if before:
                elements.append({"tag": "markdown", "content": before})
            text = m.group(2).strip()
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{text}**",
                },
            })
            last_end = m.end()
        remaining = protected[last_end:].strip()
        if remaining:
            elements.append({"tag": "markdown", "content": remaining})

        for i, cb in enumerate(code_blocks):
            for el in elements:
                if el.get("tag") == "markdown":
                    el["content"] = el["content"].replace(f"\x00CODE{i}\x00", cb)

        return elements or [{"tag": "markdown", "content": content}]

    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tiff", ".tif"}
    _AUDIO_EXTS = {".opus"}
    _FILE_TYPE_MAP = {
        ".opus": "opus", ".mp4": "mp4", ".pdf": "pdf", ".doc": "doc", ".docx": "doc",
        ".xls": "xls", ".xlsx": "xls", ".ppt": "ppt", ".pptx": "ppt",
    }

    def _upload_image_sync(self, file_path_or_url: str) -> str | None:
        """将图像上传到 Feishu 并返回 image_key。支持本地文件或 URL。"""
        from lark_oapi.api.im.v1 import CreateImageRequest, CreateImageRequestBody
        try:
            # 检查是否是 URL
            if file_path_or_url.startswith(('http://', 'https://')):
                # 从 URL 下载图片
                response = requests.get(file_path_or_url, timeout=60)
                if response.status_code != 200:
                    logger.error("从 URL 下载图片失败: {}", file_path_or_url)
                    return None
                image_data = response.content
                from io import BytesIO
                image_file = BytesIO(image_data)
            else:
                # 本地文件
                image_file = open(file_path_or_url, "rb")

            try:
                request = CreateImageRequest.builder() \
                    .request_body(
                        CreateImageRequestBody.builder()
                        .image_type("message")
                        .image(image_file)
                        .build()
                    ).build()
                response = self._client.im.v1.image.create(request)
                if response.success():
                    image_key = response.data.image_key
                    logger.debug("已上传图片 {}: {}", os.path.basename(file_path_or_url) if not file_path_or_url.startswith('http') else "来自 URL", image_key)
                    return image_key
                else:
                    logger.error("上传图片失败: code={}, msg={}", response.code, response.msg)
                    return None
            finally:
                if not file_path_or_url.startswith(('http://', 'https://')):
                    image_file.close()
        except Exception as e:
            logger.error("上传图片 {} 时出错: {}", file_path_or_url, e)
            return None

    def _upload_file_sync(self, file_path: str) -> str | None:
        """将文件上传到 Feishu 并返回 file_key。"""
        from lark_oapi.api.im.v1 import CreateFileRequest, CreateFileRequestBody
        ext = os.path.splitext(file_path)[1].lower()
        file_type = self._FILE_TYPE_MAP.get(ext, "stream")
        file_name = os.path.basename(file_path)
        try:
            with open(file_path, "rb") as f:
                request = CreateFileRequest.builder() \
                    .request_body(
                        CreateFileRequestBody.builder()
                        .file_type(file_type)
                        .file_name(file_name)
                        .file(f)
                        .build()
                    ).build()
                response = self._client.im.v1.file.create(request)
                if response.success():
                    file_key = response.data.file_key
                    logger.debug("已上传文件 {}: {}", file_name, file_key)
                    return file_key
                else:
                    logger.error("上传文件失败: code={}, msg={}", response.code, response.msg)
                    return None
        except Exception as e:
            logger.error("上传文件 {} 时出错: {}", file_path, e)
            return None

    def _download_image_sync(self, message_id: str, image_key: str) -> tuple[bytes | None, str | None]:
        """通过 message_id 和 image_key 从 Feishu 消息下载图像。"""
        from lark_oapi.api.im.v1 import GetMessageResourceRequest
        try:
            request = GetMessageResourceRequest.builder() \
                .message_id(message_id) \
                .file_key(image_key) \
                .type("image") \
                .build()
            response = self._client.im.v1.message_resource.get(request)
            if response.success():
                file_data = response.file
                # GetMessageResourceRequest 返回 BytesIO，需要读取字节
                if hasattr(file_data, 'read'):
                    file_data = file_data.read()
                return file_data, response.file_name
            else:
                logger.error("下载图片失败: code={}, msg={}", response.code, response.msg)
                return None, None
        except Exception as e:
            logger.error("下载图片 {} 时出错: {}", image_key, e)
            return None, None

    def _download_file_sync(
        self, message_id: str, file_key: str, resource_type: str = "file"
    ) -> tuple[bytes | None, str | None]:
        """通过 message_id 和 file_key 从 Feishu 消息下载文件/音频/媒体。"""
        from lark_oapi.api.im.v1 import GetMessageResourceRequest

        # Feishu API 仅接受 'image' 或 'file' 作为类型参数
        # 为了 API 兼容性，将 'audio' 转换为 'file'
        if resource_type == "audio":
            resource_type = "file"

        try:
            request = (
                GetMessageResourceRequest.builder()
                .message_id(message_id)
                .file_key(file_key)
                .type(resource_type)
                .build()
            )
            response = self._client.im.v1.message_resource.get(request)
            if response.success():
                file_data = response.file
                if hasattr(file_data, "read"):
                    file_data = file_data.read()
                return file_data, response.file_name
            else:
                logger.error("下载 {} 失败: code={}, msg={}", resource_type, response.code, response.msg)
                return None, None
        except Exception:
            logger.exception("下载 {} {} 时出错", resource_type, file_key)
            return None, None

    async def _download_and_save_media(
        self,
        msg_type: str,
        content_json: dict,
        message_id: str | None = None
    ) -> tuple[str | None, str]:
        """
        从 Feishu 下载媒体并保存到本地磁盘。

        返回：
            (file_path, content_text) - 如果下载失败，file_path 为 None
        """
        loop = asyncio.get_running_loop()
        media_dir = Path.home() / ".dbot" / "media"
        media_dir.mkdir(parents=True, exist_ok=True)

        data, filename = None, None

        if msg_type == "image":
            image_key = content_json.get("image_key")
            if image_key and message_id:
                data, filename = await loop.run_in_executor(
                    None, self._download_image_sync, message_id, image_key
                )
                if not filename:
                    filename = f"{image_key[:16]}.jpg"

        elif msg_type in ("audio", "file", "media"):
            file_key = content_json.get("file_key")
            if file_key and message_id:
                data, filename = await loop.run_in_executor(
                    None, self._download_file_sync, message_id, file_key, msg_type
                )
                if not filename:
                    ext = {"audio": ".opus", "media": ".mp4"}.get(msg_type, "")
                    filename = f"{file_key[:16]}{ext}"

        if data and filename:
            file_path = media_dir / filename
            file_path.write_bytes(data)
            logger.debug("Downloaded {} to {}", msg_type, file_path)
            return str(file_path), f"[{msg_type}: {filename}]"

        return None, f"[{msg_type}: download failed]"

    def _send_message_sync(self, receive_id_type: str, receive_id: str, msg_type: str, content: str) -> bool:
        """同步发送单个消息（文本/图像/文件/交互式）。"""
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
        try:
            request = CreateMessageRequest.builder() \
                .receive_id_type(receive_id_type) \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type(msg_type)
                    .content(content)
                    .build()
                ).build()
            response = self._client.im.v1.message.create(request)
            if not response.success():
                logger.error(
                    "发送飞书 {} 消息失败: code={}, msg={}, log_id={}",
                    msg_type, response.code, response.msg, response.get_log_id()
                )
                return False
            logger.debug("飞书 {} 消息已发送到 {}", msg_type, receive_id)
            return True
        except Exception as e:
            logger.error("发送飞书 {} 消息时出错: {}", msg_type, e)
            return False

    async def send(self, msg: OutboundMessage) -> None:
        """通过 Feishu 发送消息，如果存在则包括媒体（图像/文件）。支持本地文件和 URL。"""
        if not self._client:
            logger.warning("飞书客户端未初始化")
            return

        try:
            receive_id_type = "chat_id" if msg.chat_id.startswith("oc_") else "open_id"
            loop = asyncio.get_running_loop()

            for file_path in msg.media:
                # 检查是否是 URL 或本地文件
                is_url = file_path.startswith(('http://', 'https://'))
                is_local_file = os.path.isfile(file_path) if not is_url else False

                if not is_url and not is_local_file:
                    logger.warning("媒体文件未找到: {}", file_path)
                    continue

                # 根据扩展名或 URL 判断文件类型
                if is_url:
                    # URL 图片默认当作图片处理
                    ext = '.png'  # 默认扩展名
                else:
                    ext = os.path.splitext(file_path)[1].lower()

                if ext in self._IMAGE_EXTS or is_url:
                    key = await loop.run_in_executor(None, self._upload_image_sync, file_path)
                    if key:
                        await loop.run_in_executor(
                            None, self._send_message_sync,
                            receive_id_type, msg.chat_id, "image", json.dumps({"image_key": key}, ensure_ascii=False),
                        )
                else:
                    # 非 URL 的本地文件
                    key = await loop.run_in_executor(None, self._upload_file_sync, file_path)
                    if key:
                        media_type = "audio" if ext in self._AUDIO_EXTS else "file"
                        await loop.run_in_executor(
                            None, self._send_message_sync,
                            receive_id_type, msg.chat_id, media_type, json.dumps({"file_key": key}, ensure_ascii=False),
                        )

            if msg.content and msg.content.strip():
                elements = self._build_card_elements(msg.content)
                for chunk in self._split_elements_by_table_limit(elements):
                    card = {"config": {"wide_screen_mode": True}, "elements": chunk}
                    await loop.run_in_executor(
                        None, self._send_message_sync,
                        receive_id_type, msg.chat_id, "interactive", json.dumps(card, ensure_ascii=False),
                    )

        except Exception as e:
            logger.error("发送飞书消息时出错: {}", e)

    def _on_message_sync(self, data: "P2ImMessageReceiveV1") -> None:
        """
        传入消息的同步处理器（从 WebSocket 线程调用）。
        在主事件循环中安排异步处理。
        """
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._on_message(data), self._loop)

    async def _on_message(self, data: "P2ImMessageReceiveV1") -> None:
        """处理来自 Feishu 的传入消息。"""
        try:
            event = data.event
            message = event.message
            sender = event.sender

            # 去重检查
            message_id = message.message_id
            if message_id in self._processed_message_ids:
                return
            self._processed_message_ids[message_id] = None

            # 修剪缓存
            while len(self._processed_message_ids) > 1000:
                self._processed_message_ids.popitem(last=False)

            # 跳过机器人消息
            if sender.sender_type == "bot":
                return

            sender_id = sender.sender_id.open_id if sender.sender_id else "unknown"
            chat_id = message.chat_id
            chat_type = message.chat_type
            msg_type = message.message_type

            # 添加反应
            await self._add_reaction(message_id, self.config.react_emoji)

            # 解析内容
            content_parts = []
            media_paths = []

            try:
                content_json = json.loads(message.content) if message.content else {}
            except json.JSONDecodeError:
                content_json = {}

            if msg_type == "text":
                text = content_json.get("text", "")
                if text:
                    content_parts.append(text)

            elif msg_type == "post":
                text, image_keys = _extract_post_content(content_json)
                if text:
                    content_parts.append(text)
                # 下载 post 中嵌入的图像
                for img_key in image_keys:
                    file_path, content_text = await self._download_and_save_media(
                        "image", {"image_key": img_key}, message_id
                    )
                    if file_path:
                        media_paths.append(file_path)
                    content_parts.append(content_text)

            elif msg_type in ("image", "audio", "file", "media"):
                file_path, content_text = await self._download_and_save_media(msg_type, content_json, message_id)
                if file_path:
                    media_paths.append(file_path)
                content_parts.append(content_text)

            elif msg_type in ("share_chat", "share_user", "interactive", "share_calendar_event", "system", "merge_forward"):
                # 处理分享卡片和交互式消息
                text = _extract_share_card_content(content_json, msg_type)
                if text:
                    content_parts.append(text)

            else:
                content_parts.append(MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]"))

            content = "\n".join(content_parts) if content_parts else ""

            if not content and not media_paths:
                return

            # 转发到消息总线
            reply_to = chat_id if chat_type == "group" else sender_id
            await self._handle_message(
                sender_id=sender_id,
                chat_id=reply_to,
                content=content,
                media=media_paths,
                metadata={
                    "message_id": message_id,
                    "chat_type": chat_type,
                    "msg_type": msg_type,
                }
            )

        except Exception as e:
            logger.error("处理飞书消息时出错: {}", e)
