"""B 站 WBI 请求签名。

移植自 dsh-bili-eye/lib/wbi.js（同一套置换表与算法），改成纯标准库实现，
不依赖任何第三方包。

2023 年起 B 站把大部分 web 接口换成了 WBI 签名：nav 接口下发一对
img_key / sub_key，二者拼接后按固定置换表混淆出 mixinKey；请求方把参数按
key 排序拼成查询串，末尾接 mixinKey 取 md5 得到 w_rid，同时带上秒级 wts。
"""
import hashlib

# 官方混淆置换表：64 个位置，配对后取前 32 位作为 mixinKey。
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def mixin_key_of(img_key, sub_key):
    """由 img_key + sub_key 推出 mixinKey（32 位）。"""
    raw = f"{img_key}{sub_key}"
    return "".join(raw[i] if i < len(raw) else "" for i in MIXIN_KEY_ENC_TAB)[:32]


def wbi_keys_from_nav(nav_data):
    """从 nav 响应里取出这一轮的 wbi 密钥。

    返回 (img_key, sub_key)。缺字段直接抛错——签名拿不到密钥就没法继续。
    """
    img_url = (nav_data or {}).get("wbi_img", {}).get("img_url", "")
    sub_url = (nav_data or {}).get("wbi_img", {}).get("sub_url", "")

    def basename(url):
        return str(url).split("/")[-1].split(".")[0]

    img_key, sub_key = basename(img_url), basename(sub_url)
    if not img_key or not sub_key:
        raise ValueError("B 站 nav 响应里没有 wbi_img，无法为请求签名")
    return img_key, sub_key


def sign_wbi(params, img_key, sub_key, now_ms=None):
    """把参数签名成可直接拼进 URL 的查询串（含 wts 与 w_rid）。"""
    import time
    wts = int(round((now_ms if now_ms is not None else time.time() * 1000) / 1000))
    merged = {**params, "wts": wts}
    pairs = []
    for key in sorted(merged.keys()):
        # 官方实现会先剔除 !'()* 再去 URL 编码，顺序不能换。
        import re
        value = re.sub(r"[!'()*]", "", str(merged[key]))
        from urllib.parse import quote
        pairs.append(f"{quote(str(key), safe='')}={quote(value, safe='')}")
    query = "&".join(pairs)
    w_rid = hashlib.md5((query + mixin_key_of(img_key, sub_key)).encode()).hexdigest()
    return f"{query}&w_rid={w_rid}"
