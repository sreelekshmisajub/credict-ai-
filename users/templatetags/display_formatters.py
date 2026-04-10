from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()

def _coerce_decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None

def _indian_grouping(number_string):
    if len(number_string) <= 3:
        return number_string
    last_three = number_string[-3:]
    leading = number_string[:-3]
    groups = []
    while len(leading) > 2:
        groups.insert(0, leading[-2:])
        leading = leading[:-2]
    if leading:
        groups.insert(0, leading)
    groups.append(last_three)
    return ",".join(groups)

@register.filter
def inr_currency(value):
    amount = _coerce_decimal(value)
    if amount is None:
        return value
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    decimals = 0 if amount == amount.quantize(Decimal("1")) else 2
    formatted = f"{amount:.{decimals}f}"
    if "." in formatted:
        whole, fraction = formatted.split(".", 1)
    else:
        whole, fraction = formatted, ""
    grouped = _indian_grouping(whole)
    if decimals:
        return f"{sign}\u20b9{grouped}.{fraction}"
    return f"{sign}\u20b9{grouped}"

@register.filter(name='replace')
def replace(value, arg):
    """
    Replaces a string with another string.
    Usage: {{ value|replace:"search_string" }} -> replaces with space
    Usage: {{ value|replace:"search:replace" }} -> replaces search with replace
    """
    if not isinstance(value, str):
        value = str(value)
    
    if ":" in arg:
        search, replacement = arg.split(":", 1)
        return value.replace(search, replacement)
    
    return value.replace(arg, " ")

@register.filter(name='multiply')
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0
