OUT_OF_STOCK = 'OUT_OF_STOCK'
LOW_STOCK = 'LOW_STOCK'
IN_STOCK = 'IN_STOCK'


def public_stock_status(available_quantity, low_stock_threshold):
    """Return a customer-safe stock state without exposing an exact quantity."""
    available = max(int(available_quantity or 0), 0)
    threshold = max(int(low_stock_threshold or 0), 0)
    if available == 0:
        return OUT_OF_STOCK
    if available <= threshold:
        return LOW_STOCK
    return IN_STOCK


def public_stock_label(status):
    return {
        OUT_OF_STOCK: 'Out of stock',
        LOW_STOCK: 'Low stock - order soon',
        IN_STOCK: 'In stock',
    }[status]
