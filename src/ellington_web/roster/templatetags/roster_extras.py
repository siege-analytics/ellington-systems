from django import template

register = template.Library()


@register.simple_tag
def bar_width_px(count: int, max_count: int, max_px: int = 300) -> int:
    if not max_count:
        return 0
    return int(round((count / max_count) * max_px))
