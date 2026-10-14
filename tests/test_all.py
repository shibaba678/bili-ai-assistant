"""自包含测试：不需要网络，不需要凭据。

    python tests/test_all.py        或        python -m pytest tests/ -q

覆盖 WBI 签名算法、格式化函数、以及 @召唤 的完整逻辑流。
WBI 用「黄金向量」锁定算法——这些期望值来自社区标准实现（与 B 站
前端行为一致），算法一旦被改错，这里立刻会红。
"""
import os
import sys
import tempfile

# 让 tests/ 里的脚本能 import 到项目根的 bilicore
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bilicore.wbi as wbi                                    # noqa: E402
from bilicore.api import (format_count, format_date,          # noqa: E402
                          format_duration, parse_clock)
import monitor                                                # noqa: E402


# ── WBI 签名（黄金向量）──────────────────────────────────────────────────
#
# 期望值由社区标准实现独立算出（置换表 + md5(query + mixinKey)），
# 与 B 站前端一致。固定时间戳 now_ms=1700000000000 → wts=1700000000。
NOW = 1700000000000

GOLDEN = [
    {
        "params": {"a": 1, "b": 2}, "img": "imgkey", "sub": "subkey",
        "signed": "a=1&b=2&wts=1700000000&w_rid=a6aaf5170b739ad0afb6e026b7b88bd2",
        "mixin": "gbekykuimesy",
    },
    {
        "params": {"q": "a!b(c)"}, "img": "i", "sub": "s",
        "signed": "q=abc&wts=1700000000&w_rid=b3e6f0fdf1c27cbcbac32192f50126cf",
        "mixin": "is",
    },
    {
        # 中文参数 + 空格：验证 URL 编码路径
        "params": {"keyword": "大肥鱼 二创", "page": 1},
        "img": "7cd084941338484aae1ad9425b84077c",
        "sub": "4932caff0ff746eab6f01bf08b70ac45",
        "signed": ("keyword=%E5%A4%A7%E8%82%A5%E9%B1%BC%20%E4%BA%8C%E5%88%9B"
                   "&page=1&wts=1700000000"
                   "&w_rid=a1ae8ec3c2efe5cca4e10a800e93ba24"),
        "mixin": "ea1db124af3c7062474693fa704f4ff8",
    },
    {
        # 参数乱序输入：签名前必须按 key 排序
        "params": {"oid": 117431653635609, "type": 1, "mode": 3,
                   "next": 1, "ps": 20},
        "img": "aaa", "sub": "bbb",
        "signed": ("mode=3&next=1&oid=117431653635609&ps=20&type=1"
                   "&wts=1700000000"
                   "&w_rid=b1a4b46235440c981dcec0a0447e485c"),
        "mixin": "abbaab",
    },
]


def test_wbi_golden():
    for i, case in enumerate(GOLDEN, 1):
        got = wbi.sign_wbi(case["params"], case["img"], case["sub"], now_ms=NOW)
        assert got == case["signed"], (
            f"用例{i} 签名不一致\n  期望: {case['signed']}\n  实际: {got}")
        mixin = wbi.mixin_key_of(case["img"], case["sub"])
        assert mixin == case["mixin"], (
            f"用例{i} mixinKey 不一致: 期望 {case['mixin']}，实际 {mixin}")
    print(f"PASS 1: WBI 签名黄金向量（{len(GOLDEN)} 例）")


def test_wbi_keys_from_nav():
    nav = {"wbi_img": {
        "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
        "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png",
    }}
    img_key, sub_key = wbi.wbi_keys_from_nav(nav)
    assert img_key == "7cd084941338484aae1ad9425b84077c"
    assert sub_key == "4932caff0ff746eab6f01bf08b70ac45"
    # 缺字段必须抛错，不能静默返回空串
    for bad in ({}, {"wbi_img": {}}, {"wbi_img": {"img_url": "x.png"}}):
        try:
            wbi.wbi_keys_from_nav(bad)
            raise AssertionError(f"缺 wbi_img 时应抛错，输入={bad}")
        except ValueError:
            pass
    print("PASS 2: WBI 密钥解析与缺字段防护")


def test_perm_table():
    # 置换表必须是官方那 64 个位置
    assert len(wbi.MIXIN_KEY_ENC_TAB) == 64
    assert sorted(wbi.MIXIN_KEY_ENC_TAB) == list(range(64)), "置换表必须覆盖 0..63"
    assert len(wbi.mixin_key_of("x" * 64, "y" * 64)) == 32
    print("PASS 3: 置换表完整性")


# ── 格式化 ───────────────────────────────────────────────────────────────

def test_format():
    assert format_duration(65) == "1:05"
    assert format_duration(3665) == "1:01:05"
    assert format_duration(0) == "0:00"
    assert format_duration("bad") == "0:00"          # 脏数据不炸
    assert format_count(1234) == "1234"
    assert format_count(12345) == "1.2万"
    assert format_count(123456789) == "1.2亿"
    assert format_count(None) == "0"
    assert parse_clock("1:3") == 63
    assert parse_clock("161:53") == 9713
    assert parse_clock("bad") == 0
    assert format_date(0) == ""
    print("PASS 4: 格式化函数（含脏数据）")


# ── @召唤 逻辑流（mock 网络）─────────────────────────────────────────────

class FakeAPI:
    """假 API：固定评论列表，记录发评论调用。"""

    def __init__(self, cookie="", **kw):
        self.sent = []
        self.subtitles_returned = 0

    def video(self, bvid=None, aid=None):
        return {"aid": 115945242695525, "cid": 35571502178, "bvid": bvid,
                "title": "测试视频", "author": "测试UP",
                "description": "测试简介"}

    def subtitle(self, bvid=None, cid=None, lang=None):
        self.subtitles_returned += 1
        return {"available": True, "text": "第一行\n第二行", "lines": [],
                "tracks": []}

    def comments(self, aid, page=1, page_size=20, mode=3):
        return {"total_count": 3, "replies": [
            {"rpid": 111, "author": "召唤者A", "mid": 1,
             "content": "@助手 总结一下这个视频"},
            {"rpid": 222, "author": "路人B", "mid": 2,
             "content": "这个视频不错"},
            {"rpid": 333, "author": "召唤者C", "mid": 3,
             "content": "麻烦 @助手 帮忙总结"},
        ]}

    def post_comment(self, aid, message, root=0, parent=0):
        self.sent.append({"oid": aid, "message": message,
                          "root": root, "parent": parent})
        return {"rpid": 999}


def fake_summarize(video_info, subtitle_text, config):
    return "【一句话】测试总结。\n【要点】要点一；要点二。"


def make_cfg(tmp):
    return {
        "bilibili": {"trigger_name": "助手", "master_name": "某人"},
        "watch_list": {"bvids": ["BV1test1"]},
        "deepseek": {"api_key": "sk-test", "system_prompt": "x",
                     "max_tokens": 500, "temperature": 0.3},
        "reply": {"prefix": "", "suffix": "（由 AI 自动总结生成）",
                  "reply_delay": 0},
        "rate_limit": {"min_request_interval": 0, "max_retries": 1},
        "logging": {"level": "ERROR", "console": False},
        "state": {"file": os.path.join(tmp, "state.json")},
    }


def test_summon_flow():
    tmp = tempfile.mkdtemp()
    cfg = make_cfg(tmp)
    state = monitor.load_state(cfg["state"]["file"])

    api = FakeAPI()
    n = monitor.check_video(api, "BV1test1", "助手", state, cfg, fake_summarize)
    assert n == 2, f"应回复 2 条（rpid 111 和 333），实际 {n}"
    assert len(api.sent) == 2
    first = api.sent[0]
    assert first["message"].startswith("@召唤者A"), first["message"][:30]
    assert "（由 AI 自动总结生成）" in first["message"]
    assert str(first["root"]) == "111" and str(first["parent"]) == "111"
    assert all("路人B" not in s["message"] for s in api.sent), "不该回路人"
    print("PASS 5: @召唤识别 + 回复组装 + 跳过路人")


def test_state_and_cache():
    tmp = tempfile.mkdtemp()
    cfg = make_cfg(tmp)
    state = monitor.load_state(cfg["state"]["file"])
    api = FakeAPI()
    monitor.check_video(api, "BV1test1", "助手", state, cfg, fake_summarize)

    assert state["processed"]["111"] == "replied"
    assert state["processed"]["222"] == "skipped"
    assert state["processed"]["333"] == "replied"
    monitor.save_state(cfg["state"]["file"], state)

    # 第二轮：已处理的评论不重复回，总结不重复生成
    api2 = FakeAPI()
    n2 = monitor.check_video(api2, "BV1test1", "助手", state, cfg, fake_summarize)
    assert n2 == 0, "已处理的评论不应重复回复"
    assert api2.subtitles_returned == 0, "总结已缓存，不应重新拉字幕"
    print("PASS 6: state 记录 + 缓存复用（不重复烧 token）")


def test_build_reply():
    msg = monitor.build_reply("小明", "总结内容",
                              {"prefix": "前言", "suffix": "后缀"})
    assert msg.startswith("@小明 ")
    assert "前言" in msg and "总结内容" in msg and "后缀" in msg
    print("PASS 7: 回复文案组装")


def main():
    test_wbi_golden()
    test_wbi_keys_from_nav()
    test_perm_table()
    test_format()
    test_summon_flow()
    test_state_and_cache()
    test_build_reply()
    print("\n全部 7 项测试通过 ✅")


if __name__ == "__main__":
    main()
