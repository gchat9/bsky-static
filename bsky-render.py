#!/usr/bin/env python3
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone


API_BASE = "https://public.api.bsky.app/xrpc"


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "bsky-render/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def resolve_handle(handle):
    q = urllib.parse.urlencode({"handle": handle})
    data = fetch_json(f"{API_BASE}/com.atproto.identity.resolveHandle?{q}")
    return data.get("did")


def author_feed(did, limit=50):
    q = urllib.parse.urlencode(
        {
            "actor": did,
            "filter": "posts_and_author_threads",
            "includePins": "false",
            "limit": str(limit),
        }
    )
    return fetch_json(f"{API_BASE}/app.bsky.feed.getAuthorFeed?{q}")


def post_url(handle, uri):
    # at://did/app.bsky.feed.post/rkey
    rkey = uri.rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def render_embed(embed, post_link):
    if not isinstance(embed, dict):
        return ""
    embed_type = embed.get("$type", "")

    if embed_type.startswith("app.bsky.embed.images#"):
        items = embed.get("images") or []
        if not items:
            return ""
        entries = []
        for img in items:
            url = img.get("fullsize") or img.get("thumb")
            if not url:
                continue
            alt = html.escape(img.get("alt") or "")
            href = html.escape(url)
            entries.append(
                f'<a href="{href}" target="_blank" rel="noreferrer"><img src="{href}" alt="{alt}"></a>'
            )
        if not entries:
            return ""
        parts = [f'<div class="media images" data-count="{len(entries)}">']
        parts.extend(entries)
        parts.append("</div>")
        return "\n".join(parts)

    if embed_type.startswith("app.bsky.embed.video#"):
        playlist = embed.get("playlist")
        thumb = embed.get("thumbnail")
        alt = html.escape(embed.get("alt") or "")
        if not playlist and thumb:
            return f'<div class="media video"><img src="{html.escape(thumb)}" alt="{alt}"></div>'
        if playlist:
            poster = f'<img src="{html.escape(thumb)}" alt="{alt}">' if thumb else ""
            href = post_link or playlist
            return (
                '<div class="media video">'
                f'<a class="video-link" href="{html.escape(href)}" target="_blank" rel="noreferrer">'
                f"{poster}</a></div>"
            )
        return ""

    if embed_type.startswith("app.bsky.embed.external#"):
        ext = embed.get("external") or {}
        uri = ext.get("uri")
        thumb = ext.get("thumb")
        title = html.escape(ext.get("title") or "")
        desc = html.escape(ext.get("description") or "")
        if uri:
            thumb_html = (
                f'<img src="{html.escape(thumb)}" alt="">' if thumb else ""
            )
            return (
                '<div class="media external">'
                f'<a href="{html.escape(uri)}" target="_blank" rel="noreferrer">'
                f"{thumb_html}<div class=\"external-text\"><div class=\"external-title\">{title}</div>"
                f'<div class="external-desc">{desc}</div></div></a></div>'
            )
        return ""

    return ""


def render_html(handle, feed, ignore_patterns=None, did=None):
    items = feed.get("feed") or []
    rows = []
    hidden_rows = []
    ignore_patterns = ignore_patterns or []
    hidden_count = 0
    last_rendered_ts = None
    newest_ts = None
    last_meta = load_last_rendered_meta(handle)
    if last_meta:
        last_rendered_ts = parse_time(last_meta.get("last_rendered_post"))
    for item in items:
        post = (item or {}).get("post") or {}
        record = post.get("record") or {}
        text_raw = record.get("text") or ""
        if ignore_patterns and any(p.search(text_raw) for p in ignore_patterns):
            continue
        text = html.escape(text_raw)
        created = html.escape(record.get("createdAt") or "")
        created_ts = parse_time(record.get("createdAt"))
        if created_ts is not None:
            if newest_ts is None or created_ts > newest_ts:
                newest_ts = created_ts
        uri = post.get("uri") or ""
        link = post_url(handle, uri) if uri else ""
        embed = render_embed(post.get("embed"), link)
        is_hidden = last_rendered_ts is not None and created_ts is not None and created_ts < last_rendered_ts
        target = hidden_rows if is_hidden else rows
        if is_hidden:
            hidden_count += 1
        target.append(
            "\n".join(
                [
                    '<article class="post{}">'.format(" older" if is_hidden else ""),
                    f'<div class="meta"><a href="{html.escape(link)}" target="_blank" rel="noreferrer">{html.escape(handle)}</a>',
                    f"<span class=\"date\">{created}</span></div>",
                    f'<div class="text">{text}</div>',
                    embed,
                    "</article>",
                ]
            )
        )

    toggle_html = ""
    template_html = ""
    if hidden_count:
        toggle_html = (
            '<div class="read-more-wrap">'
            f'<a id="read-more" href="#">read more... ({hidden_count} hidden)</a>'
            "</div>"
        )
        template_html = f'<template id="cut">{"".join(hidden_rows)}</template>'
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bluesky feed: {html.escape(handle)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f3f2f0;
      --card: #ffffff;
      --ink: #161616;
      --muted: #5c5c5c;
      --accent: #1e5bff;
      --border: #e4e1dd;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Alegreya Sans", "IBM Plex Sans", system-ui, -apple-system, sans-serif;
    }}
    header {{
      padding: 24px 20px 8px;
      max-width: 900px;
      margin: 0 auto;
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: 28px;
      font-weight: 700;
    }}
    .sub {{
      color: var(--muted);
      font-size: 14px;
    }}
    main {{
      max-width: 900px;
      margin: 0 auto;
      padding: 8px 20px 32px;
    }}
    .post {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      margin: 12px 0;
      box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }}
    .meta {{
      display: flex;
      gap: 10px;
      align-items: baseline;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 8px;
    }}
    .meta a {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }}
    .text {{
      font-size: 30px;
      line-height: 1.25;
      white-space: pre-wrap;
      margin-bottom: 10px;
    }}
    .media {{
      margin-top: 8px;
    }}
    .images {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }}
    .images[data-count="1"] {{
      grid-template-columns: 1fr;
    }}
    .images[data-count="2"] {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .images a {{
      display: block;
      color: inherit;
      text-decoration: none;
    }}
    @media (max-width: 900px) {{
      .images {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 640px) {{
      .images {{
        grid-template-columns: 1fr;
      }}
    }}
    .images img {{
      width: 100%;
      height: auto;
      border-radius: 10px;
      border: 1px solid var(--border);
      max-height: min(120vh, 1000px);
      object-fit: contain;
    }}
    .video {{
      text-align: center;
    }}
    .video a {{
      position: relative;
      display: inline-block;
      color: inherit;
      text-decoration: none;
    }}
    .video a::before {{
      content: "📹";
      position: absolute;
      top: 8px;
      left: 8px;
      font-size: 18px;
      line-height: 1;
      padding: 2px 5px 3px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.8);
      border: 1px solid var(--border);
    }}
    .video img {{
      display: block;
      margin: 0 auto;
      max-width: 100%;
      width: 100%;
      height: auto;
      border-radius: 10px;
      border: 1px solid var(--border);
      max-height: min(120vh, 1000px);
      object-fit: contain;
    }}
    .external a {{
      display: grid;
      grid-template-columns: 120px 1fr;
      gap: 12px;
      align-items: center;
      text-decoration: none;
      color: inherit;
    }}
    .external img {{
      width: 120px;
      height: 80px;
      object-fit: cover;
      border-radius: 8px;
      border: 1px solid var(--border);
    }}
    .external-title {{
      font-weight: 600;
      margin-bottom: 4px;
    }}
    .external-desc {{
      color: var(--muted);
      font-size: 13px;
    }}
    .read-more-wrap {{
      text-align: center;
      margin: 18px 0 8px;
    }}
    #read-more {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <main>
    {"".join(rows)}
    {toggle_html}
  </main>
  {template_html}
  <script>
    const link = document.getElementById("read-more");
    if (link) {{
      link.addEventListener("click", (e) => {{
        e.preventDefault();
        const template = document.getElementById("cut");
        if (template) {{
          document.body.append(template.content.cloneNode(true));
          template.remove();
        }}
        link.closest(".read-more-wrap")?.remove();
      }});
    }}
  </script>
</body>
</html>
"""
    save_last_rendered_meta(handle, newest_ts, did=did)
    return html_doc


def cache_paths(handle):
    cache_dir = "/var/cache/bsky"
    cache_path = os.path.join(cache_dir, f"{handle}.json")
    return cache_dir, cache_path


def load_cached_feed(cache_path, max_age_seconds=900):
    try:
        mtime = os.path.getmtime(cache_path)
    except OSError:
        return None
    if (time.time() - mtime) > max_age_seconds:
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def save_cached_feed(cache_dir, cache_path, feed):
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(feed, f)
    except OSError:
        pass


def load_ignore_patterns(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()]
    except OSError:
        return []
    patterns = []
    for line in lines:
        if not line or line.startswith("#"):
            continue
        try:
            patterns.append(re.compile(line))
        except re.error:
            continue
    return patterns


def parse_time(value):
    if not value:
        return None
    try:
        if value.endswith("Z"):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def last_rendered_paths(handle):
    data_dir = "/var/lib/bsky"
    data_path = os.path.join(data_dir, f"{handle}.json")
    return data_dir, data_path


def load_last_rendered_meta(handle):
    _, data_path = last_rendered_paths(handle)
    try:
        with open(data_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def save_last_rendered_meta(handle, newest_ts, did=None):
    if newest_ts is None:
        return
    data_dir, data_path = last_rendered_paths(handle)
    payload = {
        "did": did,
        "last_rendered_post": datetime.fromtimestamp(newest_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    try:
        os.makedirs(data_dir, exist_ok=True)
        if os.path.exists(data_path) and not did:
            try:
                with open(data_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if isinstance(existing, dict) and existing.get("did"):
                    payload["did"] = existing.get("did")
            except (OSError, json.JSONDecodeError):
                pass
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except OSError:
        pass


def main():
    if len(sys.argv) < 2:
        print("Usage: bsky-render.py <handle> > feed.html", file=sys.stderr)
        sys.exit(2)

    handle = sys.argv[1].strip()
    if not handle:
        print("Handle is required.", file=sys.stderr)
        sys.exit(2)

    cache_dir, cache_path = cache_paths(handle)
    ignore_regexes = load_ignore_patterns("/etc/bsky/ignore")
    last_meta = load_last_rendered_meta(handle)
    did = last_meta.get("did") if isinstance(last_meta, dict) else None
    feed = load_cached_feed(cache_path)
    if feed is None:
        if not did:
            did = resolve_handle(handle)
        if not did:
            print(f"Could not resolve handle: {handle}", file=sys.stderr)
            sys.exit(1)
        feed = author_feed(did, limit=50)
        save_cached_feed(cache_dir, cache_path, feed)
    html_doc = render_html(handle, feed, ignore_regexes, did=did)
    sys.stdout.write(html_doc)


if __name__ == "__main__":
    main()
