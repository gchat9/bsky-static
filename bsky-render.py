#!/usr/bin/env python3
import html
import json
import sys
import urllib.parse
import urllib.request


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


def render_embed(embed):
    if not isinstance(embed, dict):
        return ""
    embed_type = embed.get("$type", "")

    if embed_type.startswith("app.bsky.embed.images#"):
        items = embed.get("images") or []
        if not items:
            return ""
        parts = ['<div class="media images">']
        for img in items:
            url = img.get("fullsize") or img.get("thumb")
            if not url:
                continue
            alt = html.escape(img.get("alt") or "")
            parts.append(f'<img src="{html.escape(url)}" alt="{alt}">')
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
            return (
                '<div class="media video">'
                f'<a href="{html.escape(playlist)}" target="_blank" rel="noreferrer">'
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


def render_html(handle, feed):
    items = feed.get("feed") or []
    rows = []
    for item in items:
        post = (item or {}).get("post") or {}
        record = post.get("record") or {}
        text = html.escape(record.get("text") or "")
        created = html.escape(record.get("createdAt") or "")
        uri = post.get("uri") or ""
        link = post_url(handle, uri) if uri else ""
        embed = render_embed(post.get("embed"))
        rows.append(
            "\n".join(
                [
                    '<article class="post">',
                    f'<div class="meta"><a href="{html.escape(link)}" target="_blank" rel="noreferrer">{html.escape(handle)}</a>',
                    f"<span class=\"date\">{created}</span></div>",
                    f'<div class="text">{text}</div>',
                    embed,
                    "</article>",
                ]
            )
        )

    return f"""<!doctype html>
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
      font-size: 16px;
      line-height: 1.5;
      white-space: pre-wrap;
      margin-bottom: 10px;
    }}
    .media {{
      margin-top: 8px;
    }}
    .images {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 8px;
    }}
    .images img {{
      width: 100%;
      height: auto;
      border-radius: 10px;
      border: 1px solid var(--border);
      max-height: min(120vh, 1000px);
      object-fit: contain;
    }}
    .video img {{
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
  </style>
</head>
<body>
  <header>
    <h1>Bluesky feed</h1>
    <div class="sub">{html.escape(handle)} - top 50 posts</div>
  </header>
  <main>
    {"".join(rows)}
  </main>
</body>
</html>
"""


def main():
    if len(sys.argv) < 2:
        print("Usage: bsky-render.py <handle> > feed.html", file=sys.stderr)
        sys.exit(2)

    handle = sys.argv[1].strip()
    if not handle:
        print("Handle is required.", file=sys.stderr)
        sys.exit(2)

    did = resolve_handle(handle)
    if not did:
        print(f"Could not resolve handle: {handle}", file=sys.stderr)
        sys.exit(1)

    feed = author_feed(did, limit=50)
    html_doc = render_html(handle, feed)
    sys.stdout.write(html_doc)


if __name__ == "__main__":
    main()
