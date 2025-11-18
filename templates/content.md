---
date: '{{ date }}'
title: {{ title }}
draft: false
tags:{% for tag in tags %}
- {{ tag }}{% endfor %}
slug: {{ slug }}
description: '{{ description }}'
markup: md
url: {{ url }}
aliases:
- {{ alias }}

---

(Write your content here!)
