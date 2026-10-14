"""监听核心：轮询视频池 → 找 @召唤 评论 → 总结 → 楼中楼回复。

复用 bilicore 的请求层（串行限速、WBI 签名、错误不回显 cookie）。
"""
import json
import logging
import os
import re
import time

from bilicore.api import BiliAPI, BiliError

log = logging.getLogger("monitor")


def load_state(path):
    """已处理的评论 rpid 记录 + 各视频的总结缓存。"""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            log.warning("state 文件损坏，重建")
    return {"processed": {}, "summaries": {}}


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, path)


def build_reply(comment_user, summary_text, reply_cfg):
    """组装回复文案：@召唤者 + 总结 + 后缀。"""
    prefix = reply_cfg.get("prefix", "")
    suffix = reply_cfg.get("suffix", "")
    parts = [f"@{comment_user} "]
    if prefix:
        parts.append(prefix + "\n")
    parts.append(summary_text)
    if suffix:
        parts.append("\n" + suffix)
    return "".join(parts)


def check_video(api, bvid, trigger_name, state, cfg, summarize_fn):
    """检查一个视频下所有新评论，处理 @召唤。返回本次处理的评论数。"""
    info = api.video(bvid=bvid)
    cached = state["summaries"].get(bvid)

    comments = api.comments(info["aid"], page=1, page_size=20, mode=3)
    processed = state["processed"]
    reply_cfg = cfg.get("reply", {})
    handled = 0

    for c in comments["replies"]:
        rpid = str(c["rpid"])
        if rpid in processed:
            continue

        text = c["content"]
        # B站评论里 @ 展示成 " @名字 " 带空格的形式
        if not re.search(r"@" + re.escape(trigger_name), text):
            processed[rpid] = "skipped"   # 不含召唤词，标记跳过
            continue

        user = c["author"]
        log.info(" [%s] %s 召唤: %s", bvid, user, text[:60])

        summary_text = cached
        if not summary_text:
            sub = api.subtitle(bvid=bvid)
            summary_text = summarize_fn(info, sub["text"], cfg["deepseek"])
            if not summary_text:
                log.error("总结失败，本轮跳过，下轮重试")
                continue
            state["summaries"][bvid] = summary_text

        message = build_reply(user, summary_text, reply_cfg)[:950]

        try:
            api.post_comment(info["aid"], message, root=c["rpid"],
                             parent=c["rpid"])
            processed[rpid] = "replied"
            handled += 1
            log.info("回复成功 → %s", user)
        except BiliError as e:
            log.error("回复失败: %s", e)
            # 内容/频率类错误标记掉，避免死循环；其余留着重试
            if e.code in (12002, 12009, -111):
                processed[rpid] = f"failed:{e.code}"

        time.sleep(float(reply_cfg.get("reply_delay", 5)))

    return handled


def run(cfg):
    """主循环。"""
    logging.basicConfig(
        level=getattr(logging, cfg["logging"].get("level", "INFO")),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=_make_handlers(cfg))

    from bilicore.config import ConfigError, load_config, make_api
    from post_summary_comment import deepseek_summarize

    api = make_api(cfg)

    state_path = cfg.get("state", {}).get("file", "state.json")
    state = load_state(state_path)
    trigger_name = cfg["bilibili"]["trigger_name"]
    bvids = cfg["watch_list"]["bvids"]
    interval = int(cfg["bilibili"].get("check_interval", 300))

    log.info("启动。监听 %d 个视频，召唤词: @%s", len(bvids), trigger_name)

    while True:
        for bvid in bvids:
            try:
                n = check_video(api, bvid, trigger_name, state, cfg,
                                deepseek_summarize)
                save_state(state_path, state)
                if n:
                    log.info("[%s] 本轮回复了 %d 条", bvid, n)
            except Exception:
                log.exception("处理 %s 出错", bvid)
        log.info("休眠 %d 秒", interval)
        time.sleep(interval)


def _make_handlers(cfg):
    handlers = []
    log_cfg = cfg.get("logging", {})
    if log_cfg.get("console", True):
        handlers.append(logging.StreamHandler())
    if log_cfg.get("file"):
        os.makedirs(os.path.dirname(log_cfg["file"]) or ".", exist_ok=True)
        handlers.append(logging.FileHandler(log_cfg["file"], encoding="utf-8"))
    return handlers


if __name__ == "__main__":
    import sys
    from bilicore.config import ConfigError, load_config

    cfg_path = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        run_cfg = load_config(cfg_path)
    except ConfigError as e:
        print(f"配置有问题：\n{e}", file=sys.stderr)
        sys.exit(1)
    run(run_cfg)
