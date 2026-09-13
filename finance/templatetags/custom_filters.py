from django import template

register = template.Library()

@register.filter
def format_currency(value):
    if value is None:
        return ''
    try:
        value = float(value)
        return '{:,.0f}'.format(value).replace(',', ' ')
    except (ValueError, TypeError):
        return value

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key."""
    if isinstance(dictionary, dict):
        try:
            return dictionary.get(key, key)
        except TypeError:  # unhashable key
            return key
    return key

_PENDING_CURRENCY_LABELS = (
    ('total_uzs', "so'm"),
    ('total_usd', '$'),
    ('total_rub', '₽'),
    ('total_eur', '€'),
)

@register.filter
def pending_summary(amounts):
    """Compact "60 000 so'm, 6 000 €" string of the non-zero currencies in
    `amounts` (a per-currency dict/model), or '' if every currency is zero."""
    if not amounts:
        return ''
    parts = []
    for key, label in _PENDING_CURRENCY_LABELS:
        value = amounts.get(key) if isinstance(amounts, dict) else getattr(amounts, key, None)
        if value:
            parts.append(f"{format_currency(value)} {label}")
    return ', '.join(parts)

@register.filter
def maqsad(report):
    """Purpose stored as desc = "Maqsad: <kind>[ — <comment>]"; returns the
    kind ('foyda', 'tushum', 'xarajat', 'chiqim') or '' when absent."""
    if not report or not getattr(report, 'desc', ''):
        return ''
    desc = report.desc
    if not desc.startswith('Maqsad:'):
        return ''
    rest = desc[len('Maqsad:'):].strip()
    return rest.split(' — ')[0]
