#!/usr/bin/env python3
"""在视频评论区发一条「@某人 + 视频总结」的评论。

用法：
    python post_summary_comment.py <bvid> --message "总结文案"
    python post_summary_comment.py <bvid>              # 不传文案则调 DeepSeek 生成
    python post_summary_comment.py <bvid> --dry-run    # 只看文案不发

流程：读视频信息 → 点赞（可选，养号用）→ 拼 @前缀 → 发主楼评论。

第一次用请先跑：python setup.py
"""
import argparse
import json
import sys

from bilicore.api import BiliError
from bilicore.config import ConfigError, load_api


def deepseek_summarize(video_info, subtitle_text, cfg):
    """调 DeepSeek 生成总结。需要 config 里填了 api_key。"""
    import urllib.request
    body = json.dumps({
        "model": cfg.get("model", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": cfg["system_prompt"]},
            {"role": "user", "content":
                f"【标题】{video_info['title']}\n【UP主】{video_info['author']}\n"
                + (f"【字幕全文】\n{subtitle_text[:20000]}" if subtitle_text
                   else f"【简介】\n{video_info['description'][:3000] or '（无）'}")},
        ],
        "max_tokens": int(cfg.get("max_tokens", 500)),
        "temperature": float(cfg.get("temperature", 0.3)),
    }).encode("utf-8")
    req = urllib.request.Request(
        cfg.get("base_url", "https://api.deepseek.com").rstrip("/")
        + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + cfg["api_key"]})
    with urllib.request.urlopen(req, timeout=60) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    return d["choices"][0]["message"]["content"].strip()


def main():
    ap = argparse.ArgumentParser(description="发「@某人 + 视频总结」评论")
    ap.add_argument("bvid", help="B站视频 BV 号")
    ap.add_argument("--message",
                    help="总结文案。省略则调 DeepSeek 自动生成")
    ap.add_argument("--no-like", action="store_true", help="本次不点赞")
    ap.add_argument("--dry-run", action="store_true",
                    help="只生成评论文案，不真的发布")
    args = ap.parse_args()

    try:
        api, cfg = load_api()
    except ConfigError as e:
        print(f"配置有问题：\n{e}", file=sys.stderr)
        sys.exit(1)

    master = cfg["bilibili"]["master_name"]
    info = api.video(bvid=args.bvid)
    print(f"视频: {info['title']} (UP: {info['author']})")

    # 顺手点赞：养号 + 支持 UP 主。已点过会自动跳过。
    if not args.no_like and not args.dry_run:
        try:
            if api.has_liked(args.bvid):
                print("👍 之前已点过赞")
            else:
                api.like(args.bvid, like=True)
                print("👍 已点赞")
        except BiliError as e:
            print(f"点赞失败（不影响发评论）: {e}", file=sys.stderr)

    if args.message:
        summary = args.message
        print(f"使用传入的总结文案（{len(summary)} 字）")
    else:
        if not str(cfg.get("deepseek", {}).get("api_key", "")).startswith("sk-"):
            print("没有配 DeepSeek 密钥，也没传 --message。\n"
                  "请用 --message 给文案，或重跑 python setup.py 填密钥。",
                  file=sys.stderr)
            sys.exit(1)
        sub = api.subtitle(bvid=args.bvid)
        print(f"字幕: {'有' if sub['available'] else '无，用简介兜底'}")
        summary = deepseek_summarize(info, sub["text"], cfg["deepseek"])
        print(f"\n===== 总结 =====\n{summary}\n================")

    message = f"@{master} {summary}"[:980]

    if args.dry_run:
        print(f"[dry-run] 评论文案:\n{message}")
        return

    result = api.post_comment(info["aid"], message)
    print(f"✅ 评论已发布 (rpid={result['rpid']})")
    print(f"视频链接: https://www.bilibili.com/video/{args.bvid}")
    print("提示：新账号的评论可能先进审核（state=17），过审后 @ 通知才送达。")


if __name__ == "__main__":
    main()
