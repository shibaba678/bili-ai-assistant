#!/usr/bin/env python3
"""配置向导：引导你填入**自己的** B 站账号与 DeepSeek 密钥。

    python setup.py

全程只在本机读写 config.toml，不联网、不上传、不经过任何 AI 对话。
配置完成后 config.toml 会被 .gitignore 挡住，不会被误提交。
"""
import getpass
import os
import sys

# 配置写到项目根目录（bilicore 的上一级），不管从哪里调用 setup.py。
# 这样在任意目录用绝对路径跑，配置都落在同一个地方，不会散。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bilicore.config import config_path  # noqa: E402

CONFIG_PATH = config_path()

BANNER = r"""
  ____  _ _ _   _    _   _ _____
 | __ )(_) (_) / \  | \ | |_   _|
 |  _ \| | | |/ _ \ |  \| | | |
 | |_) | | | / ___ \| |\  | | |
 |____/|_|_|_/_/   \_\_| \_| |_|      AI Assistant Setup

 用你自己的 B 站账号与自己的 AI 密钥，搭一个会总结视频的助手。
"""


def ask(label, hint, secret=False, default=""):
    """问一个值。secret=True 时不回显输入。"""
    print()
    print(f"── {label}")
    if hint:
        for line in hint.strip().splitlines():
            print(f"   {line}")
    while True:
        prompt = "   > "
        if default:
            prompt = f"   [{default}] > "
        value = (getpass.getpass(prompt) if secret else input(prompt)).strip()
        if not value and default:
            return default
        if value:
            return value
        print("   ⚠ 这一项不能为空，请重新输入。")


def guide_cookie():
    """教用户从浏览器里取 Cookie。这一步最容易卡住，写详细。"""
    print("""
╭──────────────────────────────────────────────────────────────╮
│  第 1 步：获取你的 B 站 Cookie                                │
╰──────────────────────────────────────────────────────────────╯

在电脑浏览器里登录 bilibili.com，然后：

  1. 按 F12 打开开发者工具
  2. 切到 Application（应用）标签页
     · Chrome/Edge：左侧 Storage → Cookies → https://www.bilibili.com
     · Firefox：左侧 存储 → Cookie → https://www.bilibili.com
  3. 在列表里找到下面三项，逐个复制它们的 Value（值）列：
""")
    sessdata = ask("SESSDATA 的值",
                   "登录态本体。没有它就读不到字幕、历史，也发不了评论。",
                   secret=True)
    bili_jct = ask("bili_jct 的值",
                   "CSRF 令牌。点赞、投币、发评论都需要它。",
                   secret=True)
    mid = ask("你的 UID",
              "打开 https://space.bilibili.com/ 看你主页地址里的数字，\n"
              "例如 space.bilibili.com/123456789 → 填 123456789。")
    buvid3 = ask("buvid3 的值（可留空）",
                 "设备标识。留空也能用（程序会自己领一个），\n"
                 "但填上更稳，搜索接口不容易被风控拦。",
                 secret=True)
    return sessdata, bili_jct, mid, buvid3


def guide_deepseek():
    print("""
╭──────────────────────────────────────────────────────────────╮
│  第 2 步：DeepSeek API 密钥（可选）                            │
╰──────────────────────────────────────────────────────────────╯

这个密钥用来让 AI 自动写视频总结。**可以跳过**——跳过之后，
你仍然可以用 bili.py 的所有功能，只是要自己写总结文案。

要自动总结的话：
  1. 打开 https://platform.deepseek.com/
  2. 注册登录 → API Keys → Create API Key
  3. 复制生成的密钥（sk- 开头）
""")
    key = ask("DeepSeek API Key（直接回车跳过）", "", secret=True)
    return key


def guide_master():
    print("""
╭──────────────────────────────────────────────────────────────╮
│  第 3 步：你想 @ 谁                                            │
╰──────────────────────────────────────────────────────────────╯

助手发评论时会以「@昵称」开头，被 @ 的人会收到 B 站通知。
填你自己的昵称，就是「助手 @ 我」；填朋友的，就是「助手 @ 朋友」。

注意：必须和 B 站昵称**一字不差**，否则 @ 不会生效。
""")
    name = ask("要 @ 的 B 站昵称")
    return name


def write_config(sessdata, bili_jct, mid, buvid3, deepseek_key, master_name):
    """写 config.toml。字符串里的引号与反斜杠要转义，否则 TOML 会解析失败。"""
    def esc(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')

    content = f'''# 由 setup.py 生成 —— 请勿提交到 git（已在 .gitignore 中）
# 想改配置直接编辑本文件，或重跑 python setup.py

[bilibili]
sessdata = "{esc(sessdata)}"
bili_jct = "{esc(bili_jct)}"
mid = "{esc(mid)}"
buvid3 = "{esc(buvid3)}"

# 发评论账号的昵称（常驻监听 monitor.py 用来识别 @召唤）
trigger_name = ""
# 评论区 @ 的目标 —— 你自己的 B 站昵称
master_name = "{esc(master_name)}"

timeout = 15
check_interval = 300

[watch_list]
# monitor.py 要盯的视频；对话内工具用不到，可留空
bvids = []

[deepseek]
api_key = "{esc(deepseek_key)}"
base_url = "https://api.deepseek.com"
model = "deepseek-chat"
max_tokens = 500
temperature = 0.3
system_prompt = """你是一个视频总结助手，帮用户快速了解一个 B 站视频讲了什么。

风格要求：
- 像朋友聊天一样自然地讲，不要编号、不要「第一第二第三」、不要罗列要点
- 直接说内容，不要「这个视频讲述了」这种套话开场
- 抓住最核心的看点和一两个有意思的细节，250 字以内
- 不确定的地方不要编，字幕没有的信息就别提

直接输出总结正文，不要寒暄。"""

[reply]
prefix = ""
suffix = ""
reply_delay = 5

[rate_limit]
# 请求最小间隔（秒）。所有请求串行，别往下调。
min_request_interval = 0.7

[logging]
level = "INFO"
file = "logs/bot.log"
console = true

[state]
file = "state.json"
'''
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    try:
        os.chmod(CONFIG_PATH, 0o600)  # 尽力而为：Windows 上可能无效
    except OSError:
        pass


def verify(cfg_path=CONFIG_PATH):
    """配置写完立刻验证一次，别让用户到用的时候才发现填错。"""
    print("\n正在验证凭据…")
    try:
        from bilicore.api import BiliAPI
        from bilicore.config import build_cookie, load_config
        cfg = load_config(cfg_path)
        api = BiliAPI(cookie=build_cookie(cfg))
        nav = api.nav()
    except Exception as e:
        print(f"\n⚠ 验证没通过：{e}")
        print("  配置已保存，可以改完再跑一次 python setup.py。")
        return False

    if nav["logged_in"]:
        print(f"\n✅ 登录成功：{nav['username']}（mid {nav['mid']}）")
        return True
    print("\n⚠ 凭据已保存，但 B 站判定为未登录。")
    print("  多半是 SESSDATA 复制不全或已过期——重新登录 B 站再取一次。")
    return False


def main():
    print(BANNER)
    if os.path.exists(CONFIG_PATH):
        print(f"检测到已存在的 {CONFIG_PATH}。")
        answer = input("要覆盖重填吗？(y/N) > ").strip().lower()
        if answer != "y":
            print("已保留原配置，退出。")
            return

    print("\n提示：输入密钥类内容时不会回显，这是正常的。")
    sessdata, bili_jct, mid, buvid3 = guide_cookie()
    deepseek_key = guide_deepseek()
    master_name = guide_master()

    write_config(sessdata, bili_jct, mid, buvid3, deepseek_key, master_name)
    print(f"\n✅ 配置已写入 {CONFIG_PATH}")

    ok = verify()
    if ok:
        print("""
下一步，试试这些命令：

    python bili.py status                       # 看登录状态
    python bili.py feed --source recommend       # 刷推荐流
    python bili.py search "关键词"               # 搜视频
    python bili.py video BV1xx411c7mD            # 视频详情
    python bili.py subtitle BV1xx411c7mD         # 字幕全文

发一条视频总结评论：

    python post_summary_comment.py BV1xx411c7mD \\
        --message "@你的昵称 这条视频讲的是……"
""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消，未写入任何内容。")
        sys.exit(1)
