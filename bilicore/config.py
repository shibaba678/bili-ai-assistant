"""配置加载：一个地方管配置文件查找、校验与 Cookie 组装。

查找顺序（先找到先用）：
    config.toml          —— 推荐。用 setup.py 生成，已在 .gitignore 里
    secret.config.toml   —— 兼容旧名

设计约束：凭据只从本地文件读，永远不从命令行参数或环境变量回显，
也不写进任何日志。
"""
import os
import sys

# 候选配置文件名，按优先级排列
CONFIG_CANDIDATES = ("config.toml", "secret.config.toml")

# 需要替换掉的占位值（示例配置里的原文）
PLACEHOLDERS = ("在这里填", "你的昵称", "主人的B站昵称", "123456789")


class ConfigError(Exception):
    """配置文件缺失或填写不完整。"""


def project_root():
    """项目根目录（bilicore 的上一级）。

    用来定位配置：用户可能在任意目录下用绝对路径调用脚本，
    只按当前工作目录找会找不到配置。
    """
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_path():
    """本项目约定的配置文件绝对路径（setup.py 写的就是这个）。"""
    return os.path.join(project_root(), "config.toml")


def find_config(explicit=None):
    """定位配置文件，返回路径；找不到抛 ConfigError。

    查找顺序：显式路径 → 当前工作目录 → 项目根目录。
    后两者都查，是为了让「在项目里跑」和「在别处用绝对路径跑」都能work。
    """
    if explicit:
        if os.path.exists(explicit):
            return explicit
        raise ConfigError(f"找不到配置文件：{explicit}")

    roots = [os.getcwd(), project_root()]
    seen = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        for name in CONFIG_CANDIDATES:
            candidate = os.path.join(root, name)
            if os.path.exists(candidate):
                return candidate

    raise ConfigError(
        "找不到配置文件。请先运行：\n"
        "    python setup.py\n"
        "它会引导你填入自己的 B 站 Cookie 与 DeepSeek 密钥，生成 config.toml。")


def load_config(explicit=None):
    """读配置，返回 dict。"""
    try:
        import tomllib
    except ImportError:  # Python 3.10 及以下
        raise ConfigError("需要 Python 3.11+（用到内置 tomllib）")

    path = find_config(explicit)
    with open(path, "rb") as f:
        cfg = tomllib.load(f)

    _validate(cfg, path)
    return cfg


def _validate(cfg, path):
    """把「没填」和「填错」在启动时就挡住，别等发评论才报错。"""
    b = cfg.get("bilibili") or {}

    def need(key, label):
        value = str(b.get(key, "") or "").strip()
        if not value or any(p in value for p in PLACEHOLDERS):
            raise ConfigError(
                f"{path} 里的 bilibili.{key} 还没填（{label}）。\n"
                f"运行 python setup.py 重新配置，或手动编辑该文件。")
        return value

    need("sessdata", "登录态，F12 里复制 SESSDATA 的值")
    need("bili_jct", "CSRF 令牌，点赞与发评论必需")
    need("mid", "你的 B 站 UID，space.bilibili.com/XXX 里的数字")
    need("master_name", "要 @ 的 B 站昵称")


def build_cookie(cfg):
    """把配置里的凭据字段拼成 Cookie 串。"""
    b = cfg["bilibili"]
    parts = [
        f"SESSDATA={b['sessdata']}",
        f"bili_jct={b['bili_jct']}",
        f"DedeUserID={b['mid']}",
    ]
    if str(b.get("buvid3", "") or "").strip():
        parts.append(f"buvid3={b['buvid3']}")
    return "; ".join(parts)


def make_api(cfg):
    """按配置造一个 BiliAPI。"""
    from .api import BiliAPI
    b = cfg["bilibili"]
    rl = cfg.get("rate_limit") or {}
    return BiliAPI(
        cookie=build_cookie(cfg),
        timeout=float(b.get("timeout", 15)),
        min_interval=float(rl.get("min_request_interval", 0.7)),
    )


def load_api(explicit=None):
    """一步到位：读配置 + 造 API。"""
    cfg = load_config(explicit)
    return make_api(cfg), cfg
