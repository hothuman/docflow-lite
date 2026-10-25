"""Configure a real HTTPS base URL, including GitHub Pages subdirectories."""
from pathlib import Path
from urllib.parse import urlsplit
import re
import sys


def normalize_base(value: str) -> tuple[str, str]:
    raw = value.strip()
    if re.search(r"[\x00-\x20\\]", raw):
        raise ValueError("В адресе недопустимы пробелы, управляющие символы и обратные слеши")
    parts = urlsplit(raw)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment):
        raise ValueError("Нужен реальный HTTPS-адрес без логина, параметров и фрагмента")
    host = parts.hostname.encode("idna").decode("ascii").lower()
    if not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split(".")):
        raise ValueError("Некорректное имя хоста")
    port = parts.port
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Некорректный порт")
    origin = "https://" + host + (":" + str(port) if port else "")
    path = parts.path
    if path and path != "/":
        segments = path.removeprefix("/").removesuffix("/").split("/")
        if any(segment in ("", ".", "..") or not re.fullmatch(r"[A-Za-z0-9._~-]+", segment) for segment in segments):
            raise ValueError("Подкаталоги должны состоять из обычных URL-символов без . или ..")
        prefix = "/" + "/".join(segments) + "/"
    else:
        prefix = "/"
    return origin + prefix, prefix


def configure(value: str, directory: Path, index_home: bool = True) -> str:
    home, prefix = normalize_base(value)
    prepared = {}
    indexed = []
    for name in ("index.html", "privacy.html", "terms.html", *([name for name in ("service.html","software.html") if (directory/name).is_file()])):
        html = (directory / name).read_text(encoding="utf-8")
        page_url = home if name == "index.html" else home + name
        html = re.sub(r'\s*<link rel="canonical"[^>]*>', "", html)
        html = re.sub(r'\s*<meta property="og:url"[^>]*>', "", html)
        html = re.sub(r'\s*<meta name="robots"[^>]*>', "", html)
        html = re.sub(r'(<meta property="og:image" content=")[^"]*', r'\g<1>' + home + "assets/social-card.png", html)
        robots = "index,follow" if name == "index.html" and index_home else "noindex,follow"
        html = html.replace("</head>", f'  <link rel="canonical" href="{page_url}">\n  <meta property="og:url" content="{page_url}">\n  <meta name="robots" content="{robots}">\n</head>')
        prepared[name] = html
        if not re.search(r'<meta\s+name="robots"\s+content="[^"]*noindex', html, re.I):
            indexed.append(page_url)
    # Validate/read every input before changing any file.
    for name, html in prepared.items():
        (directory / name).write_text(html, encoding="utf-8")
    urls = "".join("<url><loc>" + url + "</loc></url>" for url in indexed)
    (directory / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + '</urlset>\n', encoding="utf-8")
    robots_text = "User-agent: *\nAllow: " + prefix + "\nSitemap: " + home + "sitemap.xml\n" if index_home else "User-agent: *\nDisallow: /\n"
    (directory / "robots.txt").write_text(robots_text, encoding="utf-8")
    return home


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Передайте реальный HTTPS-адрес опубликованного сайта одним аргументом")
    try:
        result = configure(sys.argv[1], Path(__file__).resolve().parents[1] / "dist")
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print("Обновлены canonical, Open Graph, sitemap и robots для " + result)
