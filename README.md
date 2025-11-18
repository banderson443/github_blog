# banderson443.github.io

Whoops, I built a static site generator. This is also now my personal site.

## Goals

Why did I do this?

> mostly because I'm lazy and got tired of trying to learn the other sysems (hugo)

I also had some very clear goals:

- Ability to write content in markdown (with support for [CommonMark](https://commonmark.org/)
- I just wanted simple, easy-to-learn template engine (Hello Jinja)
- Ability to keep the same URLs that I had in django-blargg (good urls don't change)
- A command-line tool to build content (TBD, i'll get there eventually)
- Ability to just publish on github pages

### Content

Directory structure is broken into

    content/
        blog/
            <title-slug>/index.md
        page/
            <title>.md

The index page should be a listing of _recent_ posts.


## built with

- [jinja](https://jinja.palletsprojects.com/)
- [markdown-it-py](https://github.com/executablebooks/markdown-it-py)
- [simple.css](https://github.com/kevquirk/simple.css)
