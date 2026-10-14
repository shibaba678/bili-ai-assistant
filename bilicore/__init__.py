"""bilicore —— B 站请求核心（纯标准库，无第三方依赖）。

模块：
    config.py  配置加载、校验与 Cookie 组装
    wbi.py     WBI 请求签名
    client.py  请求层：串行限速 + 匿名设备回收 + WBI 缓存 + 错误不回显凭据
    api.py     业务接口：读 + 写 + 发评论
"""
from .api import BiliAPI, BiliError, format_count, format_duration
from .client import BiliClient
from .config import ConfigError, build_cookie, load_api, load_config, make_api

__all__ = [
    "BiliAPI", "BiliClient", "BiliError",
    "ConfigError", "build_cookie", "load_api", "load_config", "make_api",
    "format_count", "format_duration",
]
