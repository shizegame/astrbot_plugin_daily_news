"""Validate AstrBot t2i results without treating URLs/paths as base64 data."""
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname


def image_location(value):
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("文转图服务未返回图片地址")
    value = value.strip()
    if len(value) > 4096 or any(ord(char) < 32 for char in value):
        raise ValueError("文转图返回的图片地址无效")
    try:
        parsed = urlsplit(value)
        if parsed.scheme in ("http", "https"):
            if not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("文转图返回的图片 URL 无效")
            return "url", value
        if parsed.scheme == "file":
            if parsed.netloc not in ("", "localhost"):
                raise ValueError("不支持远程 file 地址")
            value = url2pathname(parsed.path)
        path = Path(value)
        if path.is_file():
            return "file", str(path.resolve())
    except (OSError, ValueError) as exc:
        raise ValueError("文转图返回的图片地址无效") from exc
    raise ValueError("文转图返回的本地图片不存在或格式不受支持")
