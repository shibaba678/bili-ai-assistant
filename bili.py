"""bili.py —— 统一的 B 站命令行工具。

一条命令调一个功能：刷流、搜索、详情、字幕、评论、历史、点赞、投币、
收藏、发评论、删评论。所有输出是 JSON，方便脚本或 AI 助手直接消费。

第一次用请先跑：python setup.py

用法：
    python bili.py status
    python bili.py feed --source recommend --size 12
    python bili.py feed --source popular
    python bili.py feed --source ranking --rid 0
    python bili.py search "关键词" --order click
    python bili.py video BV1xx411c7mD
    python bili.py subtitle BV1xx411c7mD
    python bili.py comments BV1xx411c7mD --page 1
    python bili.py replies BV1xx411c7mD --rpid 123
    python bili.py checkcomment BV1xx411c7mD --rpid 123
    python bili.py history
    python bili.py like BV1xx411c7mD [--unlike]
    python bili.py coin BV1xx411c7mD --count 1
    python bili.py fav BV1xx411c7mD --folder 123
    python bili.py favfolders
    python bili.py comment BV1xx411c7mD --message "..." [--root R --parent P]
    python bili.py delcomment BV1xx411c7mD --rpid 123
"""
import argparse
import json
import sys

from bilicore.config import ConfigError, load_config, make_api


def get_api():
    """读配置 + 造 API；配置有问题就给一句人话，别甩 traceback。"""
    try:
        cfg = load_config()
    except ConfigError as e:
        print(f"配置有问题：\n{e}", file=sys.stderr)
        sys.exit(1)
    return make_api(cfg)


def brief_videos(items):
    """视频列表压成一行一条，省 token。"""
    return [
        {"bvid": v.get("bvid"), "title": (v.get("title") or "")[:70],
         "author": v.get("author"), "duration": v.get("duration"),
         "views": v.get("views"), "published": v.get("published_at")}
        for v in items
    ]


def main():
    ap = argparse.ArgumentParser(description="B 站统一工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="账号与凭据状态")
    sub.add_parser("favfolders", help="收藏夹列表")

    p = sub.add_parser("feed", help="刷推荐流/热门/排行榜")
    p.add_argument("--source", default="recommend",
                   choices=["recommend", "popular", "ranking"])
    p.add_argument("--size", type=int, default=12)
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--rid", type=int, default=0, help="排行榜分区，0=全站")
    p.add_argument("--fresh", type=int, default=1, help="推荐流翻页序号")

    p = sub.add_parser("search", help="搜索视频")
    p.add_argument("keyword")
    p.add_argument("--order", default="totalrank",
                   choices=["totalrank", "click", "pubdate", "dm", "stow"])
    p.add_argument("--page", type=int, default=1)

    p = sub.add_parser("video", help="视频详情")
    p.add_argument("bvid")

    p = sub.add_parser("subtitle", help="字幕全文")
    p.add_argument("bvid")
    p.add_argument("--lang", default=None)
    p.add_argument("--max-chars", type=int, default=12000)

    p = sub.add_parser("comments", help="评论主楼")
    p.add_argument("bvid")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--size", type=int, default=20)
    p.add_argument("--sort", default="hot", choices=["hot", "time"])

    p = sub.add_parser("replies", help="楼中楼")
    p.add_argument("bvid")
    p.add_argument("--rpid", type=int, required=True)
    p.add_argument("--page", type=int, default=1)

    p = sub.add_parser("checkcomment", help="按 rpid 查评论状态与 @ 解析")
    p.add_argument("bvid")
    p.add_argument("--rpid", type=int, required=True)

    sub.add_parser("history", help="观看历史")

    p = sub.add_parser("like", help="点赞/取消点赞")
    p.add_argument("bvid")
    p.add_argument("--unlike", action="store_true")

    p = sub.add_parser("coin", help="投币")
    p.add_argument("bvid")
    p.add_argument("--count", type=int, default=1, choices=[1, 2])
    p.add_argument("--also-like", action="store_true")

    p = sub.add_parser("fav", help="收藏/取消收藏")
    p.add_argument("bvid")
    p.add_argument("--folder", type=int, action="append", default=[])
    p.add_argument("--unfav", action="store_true")

    p = sub.add_parser("comment", help="发评论（主楼或楼中楼）")
    p.add_argument("bvid")
    p.add_argument("--message", required=True)
    p.add_argument("--root", type=int, default=0)
    p.add_argument("--parent", type=int, default=0)

    p = sub.add_parser("delcomment", help="删自己的评论")
    p.add_argument("bvid")
    p.add_argument("--rpid", type=int, required=True)

    args = ap.parse_args()
    api = get_api()

    def need_aid(bvid):
        return api.video(bvid=bvid)["aid"]

    if args.cmd == "status":
        out = api.status()
    elif args.cmd == "favfolders":
        out = api.fav_folders()
    elif args.cmd == "feed":
        if args.source == "recommend":
            out = brief_videos(api.recommend(page_size=args.size,
                                             fresh_idx=args.fresh))
        elif args.source == "popular":
            out = brief_videos(api.popular(page_size=args.size, page=args.page))
        else:
            out = brief_videos(api.ranking(rid=args.rid, page_size=args.size))
    elif args.cmd == "search":
        out = brief_videos(api.search(args.keyword, page=args.page,
                                      order=args.order))
    elif args.cmd == "video":
        out = api.video(bvid=args.bvid)
    elif args.cmd == "subtitle":
        sub = api.subtitle(bvid=args.bvid, lang=args.lang)
        out = {
            "available": sub["available"],
            "language": sub.get("language"),
            "tracks": sub["tracks"],
            "chars": len(sub["text"]),
            "text": sub["text"][:args.max_chars],
        }
    elif args.cmd == "comments":
        aid = need_aid(args.bvid)
        out = api.comments(aid, page=args.page, page_size=args.size,
                           mode=3 if args.sort == "hot" else 2)
    elif args.cmd == "replies":
        aid = need_aid(args.bvid)
        out = api.comment_replies(aid, args.rpid, page=args.page)
    elif args.cmd == "checkcomment":
        aid = need_aid(args.bvid)
        out = api.comment_by_rpid(aid, args.rpid)
    elif args.cmd == "history":
        out = api.history()
    elif args.cmd == "like":
        out = api.like(args.bvid, like=not args.unlike)
    elif args.cmd == "coin":
        out = api.coin(args.bvid, count=args.count, also_like=args.also_like)
    elif args.cmd == "fav":
        if args.unfav:
            out = api.fav(args.bvid, del_ids=args.folder)
        else:
            folders = args.folder or [f["id"] for f in api.fav_folders()][:1]
            out = api.fav(args.bvid, add_ids=folders)
    elif args.cmd == "comment":
        aid = need_aid(args.bvid)
        out = api.post_comment(aid, args.message,
                               root=args.root, parent=args.parent)
        out["bvid"] = args.bvid
        out["url"] = f"https://www.bilibili.com/video/{args.bvid}"
    elif args.cmd == "delcomment":
        aid = need_aid(args.bvid)
        out = api.del_comment(aid, args.rpid)
    else:
        ap.error("未知命令")

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
