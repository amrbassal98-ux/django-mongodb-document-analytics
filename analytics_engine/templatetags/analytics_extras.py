import json

from django import template
from django.utils.safestring import mark_safe
from django.utils.html import conditional_escape

register = template.Library()


@register.filter
def json_pretty(value):
    try:
        dumped = json.dumps(value, indent=2, ensure_ascii=False)
        return mark_safe(dumped)
    except Exception:
        return str(value)


@register.filter(is_safe=True, needs_autoescape=True)
def render_payload(value, autoescape=True):
    try:
        html = _render_value(value, level=0, autoescape=autoescape)
        return mark_safe(html)
    except Exception:
        return mark_safe('<div class="text-danger small">Unable to render payload.</div>')


def _esc(text, autoescape):
    return conditional_escape(str(text)) if autoescape else str(text)


def _render_value(value, level, autoescape):
    if isinstance(value, dict):
        return _render_dict(value, level, autoescape)
    elif isinstance(value, list):
        return _render_list(value, level, autoescape)
    elif isinstance(value, bool):
        badge_class = "bg-success" if value else "bg-secondary"
        label = "true" if value else "false"
        return f'<span class="badge {badge_class}">{label}</span>'
    elif isinstance(value, (int, float)):
        cls = "text-warning fw-semibold" if isinstance(value, float) else "text-info fw-semibold"
        return f'<span class="{cls}">{_esc(value, autoescape)}</span>'
    elif value is None:
        return '<span class="text-body-secondary fst-italic">null</span>'
    else:
        return _esc(value, autoescape)


def _clean_key(key):
    return str(key).replace("_", " ").title()


def _render_dict(d, level, autoescape):
    if level > 3:
        items = ", ".join(f"{_clean_key(k)}: {_render_value(v, level + 1, autoescape)}" for k, v in d.items())
        return f'<span class="text-body-secondary small">&#123;{items}&#125;</span>'

    rows = []
    for key, value in d.items():
        display_key = _clean_key(key)
        rendered_val = _render_value(value, level + 1, autoescape)
        if level == 0:
            rows.append(
                f'<dt class="col-sm-4 text-body-secondary text-truncate">{_esc(display_key, autoescape)}</dt>\n'
                f'<dd class="col-sm-8">{rendered_val}</dd>'
            )
        else:
            rows.append(
                f'<div class="mb-1"><span class="text-body-secondary small fw-medium">{_esc(display_key, autoescape)}: </span>{rendered_val}</div>'
            )

    if level == 0:
        return f'<dl class="row mb-0">{"".join(rows)}</dl>'
    else:
        return f'<div class="card card-body p-2 mb-2 bg-body-tertiary border-body-tertiary">{"".join(rows)}</div>'


def _render_list(lst, level, autoescape):
    if not lst:
        return '<span class="text-body-secondary fst-italic small">empty list</span>'

    all_simple = all(not isinstance(item, (dict, list)) for item in lst)
    if all_simple and len(lst) <= 12:
        badges = " ".join(
            f'<span class="badge bg-secondary me-1">{_render_value(item, level + 1, autoescape)}</span>'
            for item in lst
        )
        return f'<div class="d-inline-flex flex-wrap gap-1">{badges}</div>'
    else:
        items = "".join(
            f'<li class="list-group-item border-0 py-1">{_render_value(item, level + 1, autoescape)}</li>'
            for item in lst
        )
        return f'<ul class="list-group list-group-flush mb-0">{items}</ul>'
