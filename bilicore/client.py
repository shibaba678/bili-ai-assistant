"""B 站请求层。

整合自 dsh-bili-eye/lib/client.js 的设计优点，改成纯标准库实现：

  1. 串行限速：所有请求排一条队，两次之间至少隔 min_interval 毫秒——
     避免把账号打成风控靶子。
  2. WBI 密钥缓存：nav 下发的密钥每天轮换，缓存 30 分钟。
  3. 匿名设备标识回收：从响应 Set-Cookie 里收 buvid3/buvid4 等，
     没有它们搜索接口会直接回 -412 风控。
  4. 错误信息不回显 Cookie 值——错误会进日志。
  5. 业务 code 白名单：未登录的 -101 是正常状态，不是错误。
"""
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .wbi import sign_wbi, wbi_keys_from_nav

log = logging.getLogger("bilicore")

API_ORIGIN = "https://api.bilibili.com"
WEB_ORIGIN = "https://www.bilibili.com"
DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 需要长期留用的匿名 Cookie：没有它们，搜索等接口会直接回 -412 风控。
ANON_COOKIE_NAMES = re.compile(r"^(buvid3|buvid4|b_nut|buvid_fp|_uuid)$")
# WBI 密钥的复用窗口。
WBI_TTL_S = 30 * 60


class BiliError(Exception):
    """B 站接口返回 code != 0 时抛这个，带上 code 便于上层区分未登录 / 风控。"""

    def __init__(self, message, code=None, path=None):
        super().__init__(message)
        self.code = code
        self.path = path


class BiliClient:
    """串行限速的 B 站客户端。线程安全（限速队列用锁保护）。"""

    def __init__(self, cookie="", timeout=15, min_interval=0.7, ua=None):
        self.cookie = cookie or ""
        self.timeout = timeout
        self.min_interval = max(0.1, min_interval)
        self.ua = ua or DEFAULT_UA
        self._anon = {}
        self._anon_probed = False
        self._wbi = None          # {img_key, sub_key, at}
        self._last_at = 0.0
        self._lock = threading.Lock()

    # ── 限速 ──────────────────────────────────────────────────────────────

    def _throttle(self):
        """串行限速：两次请求之间至少隔 min_interval 秒。"""
        with self._lock:
            wait = self.min_interval - (time.time() - self._last_at)
            if wait > 0:
                time.sleep(wait)
            self._last_at = time.time()

    # ── Cookie 组装 ───────────────────────────────────────────────────────

    def cookie_header(self):
        """主人凭据优先，匿名设备标识补位。"""
        parts = []
        if self.cookie:
            parts.append(self.cookie.rstrip("; "))
        for name, value in self._anon.items():
            if not re.search(rf"(?:^|;\s*){re.escape(name)}=", self.cookie):
                parts.append(f"{name}={value}")
        return "; ".join(parts)

    def csrf_token(self):
        """从 Cookie 串里取 bili_jct —— 写操作的 CSRF 令牌。"""
        m = re.search(r"(?:^|;\s*)bili_jct=([^;]+)", self.cookie_header())
        return m.group(1) if m else None

    def _absorb_set_cookie(self, headers):
        """记住响应下发的匿名 Cookie。"""
        lines = headers.get_all("Set-Cookie") or []
        for line in lines:
            pair = line.split(";")[0]
            if "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            name, value = name.strip(), value.strip()
            if value and ANON_COOKIE_NAMES.match(name):
                self._anon[name] = value

    # ── 请求 ──────────────────────────────────────────────────────────────

    def request(self, path, params=None, method="GET", body=None,
                wbi=False, tolerate_codes=()):
        """发一个接口请求，返回解包后的 data。"""
        self._throttle()

        url = API_ORIGIN + path
        query = dict(params or {})
        if wbi:
            # 签名放在限速之后算：wts 是秒级时间戳，排队等太久会让签名过期。
            # POST 也能带签名——签名串拼在 URL 上，表单体照旧放 body。
            img_key, sub_key = self.wbi_keys()
            url += "?" + sign_wbi(query, img_key, sub_key)
        elif query:
            url += "?" + urllib.parse.urlencode(query)

        headers = {
            "User-Agent": self.ua,
            "Referer": WEB_ORIGIN + "/",
            "Origin": WEB_ORIGIN,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "application/json, text/plain, */*",
        }
        cookie = self.cookie_header()
        if cookie:
            headers["Cookie"] = cookie

        data = None
        if method == "POST":
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = urllib.parse.urlencode(
                {k: str(v) for k, v in (body or {}).items()}).encode()

        req = urllib.request.Request(url, data=data, headers=headers,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self._absorb_set_cookie(resp.headers)
                text = resp.read().decode("utf-8", "replace")
                status = resp.status
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            status = e.code
        except Exception as e:
            raise BiliError(f"请求 B 站失败：{e}") from e

        try:
            payload = json.loads(text)
        except ValueError:
            # 风控页 / 维护页会直接吐 HTML。
            raise BiliError(
                f"B 站返回了非 JSON 响应（HTTP {status}），通常是被风控拦下：{path}",
                path=path)

        code = payload.get("code")
        if code != 0 and code not in tolerate_codes:
            raise BiliError(
                f"B 站接口报错 code={code}：{payload.get('message') or '(无消息)'}",
                code=code, path=path)
        return payload.get("data")

    def request_absolute(self, url):
        """请求一个绝对 URL（字幕 JSON 挂在另一台域名上，不带 API 前缀）。"""
        self._throttle()
        req = urllib.request.Request(url, headers={
            "User-Agent": self.ua, "Referer": WEB_ORIGIN + "/"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except Exception as e:
            raise BiliError(f"请求字幕文件失败：{e}") from e

    def wbi_keys(self):
        """取（并缓存）当前 WBI 密钥。"""
        now = time.time()
        if self._wbi and now - self._wbi["at"] < WBI_TTL_S:
            return self._wbi["img_key"], self._wbi["sub_key"]
        nav = self.request("/x/web-interface/nav", tolerate_codes=(-101,))
        img_key, sub_key = wbi_keys_from_nav(nav)
        self._wbi = {"img_key": img_key, "sub_key": sub_key, "at": now}
        return img_key, sub_key

    def ensure_anon_device(self):
        """没有从主人凭据拿到 buvid3 时，主动去主站领一个。只做一次。"""
        if self._anon_probed:
            return
        self._anon_probed = True
        if any(n.startswith("buvid") for n in self._anon):
            return
        try:
            req = urllib.request.Request(WEB_ORIGIN + "/", headers={
                "User-Agent": self.ua, "Accept-Language": "zh-CN,zh;q=0.9"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self._absorb_set_cookie(resp.headers)
                resp.read()
        except Exception:
            # 拿不到就算了，公开接口大多还能用。
            pass
