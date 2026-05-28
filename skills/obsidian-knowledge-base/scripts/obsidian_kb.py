#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

STOP_QUERY_PARAMS = {"fbclid", "gclid", "yclid", "igshid", "mc_cid", "mc_eid", "spm", "ref"}
DEFAULT_BOOKMARK_FOLDER = "AI Inbox"
SKILL_NAME = "obsidian-knowledge-base"
DOCUMENT_EXTS = {"pdf", "xlsx", "xls", "docx", "pptx", "csv"}
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024


def today() -> str:
    return dt.datetime.now().date().isoformat()


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def ascii_slug(value: str, fallback: str = "note") -> str:
    value = html.unescape(value or "")
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:90].strip("-") or fallback


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "vault-template").exists() and (parent / "skills").exists():
            return parent
    return here.parents[3] if len(here.parents) > 3 else Path.cwd()


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8") or json.dumps(default))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def vault_config(root: Path) -> dict[str, str]:
    data = read_json(root / ".obsidian-kb.json", {})
    return {str(k): str(v) for k, v in data.items() if v is not None}


def ensure_vault(root: Path) -> None:
    missing = [name for name in ["sources", "notes", "daily", "inbox", "logs", "templates", "system"] if not (root / name).exists()]
    if missing:
        raise SystemExit(f"Vault root looks incomplete: {root}. Missing: {', '.join(missing)}")


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        parsed = urlparse("https://" + url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    query_pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_l = key.lower()
        if key_l.startswith("utm_") or key_l in STOP_QUERY_PARAMS:
            continue
        query_pairs.append((key, value))
    query = urlencode(sorted(query_pairs))
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", query, ""))


def file_ext_from_url(url: str) -> str:
    path = urlparse(normalize_url(url)).path.lower()
    match = re.search(r"\.([a-z0-9]{2,6})$", path)
    return match.group(1) if match else ""


def source_type_for(url: str) -> str:
    ext = file_ext_from_url(url)
    if ext in DOCUMENT_EXTS:
        return "document"
    host = urlparse(normalize_url(url)).netloc
    if host in {"youtu.be", "youtube.com", "m.youtube.com"} or host.endswith(".youtube.com"):
        return "youtube"
    if host in {"x.com", "twitter.com"} or host.endswith(".x.com") or host.endswith(".twitter.com"):
        return "x"
    if host == "zenn.dev" or host.endswith(".zenn.dev"):
        return "zenn"
    if host == "qiita.com" or host.endswith(".qiita.com"):
        return "qiita"
    return "web"


def yaml_escape(value: str) -> str:
    if value == "":
        return ""
    if re.match(r"^[A-Za-z0-9_./: @#+-]+$", value) and not value.startswith(("-", "{", "[", "#")):
        return value
    return json.dumps(value, ensure_ascii=False)


def frontmatter(fields: dict) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            if value:
                lines.append(f"{key}:")
                lines.extend(f"  - {yaml_escape(str(item))}" for item in value)
            else:
                lines.append(f"{key}: []")
        else:
            lines.append(f"{key}: {yaml_escape(str(value)) if value is not None else ''}")
    lines.append("---")
    return "\n".join(lines)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    raw = text[4:end].strip().splitlines()
    data: dict = {}
    key = None
    for line in raw:
        if line.startswith("  - ") and key:
            data.setdefault(key, []).append(line[4:].strip().strip('"'))
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        v = v.strip()
        if v == "":
            data[key] = []
        elif v == "[]":
            data[key] = []
            key = None
        else:
            data[key] = v.strip('"')
            key = None
    return data, text[end + 4:].lstrip("\n")


class ReadableHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.in_title = False
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = {k.lower(): v or "" for k, v in attrs}
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas"}:
            self.skip_depth += 1
            return
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            content = attrs_dict.get("content", "").strip()
            if name and content:
                self.meta[name] = html.unescape(content)
        if tag in {"p", "li", "h1", "h2", "h3", "blockquote", "pre"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skip_depth and tag in {"script", "style", "noscript", "svg", "canvas"}:
            self.skip_depth -= 1
            return
        if tag == "title":
            self.in_title = False
        if tag in {"p", "li", "h1", "h2", "h3", "blockquote", "pre"}:
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth:
            return
        value = html.unescape(data).strip()
        if not value:
            return
        if self.in_title:
            self.title_parts.append(value)
        else:
            self.text_parts.append(value + " ")

    @property
    def title(self) -> str:
        return clean_space(" ".join(self.title_parts))

    @property
    def text(self) -> str:
        lines = [clean_space(line) for line in "".join(self.text_parts).splitlines()]
        return "\n\n".join(dedupe([line for line in lines if len(line) >= 35]))


def fetch_bytes(url: str, timeout: int = 30, max_bytes: int = MAX_DOCUMENT_BYTES) -> tuple[bytes, str]:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 obsidian-bookmark-wiki-kit/1.0"})
    with urlopen(req, timeout=timeout) as res:
        content_type = res.headers.get("content-type", "")
        length = res.headers.get("content-length")
        if length and int(length) > max_bytes:
            raise ValueError(f"Document is too large: {length} bytes > {max_bytes} bytes")
        raw = res.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError(f"Document is too large: > {max_bytes} bytes")
    return raw, content_type


def fetch_url(url: str, timeout: int = 20) -> str:
    raw, content_type = fetch_bytes(url, timeout=timeout)
    charset_match = re.search(r"charset=([^;]+)", content_type, re.I)
    charset = charset_match.group(1) if charset_match else "utf-8"
    return raw.decode(charset, errors="replace")


def summarize_text(text: str, max_points: int = 7) -> tuple[str, list[str], list[str]]:
    paragraphs = [clean_space(p) for p in re.split(r"\n{2,}", text) if clean_space(p)]
    paragraphs = [p for p in paragraphs if len(p) >= 45]
    summary = "\n\n".join(paragraphs[:3])
    key_points = [p for p in paragraphs if 50 <= len(p) <= 260][:max_points]
    quotes = [p for p in paragraphs if 60 <= len(p) <= 180][:3]
    return summary, key_points, quotes


def ingest_web(url: str) -> dict:
    raw = fetch_url(url)
    parser = ReadableHTMLParser()
    parser.feed(raw)
    title = parser.meta.get("og:title") or parser.meta.get("twitter:title") or parser.title or url
    description = parser.meta.get("description") or parser.meta.get("og:description") or ""
    text = "\n\n".join([description, parser.text])
    summary, key_points, quotes = summarize_text(text)
    return {
        "title": clean_space(title),
        "summary": summary or description,
        "key_points": key_points,
        "quotes": quotes,
        "raw_text": parser.text,
        "author": parser.meta.get("author", ""),
        "published": (parser.meta.get("article:published_time") or parser.meta.get("date") or "")[:10],
        "content_status": "summarized" if (summary or key_points) else "fetched",
        "content_provider": "stdlib-html",
    }



def skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def markitdown_convert(path: Path) -> str:
    try:
        from markitdown import MarkItDown
        md = MarkItDown(enable_plugins=False)
        result = md.convert(str(path))
        return getattr(result, "text_content", None) or getattr(result, "markdown", "") or ""
    except Exception as import_exc:
        venv_python = skill_dir() / ".venv" / "bin" / "python"
        if not venv_python.exists():
            raise RuntimeError("markitdown is not installed. Run: obsidian_kb.py install-deps") from import_exc
        code = """
from markitdown import MarkItDown
import sys
md = MarkItDown(enable_plugins=False)
r = md.convert(sys.argv[1])
sys.stdout.write(getattr(r, 'text_content', None) or getattr(r, 'markdown', '') or '')
"""
        proc = subprocess.run([str(venv_python), "-c", code, str(path)], text=True, capture_output=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "markitdown conversion failed")
        return proc.stdout


def title_from_document_url(url: str) -> str:
    path = urlparse(normalize_url(url)).path
    name = Path(path).stem
    return clean_space(name.replace("-", " ").replace("_", " ")) or url


def ingest_document(root: Path, url: str) -> dict:
    raw, content_type = fetch_bytes(url, timeout=45)
    ext = file_ext_from_url(url)
    if not ext:
        if "pdf" in content_type:
            ext = "pdf"
        elif "spreadsheet" in content_type or "excel" in content_type:
            ext = "xlsx"
        elif "word" in content_type:
            ext = "docx"
        elif "presentation" in content_type or "powerpoint" in content_type:
            ext = "pptx"
        else:
            ext = "bin"
    title = title_from_document_url(url)
    digest = hashlib.sha256(raw).hexdigest()[:16]
    with tempfile.TemporaryDirectory(prefix="obsidian-doc-") as tmp:
        local = Path(tmp) / f"download.{ext}"
        local.write_bytes(raw)
        try:
            converted = markitdown_convert(local)
        except Exception as exc:
            return {"title": title, "summary": f"MarkItDown conversion failed: {exc}", "key_points": [], "quotes": [], "raw_text": "", "author": "", "published": "", "content_status": "conversion_failed", "content_provider": "markitdown", "file_type": ext}
    converted = converted.strip()
    extracted_rel = Path("assets") / "extracted" / f"{ascii_slug(title, 'document')}-{digest}.md"
    extracted_path = root / extracted_rel
    extracted_path.parent.mkdir(parents=True, exist_ok=True)
    extracted_path.write_text(converted + "\n", encoding="utf-8")
    summary, key_points, quotes = summarize_text(converted)
    return {"title": title, "summary": summary or converted[:1200], "key_points": key_points, "quotes": quotes, "raw_text": converted, "author": "", "published": "", "content_status": "converted_summarized" if converted else "converted_empty", "content_provider": "markitdown", "file_type": ext, "converted_path": str(extracted_rel)}


def ingest_youtube(url: str) -> dict:
    if not shutil.which("yt-dlp"):
        return {"title": url, "summary": "yt-dlp がないため transcript を取得できませんでした。", "key_points": [], "quotes": [], "raw_text": "", "author": "", "published": "", "content_status": "asr_required", "content_provider": "none"}
    proc = subprocess.run(["yt-dlp", "-J", "--skip-download", url], text=True, capture_output=True, timeout=60)
    if proc.returncode != 0:
        return {"title": url, "summary": clean_space(proc.stderr)[:500], "key_points": [], "quotes": [], "raw_text": "", "author": "", "published": "", "content_status": "fetch_failed", "content_provider": "yt-dlp"}
    meta = json.loads(proc.stdout)
    title = clean_space(meta.get("title") or url)
    transcript = ""
    provider = "yt-dlp"
    for bucket_name in ["subtitles", "automatic_captions"]:
        bucket = meta.get(bucket_name) or {}
        for lang in ["ja", "ja-JP", "en", "en-US", *sorted(bucket.keys())]:
            entries = bucket.get(lang) or []
            item = next((x for x in entries if x.get("ext") == "vtt" and x.get("url")), None) or next((x for x in entries if x.get("url")), None)
            if not item:
                continue
            try:
                vtt = fetch_url(item["url"])
                lines = []
                for line in vtt.splitlines():
                    line = line.strip()
                    if not line or line == "WEBVTT" or "-->" in line or line.startswith(("Kind:", "Language:")):
                        continue
                    line = clean_space(re.sub(r"<[^>]+>", "", html.unescape(line)))
                    if line:
                        lines.append(line)
                transcript = "\n".join(dedupe(lines))
                provider = f"yt-dlp:{bucket_name}"
                break
            except Exception:
                continue
        if transcript:
            break
    upload_date = meta.get("upload_date") or ""
    published = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}" if len(upload_date) == 8 else ""
    if transcript:
        summary, key_points, quotes = summarize_text(transcript)
        status = "transcript_summarized"
    else:
        summary, key_points, quotes, status = "Transcript を取得できませんでした。必要なら手動承認後に ASR を行ってください。", [], [], "asr_required"
    return {"title": title, "summary": summary, "key_points": key_points, "quotes": quotes, "raw_text": transcript, "author": clean_space(meta.get("uploader") or meta.get("channel") or ""), "published": published, "content_status": status, "content_provider": provider}


def hermes_helper() -> Path | None:
    candidates = [
        codex_home() / "skills/hermes-x-research/scripts/hermes_x_research.py",
        Path.home() / ".codex/skills/hermes-x-research/scripts/hermes_x_research.py",
    ]
    return next((p for p in candidates if p.exists()), None)


def ingest_x(url: str) -> dict:
    helper = hermes_helper()
    if not helper:
        return {"title": f"X Metadata: {url}", "summary": "Hermes helper が見つからないため metadata_only として保存しました。", "key_points": [], "quotes": [], "raw_text": "", "author": "", "published": "", "content_status": "metadata_only", "content_provider": "none"}
    prompt = "次のX/Twitter URLをSource Note化するために調査し、投稿本文、著者、日付、主要論点、実用的示唆、URLを日本語で簡潔にまとめてください: " + url
    proc = subprocess.run(["python3", str(helper), prompt], text=True, capture_output=True, timeout=180)
    output = proc.stdout.strip() or proc.stderr.strip()
    summary, key_points, quotes = summarize_text(output)
    return {"title": f"X Research: {urlparse(url).path.strip('/') or url}", "summary": summary or output[:1200], "key_points": key_points, "quotes": quotes, "raw_text": output, "author": "", "published": "", "content_status": "summarized" if proc.returncode == 0 and output else "fetch_failed", "content_provider": "hermes-x-research"}


def extract_tags(title: str, text: str, source_type: str) -> list[str]:
    blob = f"{title} {text[:3000]}".lower()
    tags = [] if source_type == "web" else [source_type]
    mapping = {"react": ["react", "jsx", "hooks"], "frontend": ["frontend", "css", "browser"], "ai": ["openai", "llm", "ai agent", "codex", "生成ai"], "typescript": ["typescript"], "javascript": ["javascript", "node.js"], "performance": ["performance", "cache", "最適化"], "obsidian": ["obsidian"]}
    for tag, needles in mapping.items():
        if any(n in blob for n in needles):
            tags.append(tag)
    return dedupe(tags)[:8]


def source_note_path(root: Path, url: str, title: str) -> Path:
    stype = source_type_for(url)
    source_dir = "documents" if stype == "document" else stype
    domain = ascii_slug(urlparse(normalize_url(url)).netloc or "unknown", "unknown")
    slug = ascii_slug(title, "source")
    path = root / "sources" / source_dir / domain / f"{slug}.md"
    if not path.exists():
        return path
    short = hashlib.sha256(normalize_url(url).encode()).hexdigest()[:8]
    return root / "sources" / source_dir / domain / f"{slug}-{short}.md"


def write_source(root: Path, url: str, force: bool = False) -> Path:
    ensure_vault(root)
    normalized = normalize_url(url)
    ingested = read_json(root / "logs/ingested.json", {})
    if normalized in ingested and not force:
        existing = root / ingested[normalized].get("note_path", "")
        if existing.exists():
            print(f"Already ingested: {existing.relative_to(root)}")
            return existing
    stype = source_type_for(url)
    info = ingest_document(root, url) if stype == "document" else ingest_youtube(url) if stype == "youtube" else ingest_x(url) if stype == "x" else ingest_web(url)
    title = info["title"] or normalized
    path = source_note_path(root, url, title)
    path.parent.mkdir(parents=True, exist_ok=True)
    status = "summarized" if info.get("content_status") in {"summarized", "transcript_summarized", "asr_summarized", "converted_summarized"} else "unread"
    tags = extract_tags(title, info.get("raw_text") or info.get("summary") or "", stype)
    fields = {"type": "source", "title": title, "source_url": url, "normalized_url": normalized, "source_type": stype, "domain": urlparse(normalized).netloc, "author": info.get("author", ""), "published": info.get("published", ""), "captured": today(), "status": status, "content_status": info.get("content_status", "metadata_only"), "content_provider": info.get("content_provider", ""), "file_type": info.get("file_type", ""), "converted_path": info.get("converted_path", ""), "tags": tags}
    body = [frontmatter(fields), "", f"# {title}", "", "## Summary", "", info.get("summary", "").strip(), "", "## Key Points", "", "\n".join(f"- {p}" for p in info.get("key_points", [])), "", "## Quotes", "", "\n".join(f"- {p}" for p in info.get("quotes", [])), "", "## My Memo", "", "", "## Related", ""]
    path.write_text("\n".join(body).rstrip() + "\n", encoding="utf-8")
    ingested[normalized] = {"source_url": url, "normalized_url": normalized, "note_path": str(path.relative_to(root)), "title": title, "source_type": stype, "captured": today(), "last_checked": today(), "content_hash": "sha256:" + hashlib.sha256((info.get("raw_text") or info.get("summary") or "").encode()).hexdigest(), "status": status}
    write_json(root / "logs/ingested.json", ingested)
    print(f"Wrote: {path.relative_to(root)}")
    return path


def chrome_bookmark_files(chrome_profile: str | None = None) -> list[Path]:
    base = Path.home() / "Library/Application Support/Google/Chrome"
    if not base.exists():
        return []
    return [child / "Bookmarks" for child in base.iterdir() if child.is_dir() and (not chrome_profile or child.name == chrome_profile) and (child / "Bookmarks").exists()]


def collect_bookmark_urls(node: dict, folder_name: str, inside: bool = False) -> list[str]:
    urls = []
    now_inside = inside or (node.get("type") == "folder" and node.get("name") == folder_name)
    if now_inside and node.get("type") == "url" and node.get("url"):
        urls.append(node["url"])
    for child in node.get("children", []) or []:
        if isinstance(child, dict):
            urls.extend(collect_bookmark_urls(child, folder_name, now_inside))
    return urls


def list_bookmark_folders(chrome_profile: str | None = None) -> None:
    def walk(node, path, profile):
        if node.get("type") == "folder":
            current = [*path, node.get("name", "")]
            print(f"{profile}: {' / '.join(x for x in current if x)}")
            for child in node.get("children", []) or []:
                if isinstance(child, dict):
                    walk(child, current, profile)
    for path in chrome_bookmark_files(chrome_profile):
        data = read_json(path, {})
        for root_node in (data.get("roots") or {}).values():
            if isinstance(root_node, dict):
                walk(root_node, [], path.parent.name)


def ingest_bookmarks(root: Path, limit: int | None = None, bookmark_folder: str | None = None, chrome_profile: str | None = None) -> None:
    ensure_vault(root)
    cfg = vault_config(root)
    folder = bookmark_folder or cfg.get("bookmark_folder") or DEFAULT_BOOKMARK_FOLDER
    profile = chrome_profile if chrome_profile is not None else (cfg.get("chrome_profile") or None)
    urls: list[str] = []
    for path in chrome_bookmark_files(profile):
        data = read_json(path, {})
        for root_node in (data.get("roots") or {}).values():
            if isinstance(root_node, dict):
                urls.extend(collect_bookmark_urls(root_node, folder))
    urls = dedupe(urls)
    if limit is not None:
        urls = urls[:limit]
    print(f"Bookmark folder '{folder}' URLs from {profile or 'all Chrome profiles'}: {len(urls)}")
    for url in urls:
        try:
            write_source(root, url)
        except Exception as exc:
            print(f"Failed: {url}: {exc}", file=sys.stderr)


def iter_markdown(root: Path, dirs: list[str] | None = None) -> list[Path]:
    dirs = dirs or ["notes", "sources", "daily", "inbox", "system"]
    paths: list[Path] = []
    for name in dirs:
        base = root / name
        if base.exists():
            paths.extend(sorted(base.rglob("*.md")))
    return paths


def query(root: Path, terms: list[str], limit: int = 30) -> None:
    ensure_vault(root)
    needles = [term.lower() for term in terms if term.strip()]
    results = []
    for path in iter_markdown(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        score = sum(text.lower().count(n) for n in needles)
        if score <= 0:
            continue
        fm, body = parse_frontmatter(text)
        hit = next((clean_space(line) for line in body.splitlines() if any(n in line.lower() for n in needles)), "")
        results.append((score, path, fm.get("title", path.stem), hit))
    for score, path, title, hit in sorted(results, key=lambda x: (-x[0], str(x[1])))[:limit]:
        print(f"- {path.relative_to(root)} | score={score} | {title}")
        if hit:
            print(f"  {hit[:220]}")


def create_note(root: Path, theme: str, category: str = "general") -> Path:
    ensure_vault(root)
    path = root / "notes" / ascii_slug(category, "general") / f"{ascii_slug(theme, 'knowledge')}.md"
    if path.exists():
        print(f"Already exists: {path.relative_to(root)}")
        return path
    words = [x for x in re.split(r"[\s/-]+", theme.lower()) if x]
    related = []
    for src in iter_markdown(root, ["sources", "notes"]):
        text = src.read_text(encoding="utf-8", errors="replace")
        score = sum(text.lower().count(w) for w in words)
        if score:
            fm, _ = parse_frontmatter(text)
            related.append((score, src, fm.get("title", src.stem)))
    related = sorted(related, key=lambda x: (-x[0], str(x[1])))[:12]
    fields = {"type": "knowledge", "title": theme, "updated": today(), "tags": dedupe([ascii_slug(w) for w in words])[:8]}
    body = [frontmatter(fields), "", f"# {theme}", "", "## Conclusion", "", "TODO: 関連 Source を読んで、自分の結論をここに統合する。", "", "## Important Insights", ""]
    body.extend(f"- [[{src.stem}]]: {title}" for _, src, title in related[:8])
    body.extend(["", "## Best Practices", "", "## Open Questions", "", "## Related Sources", ""])
    body.extend(f"- [[{src.stem}]]" for _, src, _ in related if "/sources/" in "/" + str(src.relative_to(root)))
    body.extend(["", "## Related Notes", ""])
    body.extend(f"- [[{src.stem}]]" for _, src, _ in related if "/notes/" in "/" + str(src.relative_to(root)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote: {path.relative_to(root)}")
    return path


def daily(root: Path, date: str | None = None) -> Path:
    ensure_vault(root)
    date = date or today()
    inbox, unread, unlinked, orphan = [], [], [], []
    for path in iter_markdown(root, ["inbox", "sources", "notes"]):
        text = path.read_text(encoding="utf-8", errors="replace")
        fm, body = parse_frontmatter(text)
        rel = path.relative_to(root)
        if fm.get("type") == "inbox" and fm.get("status") == "unprocessed":
            inbox.append(rel)
        if fm.get("type") == "source" and fm.get("status") == "unread":
            unread.append(rel)
        if fm.get("type") == "source" and fm.get("status") == "summarized" and "[[" not in body:
            unlinked.append(rel)
        if fm.get("type") == "knowledge" and "[[" not in body:
            orphan.append(rel)
    fields = {"type": "daily", "date": date, "created": today(), "tags": ["daily-review"]}
    path = root / "daily" / f"{date}.md"
    def bullets(items, empty): return "\n".join(f"- {x}" for x in items) if items else f"- {empty}"
    body = [frontmatter(fields), "", f"# Daily Review {date}", "", "## Inbox Review", "", bullets(inbox, "未処理 inbox はありません。"), "", "## New Sources", "", bullets(unread, "unread Source はありません。"), "", "## Notes Updated", "", "- TODO: 今日更新した Knowledge Note を確認する。", "", "## Orphan Notes", "", bullets(orphan, "孤立 Knowledge Note はありません。"), "", "## Suggested Promotions", "", bullets(unlinked, "Knowledge Note 化候補はありません。"), "", "## Actions", "", "- 必要な Source Note を Knowledge Note に統合する。"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote: {path.relative_to(root)}")
    return path


def link(root: Path, limit: int = 50) -> None:
    ensure_vault(root)
    entries = []
    for path in iter_markdown(root, ["notes", "sources"]):
        text = path.read_text(encoding="utf-8", errors="replace")
        fm, body = parse_frontmatter(text)
        tags = fm.get("tags") if isinstance(fm.get("tags"), list) else []
        entries.append((path, fm.get("title", path.stem), set(tags), body))
    count = 0
    for path, title, tags, body in entries:
        suggestions = []
        for other, other_title, other_tags, _ in entries:
            if other == path or f"[[{other.stem}]]" in body:
                continue
            shared = sorted((tags & other_tags) - {"web", "youtube", "x", "zenn", "qiita"})
            if shared:
                suggestions.append((len(shared), other, other_title, shared))
        if suggestions:
            print(f"\n{path.relative_to(root)} | {title}")
            for _, other, other_title, shared in sorted(suggestions, key=lambda x: (-x[0], str(x[1])))[:5]:
                print(f"- [[{other.stem}]] | {other_title} | tags: {', '.join(shared)}")
                count += 1
                if count >= limit:
                    return


def embedded_file_map(bookmark_folder: str, chrome_profile: str, language: str) -> dict[str, str]:
    cfg = {"bookmark_folder": bookmark_folder, "chrome_profile": chrome_profile, "language": language, "auto_commit": False, "auto_push": False, "x_provider": "hermes"}
    return {
        ".obsidian-kb.json": json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
        ".gitignore": ".obsidian/workspace.json\n.obsidian/workspace-mobile.json\n.trash/\n.DS_Store\n",
        "AGENTS.md": "# AGENTS.md instructions for Obsidian bookmark wiki\n\n常に日本語で回答してください。\n\nこのリポジトリは Obsidian vault です。\n",
        "logs/ingested.json": "{}\n",
        "logs/query-history.json": "[]\n",
        "templates/source-note.md": "---\ntype: source\ntitle:\nsource_url:\nnormalized_url:\nsource_type:\ndomain:\nauthor:\npublished:\ncaptured:\nstatus: unread\ncontent_status: metadata_only\ncontent_provider:\ntags: []\n---\n\n# {{title}}\n\n## Summary\n\n## Key Points\n\n## Quotes\n\n## My Memo\n\n## Related\n",
        "templates/knowledge-note.md": "---\ntype: knowledge\ntitle:\nupdated:\ntags: []\n---\n\n# {{title}}\n\n## Conclusion\n\n## Important Insights\n\n## Best Practices\n\n## Open Questions\n\n## Related Sources\n\n## Related Notes\n",
        "templates/inbox-note.md": "---\ntype: inbox\ntitle:\ncreated:\nstatus: unprocessed\ntags: []\n---\n\n# {{title}}\n\n## Capture\n\n## Context\n\n## Next Action\n",
        "templates/daily-note.md": "---\ntype: daily\ndate:\ncreated:\ntags:\n  - daily-review\n---\n\n# Daily Review {{date}}\n\n## Inbox Review\n\n## New Sources\n\n## Notes Updated\n\n## Orphan Notes\n\n## Suggested Promotions\n\n## Actions\n",
        "system/ai-native-knowledge-system.md": f"---\ntype: system\nsystem_type: architecture\nstatus: active\nupdated: {today()}\ntags:\n  - ai-native\n  - knowledge-system\n  - obsidian\n---\n\n# AI Native Knowledge System\n\n- bookmark_folder: {bookmark_folder}\n- chrome_profile: {chrome_profile or 'not fixed'}\n\nChrome Bookmark を queue、Obsidian Markdown を knowledge base として扱う。\n",
    }


def init_vault(root: Path, bookmark_folder: str, chrome_profile: str, language: str, force: bool = False) -> None:
    if root.exists() and any(root.iterdir()) and not force:
        raise SystemExit(f"Refusing to initialize non-empty directory without --force: {root}")
    dirs = ["inbox", "sources/zenn", "sources/qiita", "sources/youtube", "sources/x", "sources/web", "sources/documents", "notes/ai", "notes/frontend", "notes/gaming", "notes/general", "daily", "templates", "logs", "assets", "assets/extracted", "system/skills"]
    for name in dirs:
        (root / name).mkdir(parents=True, exist_ok=True)
        if name not in {"templates", "logs", "system/skills"}:
            (root / name / ".gitkeep").touch()
    template_root = repo_root() / "vault-template"
    if template_root.exists():
        for src in template_root.rglob("*"):
            if src.is_dir():
                continue
            rel = src.relative_to(template_root)
            if rel.name == ".obsidian-kb.example.json":
                continue
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists() or force:
                shutil.copy2(src, dst)
    for rel, content in embedded_file_map(bookmark_folder, chrome_profile, language).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or force or rel == ".obsidian-kb.json":
            path.write_text(content, encoding="utf-8")
    print(f"Initialized vault: {root}")




def install_deps(force: bool = False) -> None:
    venv = skill_dir() / ".venv"
    python = venv / "bin" / "python"
    if force and venv.exists():
        shutil.rmtree(venv)
    if not python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "markitdown[pdf,xlsx,xls,docx,pptx]"], check=True)
    print(f"Installed document dependencies: {venv}")


def install_skill(codex_home_path: Path, force: bool = True) -> None:
    src = repo_root() / "skills" / SKILL_NAME
    if not src.exists():
        raise SystemExit(f"Bundled skill not found: {src}")
    dst = codex_home_path / "skills" / SKILL_NAME
    if dst.exists():
        if not force:
            raise SystemExit(f"Skill already exists: {dst}. Use --force to overwrite.")
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"Installed skill: {dst}")


def resolve_root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    env = os.environ.get("OBSIDIAN_WIKI_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Obsidian Bookmark Wiki Kit CLI")
    parser.add_argument("--root", default=None, help="Vault root. Defaults to OBSIDIAN_WIKI_ROOT or cwd.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("install-deps")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("install-skill")
    p.add_argument("--codex-home", default=str(codex_home()))
    p.add_argument("--no-force", action="store_true")

    p = sub.add_parser("init-vault")
    p.add_argument("--root", required=True)
    p.add_argument("--bookmark-folder", default=DEFAULT_BOOKMARK_FOLDER)
    p.add_argument("--chrome-profile", default="")
    p.add_argument("--language", default="ja")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("ingest-url")
    p.add_argument("url")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("ingest-bookmarks")
    p.add_argument("--bookmark-folder", default=None)
    p.add_argument("--chrome-profile", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--list-folders", action="store_true")

    p = sub.add_parser("query")
    p.add_argument("terms", nargs="+")
    p.add_argument("--limit", type=int, default=30)

    p = sub.add_parser("note")
    p.add_argument("theme")
    p.add_argument("--category", default="general")

    p = sub.add_parser("daily")
    p.add_argument("--date", default=None)

    p = sub.add_parser("link")
    p.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()

    if args.cmd == "install-deps":
        install_deps(args.force)
        return
    if args.cmd == "install-skill":
        install_skill(Path(args.codex_home).expanduser(), force=not args.no_force)
        return
    if args.cmd == "init-vault":
        init_vault(Path(args.root).expanduser().resolve(), args.bookmark_folder, args.chrome_profile, args.language, args.force)
        return

    root = resolve_root(args.root)
    if args.cmd == "ingest-url":
        write_source(root, args.url, args.force)
    elif args.cmd == "ingest-bookmarks":
        if args.list_folders:
            cfg = vault_config(root) if root.exists() else {}
            list_bookmark_folders(args.chrome_profile if args.chrome_profile is not None else (cfg.get("chrome_profile") or None))
        else:
            ingest_bookmarks(root, args.limit, args.bookmark_folder, args.chrome_profile)
    elif args.cmd == "query":
        query(root, args.terms, args.limit)
    elif args.cmd == "note":
        create_note(root, args.theme, args.category)
    elif args.cmd == "daily":
        daily(root, args.date)
    elif args.cmd == "link":
        link(root, args.limit)


if __name__ == "__main__":
    main()
