# Bili AI Assistant

> 让 AI 助手帮你刷 B 站、看字幕、总结视频，并在评论区 **@你** 交作业。

一个不依赖第三方库的 B 站工具集：**刷推荐流 → 搜视频 → 读字幕 → 总结 → 点赞 → 发评论 @你**。
自带完整 CLI，也能直接接进任何支持工具调用的 AI 助手（Claude Code、Cursor、DSH 等）。

**用你自己的 B 站账号、你自己的 AI 密钥** —— 本项目不含任何人的凭据，
第一次运行时会有一个向导带你填自己的。

---

## 目录

- [能做什么](#能做什么)
- [快速开始](#快速开始)
- [完整命令](#完整命令)
- [接入 AI 助手](#接入-ai-助手)
- [凭据是怎么处理的](#凭据是怎么处理的)
- [风险与合规](#风险与合规)
- [常见问题](#常见问题)
- [项目结构](#项目结构)

---

## 能做什么

| 能力 | 命令 | 说明 |
| --- | --- | --- |
| 账号状态 | `bili.py status` | 看登录态、凭据是否就绪 |
| 刷推荐流 | `bili.py feed --source recommend` | 按你的口味推（需登录） |
| 全站热门 | `bili.py feed --source popular` | |
| 排行榜 | `bili.py feed --source ranking --rid 0` | `rid` 是分区 id，0 为全站 |
| 搜视频 | `bili.py search "关键词"` | 支持按播放/最新/弹幕/收藏排序 |
| 视频详情 | `bili.py video BV1xx411c7mD` | 标题、UP、简介、分P、互动数据 |
| **字幕全文** | `bili.py subtitle BV1xx411c7mD` | 带时间轴；AI 总结的主要原料 |
| 评论主楼 | `bili.py comments BV1xx411c7mD` | 按热度或时间，带楼中楼预览 |
| 楼中楼 | `bili.py replies BV1xx411c7mD --rpid 123` | |
| 查评论状态 | `bili.py checkcomment BV1xx411c7mD --rpid 123` | 看是否过审、@ 有没有挂上 |
| 观看历史 | `bili.py history` | |
| 点赞 | `bili.py like BV1xx411c7mD` | 顺手养号 |
| 投币 | `bili.py coin BV1xx411c7mD --count 1` | |
| 收藏 | `bili.py fav BV1xx411c7mD --folder 123` | 先 `favfolders` 查 id |
| **发评论** | `bili.py comment BV1xx411c7mD --message "..."` | 主楼或楼中楼 |
| 删评论 | `bili.py delcomment BV1xx411c7mD --rpid 123` | |
| **发总结评论** | `post_summary_comment.py BV1xx411c7mD --message "..."` | 一条命令走完：点赞 + @你 + 发总结 |

所有命令输出 **JSON**，方便脚本或 AI 直接消费。

### 两个典型玩法

**① 手动总结一条视频**

```bash
python bili.py subtitle BV1hyWF61EnQ          # 拿字幕
python post_summary_comment.py BV1hyWF61EnQ \
    --message "@你的昵称 这条视频讲的是……"      # 发到评论区并 @ 你
```

**② 让 AI 助手自动干**

把本项目接进 AI 助手（见 [接入 AI 助手](#接入-ai-助手)），然后对它说：

> 去 B 站搜「科幻 解说」，挑一个没看过的，总结给我，在评论区 @ 我

助手就会自己搜 → 读字幕 → 总结 → 发评论 @你。你在 B 站会收到通知。

---

## 快速开始

### 环境要求

- **Python 3.11 或更高**（用到内置 `tomllib`）
- 无第三方依赖，不用 `pip install` 任何东西

### 三步跑起来

```bash
# 1. 下载
git clone https://github.com/<你的用户名>/bili-ai-assistant.git
cd bili-ai-assistant

# 2. 配置向导（引导你填自己的 Cookie 与密钥）
python setup.py

# 3. 验证
python bili.py status
```

`setup.py` 会一步步问你：

| 问什么 | 从哪拿 |
| --- | --- |
| **SESSDATA** | 浏览器登录 B 站 → F12 → Application → Cookies → `https://www.bilibili.com` → 复制该项的 Value |
| **bili_jct** | 同上，CSRF 令牌，点赞和发评论必需 |
| **UID** | 打开 `space.bilibili.com/`，看你主页地址里的数字 |
| **buvid3**（可留空） | 同上，设备标识；留空程序会自己领 |
| **DeepSeek Key**（可跳过） | https://platform.deepseek.com/ → API Keys |
| **要 @ 的昵称** | 你自己的 B 站昵称，一字不差 |

向导会把配置写进 `config.toml`（已在 `.gitignore` 里，不会被误提交），
并当场验证一次登录是否成功。

> **跳过 DeepSeek 也能用**：只是自动总结用不了，你仍然可以用
> `--message` 自己给文案，其余功能全部可用。

### 跑测试（可选）

```bash
python tests/test_all.py
```

7 项测试，不需要网络也不需要凭据。

---

## 完整命令

```bash
# ── 读 ────────────────────────────────────────────────
python bili.py status
python bili.py feed --source recommend --size 12 [--fresh 2]
python bili.py feed --source popular [--page 1]
python bili.py feed --source ranking [--rid 0] [--size 20]
python bili.py search "关键词" [--order click|pubdate|dm|stow] [--page 1]
python bili.py video BV1xx411c7mD
python bili.py subtitle BV1xx411c7mD [--lang zh-CN] [--max-chars 12000]
python bili.py comments BV1xx411c7mD [--page 1] [--size 20] [--sort hot|time]
python bili.py replies BV1xx411c7mD --rpid 123 [--page 1]
python bili.py checkcomment BV1xx411c7mD --rpid 123
python bili.py history

# ── 写 ────────────────────────────────────────────────
python bili.py like BV1xx411c7mD [--unlike]
python bili.py coin BV1xx411c7mD [--count 1|2] [--also-like]
python bili.py favfolders
python bili.py fav BV1xx411c7mD [--folder 123] [--unfav]
python bili.py comment BV1xx411c7mD --message "@某人 内容" [--root R --parent P]
python bili.py delcomment BV1xx411c7mD --rpid 123

# ── 一条命令发总结 ────────────────────────────────────
python post_summary_comment.py BV1xx411c7mD --message "文案"
python post_summary_comment.py BV1xx411c7mD              # 调 DeepSeek 自动总结
python post_summary_comment.py BV1xx411c7mD --dry-run     # 只看文案不发
python post_summary_comment.py BV1xx411c7mD --no-like     # 不点赞

# ── 常驻监听（可选）────────────────────────────────────
python monitor.py
```

`monitor.py` 会轮询 `config.toml` 里 `watch_list.bvids` 的视频，
发现有人 @ 你配置的昵称，就自动总结并楼中楼回复。
每个视频的总结只生成一次并缓存，重复召唤不重复烧 token。

---

## 接入 AI 助手

本项目本质是一组**命令行工具**，任何能执行 shell 命令的 AI 助手都能用。
把下面这段贴进助手的系统提示词或项目说明里即可：

````markdown
# B 站助手工具

你可以用这些命令操作 B 站（工作目录：bili-ai-assistant）：

- 刷视频：`python bili.py feed --source recommend|popular|ranking`
- 搜视频：`python bili.py search "关键词"`
- 视频详情：`python bili.py video <bvid>`
- 字幕全文：`python bili.py subtitle <bvid>`
- 评论区：`python bili.py comments <bvid> [--sort time|hot]`
- 观看历史：`python bili.py history`
- 点赞：`python bili.py like <bvid>`
- 投币：`python bili.py coin <bvid> --count 1`
- 收藏：`python bili.py fav <bvid> --folder <id>`
- 发评论：`python bili.py comment <bvid> --message "内容"`

典型任务：用户说「总结这个视频并在评论区 @ 我」时——
1. `bili.py subtitle <bvid>` 拿字幕（无字幕则用 `bili.py video` 的简介）
2. 自己写成一段自然的总结（不要编号、不要罗列，像聊天一样）
3. `post_summary_comment.py <bvid> --message "<总结>"` 发出去

注意：
- 所有命令输出 JSON，直接解析即可
- 发评论前先用 `--dry-run` 预览文案
- 不要连续大量调用，两次写操作之间至少隔几秒
- 评论发出后可能是 state=17（审核中），这是正常的，不代表失败
````

### 如果你想接 DSH / Claude Code 这类支持工具调用的助手

给每条命令包一个工具定义即可，参数照抄 `bili.py --help`。
参考实现见本项目最初的设计——`bilicore/api.py` 里的每个方法都是一一对应的：

| 方法 | 对应命令 |
| --- | --- |
| `api.recommend()` / `popular()` / `ranking()` | `feed` |
| `api.search(keyword)` | `search` |
| `api.video(bvid)` | `video` |
| `api.subtitle(bvid)` | `subtitle` |
| `api.comments(aid)` | `comments` |
| `api.post_comment(aid, msg)` | `comment` |
| `api.like(bvid)` / `coin()` / `fav()` | `like` / `coin` / `fav` |

---

## 凭据是怎么处理的

- 凭据**只存在你本机的 `config.toml`**，权限设为 600（尽力而为）。
- 本项目**不含**任何人的 Cookie 或密钥，clone 下来是空的。
- `config.toml` 已在 `.gitignore` 里，`git status` 不会看到它。
- 错误信息**不回显 Cookie 值**——错误会进日志，cookie 不能跟着进去。
- 全程不联网上传，`setup.py` 只写本地文件。

> ⚠️ **绝对不要把 Cookie 贴进任何 AI 对话**。对话内容会被完整记录并长期留存，
> 等于把账号交出去。用 `setup.py` 在本地填。

---

## 风险与合规

- **自动化访问 B 站违反其用户协议**。账号可能触发风控、被限制甚至封禁，
  这个代价由账号持有者承担。
- 本项目把请求频率压到最低（所有请求**串行**，最小间隔 0.7 秒），
  但**不能替你消除风险**。
- **不做**：批量播放、挂时长、模拟观看上报、任何形式的刷量。
  这类用法不是「做不到」，是会把账号变成制造虚假数据的工具——
  代码里没有这些路径，也不接受这类 PR。
- 评论内容由你负责。请遵守 B 站社区规定，别用来刷屏或骚扰。
- 建议先用**小号**试，别拿常用大号折腾。

### 关于审核

B 站对新账号有**先审后发**机制：

- 评论发出后接口返回成功，但状态是 `state=17`（审核中），公开评论区暂时看不到
- 审核通过后才公开，**@ 通知也才送达**
- 在**自己的视频**下评论通常秒过（`state=0`）
- 养号一段时间（看视频、正常互动、提升等级）后审核会变快

用 `bili.py checkcomment <bvid> --rpid <rpid>` 可以查状态。
`content.members` 里出现被 @ 的账号，说明 @ 解析成功。

---

## 常见问题

**Q：报「找不到配置文件」**
A：跑 `python setup.py` 生成 `config.toml`。

**Q：报「B 站判定为未登录」**
A：SESSDATA 复制不全或已过期。重新登录 B 站再取一次，重跑 `setup.py`。

**Q：字幕拿不到（`available: false`）**
A：这个视频没有 CC 字幕。用 `bili.py video` 的简介兜底，或让 AI 只看标题和简介。

**Q：搜索报 `-412` 风控**
A：缺 `buvid3`。重跑 `setup.py` 填上，或确保能访问主站（程序会自动领一个）。

**Q：投币报 `-401 非法访问`**
A：这个接口**不能加 WBI 签名**（参数进了 query 串就会被判非法）。
本项目已处理；如果你自己改代码，别给它加签名。

**Q：取消点赞失败（`-400`）**
A：B 站 `archive/like` 接口 `like=0` 目前一律回 `-400`，点赞本身正常。
本项目只用点赞养号，不影响主流程。

**Q：评论发出去了，但我在别的账号看不到**
A：`state=17` 审核中。等审核通过。

**Q：怎么知道 @ 成功了？**
A：`bili.py checkcomment <bvid> --rpid <rpid>`，看 `members` 字段有没有被 @ 的账号。

---

## 项目结构

```
bili-ai-assistant/
├── setup.py                    配置向导：填自己的账号与密钥
├── bili.py                     统一 CLI（所有功能）
├── post_summary_comment.py     发「@某人 + 总结」评论
├── monitor.py                  常驻监听 @召唤（可选）
├── config.example.toml         配置模板（供手动填写）
├── requirements.txt            依赖说明（无第三方依赖）
├── bilicore/
│   ├── config.py               配置加载与校验、Cookie 组装
│   ├── wbi.py                  WBI 请求签名
│   ├── client.py               请求层：串行限速、匿名设备、WBI 缓存
│   └── api.py                  业务接口：读 + 写 + 发评论
└── tests/
    └── test_all.py             7 项自包含测试（不需要网络）
```

### 为什么是纯标准库

只依赖 Python 标准库（`urllib`、`hashlib`、`json`、`tomllib`），
不需要 `pip install`，clone 下来就能跑。

### WBI 签名

2023 年起 B 站大部分 web 接口要求签名：`nav` 接口下发一对
`img_key` / `sub_key`，按固定置换表混淆出 `mixinKey`，参数按 key 排序
拼接后加 `mixinKey` 取 md5 得到 `w_rid`。

`bilicore/wbi.py` 实现了这套算法，`tests/test_all.py` 里用**黄金向量**
锁定了 4 组期望值（含中文参数编码），算法改错立刻会红。

---

## License

MIT —— 见 [LICENSE](LICENSE)。

## 致谢

设计上参考了 [dsh-bili-eye](https://github.com/) 的请求层思路：
串行限速、WBI 签名缓存、匿名设备标识回收、错误不回显凭据。
