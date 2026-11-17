from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, Field

# Twice the value must fit in JavaScript's exact integer range.
MAX_POINTS = 4503599627370495


def validate_points(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError('點數必須是數字')
    number = Decimal(str(value))
    if not number.is_finite() or abs(number) > MAX_POINTS or number * 2 != (number * 2).to_integral_value():
        raise ValueError('點數須以 0.5 為單位且在安全範圍內')
    return float(number)


Points = Annotated[float, BeforeValidator(validate_points), Field(ge=-MAX_POINTS, le=MAX_POINTS, multiple_of=0.5)]
