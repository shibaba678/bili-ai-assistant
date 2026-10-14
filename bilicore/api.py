"""B 站接口层：把 client 的原始响应裁成好用的结构。

覆盖 dsh-bili-eye 的全部能力（读 + 写），再加上它没有的发评论能力：
  · 读：推荐流、热门、排行榜、搜索、视频详情、字幕、评论、楼中楼、观看历史
  · 写：点赞/取消、投币、收藏/取消、查收藏夹
  · 评论：发评论（主楼 / 楼中楼）、删评论
"""
import re

from .client import BiliClient, BiliError, WEB_ORIGIN

# ── 格式化 ────────────────────────────────────────────────────────────────

def _to_float(value, default=0.0):
    """把接口里的脏数据安全转成数字。

    B 站偶尔会吐 "bad" / null / "-" 这类值，直接 float() 会炸掉整条命令。
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_duration(seconds):
    """秒数裁成 mm:ss / h:mm:ss。脏数据当 0 处理，不抛异常。"""
    total = max(0, int(_to_float(seconds)))
    s, m, h = total % 60, (total // 60) % 60, total // 3600
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_count(value):
    """播放量之类的数字裁成中文习惯的短写法。"""
    n = _to_float(value)
    if n >= 1e8:
        return f"{n / 1e8:.1f}亿"
    if n >= 1e4:
        return f"{n / 1e4:.1f}万"
    return str(int(n))


def format_date(unix_seconds):
    """unix 秒 → YYYY-MM-DD。"""
    n = int(_to_float(unix_seconds))
    if not n:
        return ""
    import datetime
    return datetime.datetime.fromtimestamp(n).strftime("%Y-%m-%d")


def parse_clock(text):
    """搜索接口的时长是 "1:3" / "161:53" 字符串，统一转秒。"""
    parts = []
    for piece in str(text or "").split(":"):
        try:
            parts.append(int(piece))
        except ValueError:
            return 0
    total = 0
    for n in parts:
        total = total * 60 + n
    return total


def strip_highlight(text):
    """去掉搜索结果标题里的 <em class="keyword"> 高亮标签。"""
    return re.sub(r"</?em[^>]*>", "", str(text or ""))


class BiliAPI:
    """业务接口封装。持有 BiliClient，所有请求走它的限速队列。"""

    def __init__(self, cookie="", timeout=15, min_interval=0.7, ua=None):
        self.client = BiliClient(cookie=cookie, timeout=timeout,
                                 min_interval=min_interval, ua=ua)

    # ── 账号 ──────────────────────────────────────────────────────────────

    def nav(self):
        """登录态。未登录时 B 站回 -101，那是正常状态。"""
        data = self.client.request("/x/web-interface/nav",
                                   tolerate_codes=(-101,))
        return {
            "logged_in": bool((data or {}).get("isLogin")),
            "username": (data or {}).get("uname") or "",
            "mid": (data or {}).get("mid") or 0,
            "vip": (data or {}).get("vipStatus") == 1,
        }

    def status(self):
        """给模型看的账号状态摘要。"""
        nav = self.nav()
        return {
            "logged_in": nav["logged_in"],
            "username": nav["username"],
            "mid": nav["mid"],
            "vip": nav["vip"],
            "has_credential": bool(self.client.cookie),
            "writes_ready": bool(self.client.csrf_token()),
        }

    # ── 刷视频 ────────────────────────────────────────────────────────────

    def recommend(self, page_size=12, fresh_idx=1):
        """首页推荐流。未登录也能用，登录后个性化。"""
        self.client.ensure_anon_device()
        data = self.client.request(
            "/x/web-interface/wbi/index/top/feed/rcmd", wbi=True, params={
                "ps": page_size, "fresh_type": 4, "feed_version": "V8",
                "fresh_idx": fresh_idx, "fresh_idx_1h": fresh_idx,
                "fetch_row": 1, "brush": fresh_idx, "homepage_ver": 2})
        items = data.get("item") if isinstance(data, dict) else None
        return [
            {
                "bvid": it.get("bvid"), "aid": it.get("id"),
                "title": it.get("title"),
                "author": (it.get("owner") or {}).get("name"),
                "duration": format_duration(it.get("duration")),
                "views": format_count((it.get("stat") or {}).get("view")),
                "published_at": format_date(it.get("pubdate")),
            }
            for it in (items or [])
            if it and it.get("goto") == "av" and it.get("bvid")
        ]

    def popular(self, page_size=20, page=1):
        """综合热门。"""
        self.client.ensure_anon_device()
        data = self.client.request("/x/web-interface/popular",
                                   params={"ps": page_size, "pn": page})
        return [self._brief(it) for it in ((data or {}).get("list") or [])]

    def ranking(self, rid=0, page_size=20):
        """排行榜。rid=0 全站。接口固定吐 100 条，按 page_size 截断。"""
        self.client.ensure_anon_device()
        data = self.client.request("/x/web-interface/ranking/v2",
                                   params={"rid": rid, "type": "all"})
        items = (data or {}).get("list") or []
        return [self._brief(it) for it in items[:max(1, page_size)]]

    def search(self, keyword, page=1, page_size=20, order="totalrank"):
        """搜索视频。强依赖 Cookie，没 buvid3 会 -412。"""
        self.client.ensure_anon_device()
        data = self.client.request(
            "/x/web-interface/wbi/search/type", wbi=True, params={
                "search_type": "video", "keyword": keyword, "page": page,
                "page_size": page_size, "order": order})
        return [
            {
                "bvid": it.get("bvid"), "aid": it.get("aid"),
                "title": strip_highlight(it.get("title")),
                "author": it.get("author"),
                "duration": format_duration(parse_clock(it.get("duration"))),
                "views": format_count(it.get("play")),
                "danmaku": format_count(it.get("video_review")),
                "published_at": format_date(it.get("pubdate")),
                "description": strip_highlight(it.get("description"))[:120],
            }
            for it in ((data or {}).get("result") or [])
        ]

    @staticmethod
    def _brief(it):
        return {
            "bvid": it.get("bvid"), "aid": it.get("aid"),
            "title": it.get("title"),
            "author": (it.get("owner") or {}).get("name"),
            "duration": format_duration(it.get("duration")),
            "views": format_count((it.get("stat") or {}).get("view")),
            "published_at": format_date(it.get("pubdate")),
        }

    # ── 视频详情与字幕 ────────────────────────────────────────────────────

    def video(self, bvid=None, aid=None):
        """视频详情：标题、UP、简介、分P、互动数据。"""
        params = {"bvid": bvid} if bvid else {"aid": aid}
        data = self.client.request("/x/web-interface/view", params=params)
        if not data:
            raise BiliError("视频不存在或已被删除")
        return {
            "bvid": data.get("bvid"), "aid": data.get("aid"),
            "cid": data.get("cid"), "title": data.get("title"),
            "author": (data.get("owner") or {}).get("name"),
            "author_mid": (data.get("owner") or {}).get("mid"),
            "duration": format_duration(data.get("duration")),
            "duration_seconds": data.get("duration"),
            "published_at": format_date(data.get("pubdate")),
            "views": format_count((data.get("stat") or {}).get("view")),
            "likes": format_count((data.get("stat") or {}).get("like")),
            "coins": format_count((data.get("stat") or {}).get("coin")),
            "favorites": format_count((data.get("stat") or {}).get("favorite")),
            "danmaku": format_count((data.get("stat") or {}).get("danmaku")),
            "description": (data.get("desc") or "")[:600],
            "pages": [
                {"cid": p.get("cid"), "index": p.get("page"),
                 "title": p.get("part"),
                 "duration": format_duration(p.get("duration"))}
                for p in (data.get("pages") or [])
            ],
        }

    def subtitle(self, bvid=None, cid=None, lang=None):
        """字幕全文。走 player/wbi/v2，需要 WBI 签名。无字幕返回 available=False。"""
        detail = self.video(bvid=bvid) if bvid else None
        target_cid = cid or (detail or {}).get("cid")
        data = self.client.request("/x/player/wbi/v2", wbi=True, params={
            "bvid": (detail or {}).get("bvid") or bvid, "cid": target_cid})
        tracks = ((data or {}).get("subtitle") or {}).get("subtitles") or []
        if not tracks:
            return {"available": False, "tracks": [], "lines": [], "text": ""}
        picked = (
            (lang and next((t for t in tracks if str(t.get("lan", "")).startswith(lang)), None))
            or next((t for t in tracks if str(t.get("lan", "")).startswith("zh")), None)
            or tracks[0])
        url = picked.get("subtitle_url") or ""
        if url.startswith("//"):
            url = "https:" + url
        body = self.client.request_absolute(url) if url else None
        lines = [
            {"from": ln.get("from"), "to": ln.get("to"), "text": ln.get("content")}
            for ln in ((body or {}).get("body") or [])
        ]
        return {
            "available": bool(lines),
            "language": picked.get("lan_doc") or picked.get("lan"),
            "tracks": [{"lang": t.get("lan"), "label": t.get("lan_doc")}
                       for t in tracks],
            "lines": lines,
            "text": "\n".join(ln["text"] for ln in lines if ln["text"]),
        }

    # ── 评论 ──────────────────────────────────────────────────────────────

    def comments(self, aid, page=1, page_size=20, mode=3):
        """评论主楼。mode 3=热度（默认），2=时间。"""
        data = self.client.request("/x/v2/reply/wbi/main", wbi=True, params={
            "oid": aid, "type": 1, "mode": mode,
            "next": max(1, int(page or 1)),
            "ps": min(30, max(1, int(page_size or 20)))})
        cursor = (data or {}).get("cursor") or {}
        replies = (data or {}).get("replies") or []
        if not replies and int(cursor.get("all_count") or 0) > 0:
            raise BiliError("评论列表被登录墙拦下：请确认凭据已配置且未过期")
        return {
            "total_count": int(cursor.get("all_count") or 0),
            "is_end": bool(cursor.get("is_end")),
            "page": max(1, int(page or 1)),
            "replies": [self._project_comment(r, True) for r in replies],
        }

    def comment_replies(self, aid, root, page=1, page_size=20):
        """楼中楼翻页。root 是主楼 rpid。"""
        data = self.client.request("/x/v2/reply/reply", params={
            "oid": aid, "type": 1, "root": root,
            "pn": max(1, int(page or 1)),
            "ps": min(30, max(1, int(page_size or 20)))})
        cursor = (data or {}).get("cursor") or {}
        replies = (data or {}).get("replies") or []
        return {
            "root": int(root or 0),
            "total_count": int(cursor.get("all_count") or len(replies)),
            "is_end": bool(cursor.get("is_end")),
            "page": max(1, int(page or 1)),
            "replies": [self._project_comment(r, False) for r in replies],
        }

    @staticmethod
    def _project_comment(reply, with_preview):
        member = reply.get("member") or {}
        out = {
            "rpid": int(reply.get("rpid") or 0),
            "author": member.get("uname") or "",
            "mid": member.get("mid") or 0,
            "level": (member.get("level_info") or {}).get("current_level"),
            "content": str((reply.get("content") or {}).get("message") or "")[:500],
            "likes": int(reply.get("like") or 0),
            "reply_count": int(reply.get("rcount") or 0),
            "published_at": format_date(reply.get("ctime")),
            "state": reply.get("state"),
            "ip_location": (reply.get("reply_control") or {}).get("location") or "",
        }
        if with_preview and reply.get("replies"):
            out["replies"] = [BiliAPI._project_comment(s, False)
                              for s in reply["replies"][:3]]
        return out

    def history(self, page_size=20):
        """观看历史。未登录回 -101，翻译成看得懂的错误。"""
        data = self.client.request("/x/web-interface/history/cursor",
                                   tolerate_codes=(-101,),
                                   params={"ps": page_size, "business": ""})
        if not data:
            raise BiliError("观看历史需要登录态：当前没有凭据，或 SESSDATA 已过期")
        return [
            {
                "bvid": (it.get("history") or {}).get("bvid"),
                "aid": (it.get("history") or {}).get("oid"),
                "title": it.get("title"), "author": it.get("author_name"),
                "duration": format_duration(it.get("duration")),
                "progress": format_duration(it.get("progress")),
                "watched_at": format_date(it.get("view_at")),
            }
            for it in (data.get("list") or [])
        ]

    # ── 写操作 ────────────────────────────────────────────────────────────

    def _csrf(self):
        token = self.client.csrf_token()
        if not token:
            raise BiliError("需要 bili_jct，当前凭据里没有——请重新导出一份完整 Cookie")
        return token

    def like(self, bvid, like=True):
        """点赞 / 取消点赞。"""
        self.client.request("/x/web-interface/archive/like", method="POST",
                            body={"bvid": bvid, "like": 1 if like else 0,
                                  "csrf": self._csrf()})
        return {"bvid": bvid, "liked": bool(like)}

    def has_liked(self, bvid):
        """查是否已点赞（避免重复操作）。"""
        data = self.client.request("/x/web-interface/archive/has/like",
                                   params={"bvid": bvid})
        return bool(data)

    def coin(self, bvid, count=1, also_like=False):
        """投币。count 只能是 1 或 2。

        注意：这个接口**不要** WBI 签名。参数只放表单体，一旦同时拼进
        query 串，B 站会判定为非法访问（-401）。实测纯 POST 表单即可通过。
        """
        multiply = 2 if int(count) == 2 else 1
        self.client.request("/x/web-interface/coin/add", method="POST",
                            body={"bvid": bvid, "multiply": multiply,
                                  "select_like": 1 if also_like else 0,
                                  "csrf": self._csrf()})
        return {"bvid": bvid, "coins": multiply}

    def fav(self, bvid, add_ids=(), del_ids=()):
        """收藏 / 取消收藏。需要收藏夹 id（先调 fav_folders）。"""
        detail = self.video(bvid=bvid)
        body = {"rid": detail["aid"], "type": 2, "csrf": self._csrf()}
        if add_ids:
            body["add_media_ids"] = ",".join(str(i) for i in add_ids)
        if del_ids:
            body["del_media_ids"] = ",".join(str(i) for i in del_ids)
        self.client.request("/x/v3/fav/resource/deal", method="POST", body=body)
        return {"bvid": bvid, "added_to": list(add_ids),
                "removed_from": list(del_ids)}

    def fav_folders(self):
        """收藏夹列表，给 fav 提供合法 id。"""
        nav = self.nav()
        if not nav["logged_in"] or not nav["mid"]:
            raise BiliError("列出收藏夹需要登录态，当前凭据未登录")
        data = self.client.request("/x/v3/fav/folder/created/list-all",
                                   params={"up_mid": nav["mid"]})
        return [
            {"id": f.get("id"), "title": f.get("title"),
             "count": f.get("media_count")}
            for f in ((data or {}).get("list") or [])
        ]

    # ── 发评论（dsh-bili-eye 没有的能力）──────────────────────────────────

    def post_comment(self, aid, message, root=0, parent=0):
        """发评论。root=parent=0 是主楼；都填主楼 rpid 是楼中楼。

        返回 rpid。B 站对新账号有先审后发（state=17），成功返回不代表立刻公开。
        """
        body = {
            "type": 1, "oid": aid, "message": message,
            "root": root, "parent": parent, "plat": 1,
            "csrf": self._csrf(), "csrf_token": self._csrf(),
        }
        data = self.client.request("/x/v2/reply/add", method="POST", body=body)
        return {"rpid": int((data or {}).get("rpid") or 0)}

    def del_comment(self, aid, rpid):
        """删自己的评论。"""
        self.client.request("/x/v2/reply/del", method="POST", body={
            "type": 1, "oid": aid, "rpid": rpid,
            "csrf": self._csrf(), "csrf_token": self._csrf()})
        return {"deleted": True, "rpid": rpid}

    def comment_by_rpid(self, aid, rpid):
        """按 rpid 查一条评论（含 state 与 @ 解析结果）。"""
        data = self.client.request("/x/v2/reply/reply", params={
            "oid": aid, "type": 1, "root": rpid, "pn": 1, "ps": 1})
        root = (data or {}).get("root")
        if not root:
            return None
        out = self._project_comment(root, False)
        out["members"] = [
            {"uname": m.get("uname"), "mid": m.get("mid")}
            for m in ((root.get("content") or {}).get("members") or [])
        ]
        return out
