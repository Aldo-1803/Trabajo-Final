import phonenumbers


DEFAULT_PHONE_REGION = 'AR'


class InvalidArgentinePhone(ValueError):
    pass


def normalize_argentine_phone(value):
    """Return a canonical E.164 Argentine number without changing display input."""
    if not isinstance(value, str):
        raise InvalidArgentinePhone('Debe informar un teléfono válido.')
    display_value = value.strip()
    if not display_value:
        raise InvalidArgentinePhone('Debe informar un teléfono válido.')
    try:
        parsed = phonenumbers.parse(display_value, DEFAULT_PHONE_REGION)
    except phonenumbers.NumberParseException as exc:
        raise InvalidArgentinePhone('Debe informar un teléfono argentino válido.') from exc
    if (
        parsed.country_code != 54
        or not phonenumbers.is_possible_number(parsed)
        or not phonenumbers.is_valid_number(parsed)
    ):
        raise InvalidArgentinePhone('Debe informar un teléfono argentino válido.')
    return phonenumbers.format_number(
        parsed,
        phonenumbers.PhoneNumberFormat.E164,
    )


def try_normalize_argentine_phone(value):
    try:
        return normalize_argentine_phone(value)
    except InvalidArgentinePhone:
        return None


def mask_email(email):
    if not email or '@' not in email:
        return None
    local, domain = email.split('@', 1)
    visible = local[:1]
    return f'{visible}{"*" * max(3, len(local) - 1)}@{domain}'


def mask_phone(phone):
    if not phone:
        return None
    return f'***{phone[-4:]}'
