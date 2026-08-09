from catalog.models import ProductOption
from catalog.templatetags.catalog_extras import storefront_image_url


def _media_entry(image, alt_text):
    if not image:
        return None
    large_url = storefront_image_url(image, 960)
    if not large_url:
        return None
    return {
        'url': large_url,
        'thumbnail': storefront_image_url(image, 192),
        'alt': alt_text or 'Product image',
    }


def _deduplicate(entries):
    seen = set()
    result = []
    for entry in entries:
        if not entry or entry['url'] in seen:
            continue
        seen.add(entry['url'])
        result.append(entry)
    return result


def product_media(product):
    entries = [_media_entry(product.image, product.name)]
    entries.extend(
        _media_entry(image.image, image.alt_text)
        for image in product.gallery_images.all()
    )
    return _deduplicate(entries)


def variant_media(variant, fallback_media):
    """Resolve exact-variant media, then colour media, then product media."""
    exact = _media_entry(variant.image, f'{variant.product.name} — {variant.option_summary}')
    colour_entries = []
    for assignment in variant.option_assignments.all():
        if assignment.option.display_type != ProductOption.DisplayType.COLOUR:
            continue
        colour_entries.extend(
            _media_entry(image.image, image.alt_text)
            for image in assignment.value.images.all()
        )
        break

    if exact:
        return _deduplicate([exact, *colour_entries])
    if colour_entries:
        return _deduplicate(colour_entries)
    return list(fallback_media)
