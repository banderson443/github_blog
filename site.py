#!/usr/bin/env python3
"""
Static site generator with configuration file support.
Now supports config.yaml for easy customization.
"""
import http.server
import json
import logging
import os
import re
import shutil
import string
import unicodedata
from collections import defaultdict
from glob import glob
from itertools import chain
from pathlib import Path
from time import time

import arrow
import ez_yaml
import rich_click as click
from feedgen.feed import FeedGenerator
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from mdit_py_plugins.front_matter import front_matter_plugin

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# Default configuration
DEFAULT_CONFIG = {
    "site": {
        "title": "Firstname Lastname",
        "author": "Firstname Lastname",
        "url": "https://blog.banderson443.me",
        "description": "Personal blog and writings",
    },
    "paths": {
        "content": "content",
        "output": "docs",
        "templates": "templates",
        "static": "static",
    },
    "build": {
        "posts_per_page": 20,
        "include_drafts": False,
    },
    "feeds": {
        "enabled": True,
        "rss_path": "/feed/rss/",
        "atom_path": "/feed/atom/",
    }
}


def load_config(config_file="config.yaml"):
    """Load configuration from YAML file, fall back to defaults."""
    if Path(config_file).exists():
        logger.info(f"Loading config from {config_file}")
        with open(config_file) as f:
            user_config = ez_yaml.to_object(f.read())
            # Merge with defaults
            config = DEFAULT_CONFIG.copy()
            for key in user_config:
                if isinstance(user_config[key], dict):
                    config[key].update(user_config[key])
                else:
                    config[key] = user_config[key]
            return config
    else:
        logger.warning(f"{config_file} not found, using defaults")
        return DEFAULT_CONFIG


def to_slug(value):
    def _slugify(s):
        for c in s.lower().replace(" ", "-"):
            if c in string.ascii_lowercase + "-":
                yield c
    return "".join(list(_slugify(value)))


def find_markdown_files(parent: str) -> list:
    """Return a list of all .md files in the given parent directory"""
    files = list(glob(f"{parent}/**/*.md", recursive=True))
    logger.info("Found %s markdown files in %s", len(files), parent)
    return files


def parse_front_matter(tokens: list) -> dict:
    """Parse YAML frontmatter from markdown tokens."""
    tokens = [t for t in tokens if t.type == "front_matter"]
    if len(tokens) == 0:
        return {}

    t = tokens[0]
    fm = dict(ez_yaml.to_object(t.content))

    try:
        dt = arrow.get(fm["date"]).to("utc").datetime
        fm["date"] = dt
    except Exception as err:
        logger.error("Failed to convert %s: %s", fm.get("date"), str(err))
    return fm


def validate_frontmatter(context: dict, filename: str) -> None:
    """Validate required frontmatter fields."""
    required = ['title']
    missing = [field for field in required if field not in context]
    if missing:
        logger.warning(f"{filename}: Missing fields: {', '.join(missing)}")


def get_template_context(filename):
    logger.info("Building context for %s", filename)
    content = Path(filename).read_text()
    md = MarkdownIt().use(front_matter_plugin).enable("table")
    context = parse_front_matter(md.parse(content))
    context["html_content"] = md.render(content)
    validate_frontmatter(context, filename)
    return context


def get_template_name(filename: str, content_dir: str, default: str = "page.html") -> str:
    """Figure out which .html template to use."""
    mappings = {
        "blog": "blog.html",
        "pages": "page.html",
    }
    parent = str(filename).strip(content_dir).split("/")[0]
    path = str(Path(mappings.get(parent, default)))
    return path


def get_output_paths(output_dir: str, context: dict, file: str) -> str:
    urls = []
    if "url" in context:
        urls.append(context["url"].strip("/"))
    if "aliases" in context:
        urls += [u.strip("/") for u in context["aliases"]]

    if len(urls) == 0:
        urls = [Path(file).stem]

    results = []
    for url in urls:
        path = Path(output_dir) / Path(url)
        path.mkdir(parents=True, exist_ok=True)
        path = path / Path("index.html")
        results.append(str(path))
    return results


def build_static(output):
    """Copy static files to output directory."""
    static_output = Path(output) / Path("static")
    logger.info("Building Static output in: %s", static_output)
    if Path("static").exists():
        shutil.copytree(Path("static"), static_output, dirs_exist_ok=True)
    else:
        logger.warning("No static directory found, skipping")


def render(env, path, template, context):
    """Render a jinja template."""
    filename = "index.html" if template.endswith("html") else "index.md"
    template = env.get_template(template)
    content = template.render(**context)
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    path = path / Path(filename)
    with open(path, "w") as f:
        f.write(content)
        logger.info("Wrote %s", path)


def build_index(env, output: str, index: list, config: dict):
    """Build index pages."""
    posts_per_page = config["build"]["posts_per_page"]
    site_title = config["site"]["title"]
    
    index = sorted(index, key=lambda d: d["date"], reverse=True)

    context = {
        "title": site_title,
        "subtitle": "Latest posts...",
        "posts": index[:posts_per_page],
    }
    render(env, Path(output), "index.html", context)

    context = {
        "title": site_title,
        "subtitle": f"{site_title}. All of it.",
        "posts": index,
    }
    render(env, Path(output) / Path("blog"), "index.html", context)


def build_date_archives(env, output: str, index: list, config: dict):
    """Build date-based archives."""
    articles = defaultdict(list)
    for post in index:
        pub_year = post["date"].strftime("%Y")
        pub_month = post["date"].strftime("%Y/%m")
        pub_day = post["date"].strftime("%Y/%m/%d")
        year_path = f"blog/{pub_year}"
        month_path = f"blog/{pub_month}"
        day_path = f"blog/{pub_day}"
        articles[year_path].append(post)
        articles[month_path].append(post)
        articles[day_path].append(post)

    for path, posts in articles.items():
        context = {
            "title": config["site"]["title"],
            "subtitle": "Archive",
            "posts": posts,
        }
        render(env, f"{output}/{path}", "index.html", context)


def normalize_tag(value: str) -> str:
    """Normalize tags into URL-safe strings."""
    value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")


def build_tags(env, output: str, index: list, config: dict) -> None:
    """Build tag index and tag pages."""
    site_title = config["site"]["title"]
    
    tags = sorted(set(chain(*[post.get("tags", []) for post in index])))
    tags = [normalize_tag(tag) for tag in tags]
    context = {
        "title": site_title,
        "subtitle": "Tags",
        "tags": [(tag, f"/blog/tags/{tag}/") for tag in tags],
    }
    render(env, f"{output}/blog/tags/", "tags.html", context)

    by_tags = defaultdict(list)
    for post in index:
        for tag in post.get("tags", []):
            tag = normalize_tag(tag)
            by_tags[tag].append(post)

    for tag, posts in by_tags.items():
        context = {
            "title": site_title,
            "subtitle": f"Tagged {tag}",
            "posts": posts,
        }
        render(env, f"{output}/blog/tags/{tag}", "index.html", context)


def build_feeds(output: str, index: list, config: dict) -> None:
    """Build RSS and Atom feeds."""
    if not config["feeds"]["enabled"]:
        logger.info("Feeds disabled, skipping")
        return
        
    site_url = config["site"]["url"]
    site_title = config["site"]["title"]
    author = config["site"]["author"]
    
    rss_path = Path(output) / Path("feed/rss/")
    rss_file = rss_path / Path("rss.xml")
    os.makedirs(rss_path, exist_ok=True)
    rss_file.touch(exist_ok=True)

    atom_path = Path(output) / Path("feed/atom/")
    atom_file = atom_path / Path("atom.xml")
    os.makedirs(atom_path, exist_ok=True)
    atom_file.touch(exist_ok=True)

    fg = FeedGenerator()
    fg.id(site_url)
    fg.title(site_title)
    fg.author({"name": author})
    fg.link(href=site_url, rel="alternate")
    fg.subtitle(config["site"]["description"])
    fg.language("en")

    items = sorted(
        [post for post in index if not post.get("draft", False)], 
        key=lambda p: p["date"]
    )
    for post in items:
        fe = fg.add_entry()
        fe.id(site_url + post["url"])
        fe.author(name=author)
        fe.title(post["title"])
        fe.link(href=site_url + post["url"])
        fe.content(post["html_content"])
        fe.description(description=post.get("description", ""))
        fe.pubdate(post["date"])

    logger.info("Generating feeds")
    fg.atom_file(atom_file)
    fg.rss_file(rss_file)
    logger.info("Wrote feeds to %s", output)


def build_sitemap(output: str, index: list, config: dict) -> None:
    """Generate XML sitemap."""
    site_url = config["site"]["url"]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>']
    sitemap.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    for post in index:
        if post.get("draft", False):
            continue
        sitemap.append('  <url>')
        sitemap.append(f'    <loc>{site_url}{post["url"]}</loc>')
        sitemap.append(f'    <lastmod>{post["date"].strftime("%Y-%m-%d")}</lastmod>')
        sitemap.append('  </url>')
    
    sitemap.append('</urlset>')
    
    sitemap_file = Path(output) / "sitemap.xml"
    with open(sitemap_file, 'w') as f:
        f.write('\n'.join(sitemap))
    logger.info("Wrote sitemap to %s", sitemap_file)


def copy_texts(content: str, output: str) -> None:
    """Copy .txt files to root."""
    src_path = Path(content) / Path("texts")
    dst_path = Path(output)
    if not src_path.exists():
        logger.info("No texts directory found, skipping")
        return
    for file in glob(f"{src_path}/*.txt"):
        logger.info("Copying %s to %s", file, dst_path)
        shutil.copyfile(file, str(dst_path / Path(file).name))


def copy_cname(output: str) -> None:
    """Copy CNAME file to output directory for GitHub Pages."""
    cname_file = Path("CNAME")
    if cname_file.exists():
        dst_file = Path(output) / "CNAME"
        shutil.copyfile(str(cname_file), str(dst_file))
        logger.info("Copied CNAME to %s", dst_file)
    else:
        logger.info("No CNAME file found, skipping")


def build_dev_page(env, output: str) -> None:
    """Build the hidden developer tools page."""
    template = env.get_template("dev.html")
    html_content = template.render()
    dev_path = Path(output) / Path("dev")
    dev_path.mkdir(parents=True, exist_ok=True)
    dev_file = dev_path / Path("index.html")
    with open(dev_file, "w") as f:
        f.write(html_content)
        logger.info("Wrote: %s", dev_file)


@click.group()
def cli():
    pass


@cli.command()
@click.option("--config", default="config.yaml", help="Config file")
@click.option("--addr", default="")
@click.option("--port", default=8000)
def server(config, addr, port):
    """Run a local preview HTTP server."""
    cfg = load_config(config)
    output = cfg["paths"]["output"]
    
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, request, client_address, server, directory=output):
            super().__init__(request, client_address, server, directory=output)

    httpd = http.server.HTTPServer((addr, port), Handler)
    logger.info("Listening on %s:%s in %s...", addr, port, output)
    httpd.serve_forever()


@cli.command()
@click.option("--config", default="config.yaml", help="Config file")
def new(config):
    """Create a new post."""
    cfg = load_config(config)
    templates_dir = cfg["paths"]["templates"]
    env = Environment(loader=FileSystemLoader(templates_dir), autoescape=select_autoescape())

    prompts = [
        ("date", "Date (default is now): "),
        ("title", "Title: "),
        ("tags", "Tags (comma-separated): "),
        ("description", "Description: "),
        ("draft", "Draft (false): "),
    ]
    context = {}
    for key, prompt in prompts:
        context[key] = input(prompt)
        if key == "title":
            context["slug"] = to_slug(context[key])
        elif key == "date":
            context[key] = (
                arrow.utcnow().datetime
                if not context[key]
                else arrow.get(context[key]).datetime
            )
        elif key == "draft":
            context[key] = True if context[key] == "true" else False
        elif key == "tags":
            context[key] = [normalize_tag(tag) for tag in context[key].split(",")]

    context["url"] = f"/blog/{context['slug']}/"
    datestring = context["date"].strftime("%Y/%m/%d")
    context["alias"] = f"/blog/{datestring}/{context['slug']}/"
    
    content_dir = cfg["paths"]["content"]
    render(env, f"{content_dir}/blog/{context['slug']}", "content.md", context)


@cli.command()
@click.option("--config", default="config.yaml", help="Config file")
def build(config):
    """Build the site."""
    start = time()
    cfg = load_config(config)
    
    content = cfg["paths"]["content"]
    output = cfg["paths"]["output"]
    templates_dir = cfg["paths"]["templates"]

    env = Environment(loader=FileSystemLoader(templates_dir), autoescape=select_autoescape())
    index = []

    for file in find_markdown_files(content):
        context = get_template_context(file)
        
        # Skip drafts if configured
        if context.get("draft") and not cfg["build"]["include_drafts"]:
            logger.info("Skipping draft: %s", file)
            continue
            
        template = env.get_template(get_template_name(file, content))
        html_content = template.render(**context)

        for path in get_output_paths(output, context, file):
            with open(path, "w") as f:
                f.write(html_content)
                logger.info("Wrote: %s", path)

        if file.strip(content).startswith("/blog"):
            index.append(context)

    build_index(env, output, index, cfg)
    build_tags(env, output, index, cfg)
    build_date_archives(env, output, index, cfg)
    build_feeds(output, index, cfg)
    build_sitemap(output, index, cfg)
    build_dev_page(env, output)
    build_static(output)
    copy_texts(content, output)
    copy_cname(output)

    elapsed = round(time() - start, 2)
    logger.info("Completed in %s seconds", elapsed)


@cli.command()
def init():
    """Create a default config.yaml file."""
    config_file = Path("config.yaml")
    if config_file.exists():
        logger.error("config.yaml already exists!")
        return
    
    config_content = """# Site Configuration
site:
  title: "Firstname Lastname"
  author: "Firstname Lastname"
  url: "https://blog.banderson443.me"
  description: "Personal blog and writings"

paths:
  content: "content"
  output: "docs"
  templates: "templates"
  static: "static"

build:
  posts_per_page: 20
  include_drafts: false

feeds:
  enabled: true
  rss_path: "/feed/rss/"
  atom_path: "/feed/atom/"
"""
    
    with open(config_file, 'w') as f:
        f.write(config_content)
    logger.info("Created config.yaml")


if __name__ == "__main__":
    cli()
