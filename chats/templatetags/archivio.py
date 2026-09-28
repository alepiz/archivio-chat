from django import template
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt

register = template.Library()

# html=False: l'HTML presente nelle chat viene mostrato come testo, mai eseguito
_md = MarkdownIt("commonmark", {"html": False, "linkify": False, "breaks": True}).enable(
    ["table", "strikethrough"])


def _open_links_in_new_tab(self, tokens, idx, options, env):
    tokens[idx].attrSet("target", "_blank")
    tokens[idx].attrSet("rel", "noopener noreferrer")
    return self.renderToken(tokens, idx, options, env)


_md.add_render_rule("link_open", _open_links_in_new_tab)


@register.filter
def markdown(text):
    return mark_safe(_md.render(text or ""))


ROLE_LABELS = {"user": "Tu", "assistant": "ChatGPT", "tool": "Strumento"}


@register.filter
def role_label(msg):
    if msg.role == "tool" and msg.author_name:
        return f"Strumento · {msg.author_name}"
    return ROLE_LABELS.get(msg.role, msg.role)


@register.filter
def filesize(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
