# banderson443.github.io

Python based static site generator. This is also my personal site for now.

## Goals

Why did I do this?

> mostly because I'm lazy and wanted a python based blog, maybe i'll put something useful here. 

 goals:

- Ability to write content in markdown (with support for [CommonMark](https://commonmark.org/)
- Simple, easy-to-learn template engine (Jinja)  
- TODO: A command-line tool to build content (eta TBD)
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
