from .models import Notification


class EventType:
    GENERIC = 'GENERIC'
    OTP = 'OTP'
    ORDER_PLACED = 'ORDER_PLACED'
    PAYMENT_CONFIRMED = 'PAYMENT_CONFIRMED'
    WALKIN_RECEIPT = 'WALKIN_RECEIPT'
    ORDER_CANCELLED = 'ORDER_CANCELLED'
    DELIVERY_STATUS = 'DELIVERY_STATUS'
    PARCEL_STATUS = 'PARCEL_STATUS'
    PICKUP_READY = 'PICKUP_READY'
    PICKUP_REMINDER = 'PICKUP_REMINDER'
    COLLECTION_CONFIRMED = 'COLLECTION_CONFIRMED'
    DELIVERY_DISPUTE = 'DELIVERY_DISPUTE'
    LOW_STOCK = 'LOW_STOCK'
    TRANSFER = 'TRANSFER'
    VOID = 'VOID'
    SHIFT_VARIANCE = 'SHIFT_VARIANCE'


EVENT_CATALOG = {
    EventType.GENERIC: ('generic.sms', Notification.Criticality.INFORMATIONAL, False),
    EventType.OTP: ('security.otp', Notification.Criticality.CRITICAL, False),
    EventType.ORDER_PLACED: ('order.placed', Notification.Criticality.IMPORTANT, False),
    EventType.PAYMENT_CONFIRMED: ('payment.confirmed', Notification.Criticality.CRITICAL, True),
    EventType.WALKIN_RECEIPT: ('pos.receipt', Notification.Criticality.IMPORTANT, False),
    EventType.ORDER_CANCELLED: ('order.cancelled', Notification.Criticality.IMPORTANT, False),
    EventType.DELIVERY_STATUS: ('delivery.status', Notification.Criticality.IMPORTANT, False),
    EventType.PARCEL_STATUS: ('parcel.status', Notification.Criticality.IMPORTANT, False),
    EventType.PICKUP_READY: ('pickup.ready', Notification.Criticality.IMPORTANT, False),
    EventType.PICKUP_REMINDER: ('pickup.reminder', Notification.Criticality.IMPORTANT, False),
    EventType.COLLECTION_CONFIRMED: ('pickup.collected', Notification.Criticality.INFORMATIONAL, False),
    EventType.DELIVERY_DISPUTE: ('delivery.dispute', Notification.Criticality.CRITICAL, True),
    EventType.LOW_STOCK: ('inventory.low_stock', Notification.Criticality.IMPORTANT, False),
    EventType.TRANSFER: ('inventory.transfer', Notification.Criticality.IMPORTANT, False),
    EventType.VOID: ('pos.void', Notification.Criticality.CRITICAL, True),
    EventType.SHIFT_VARIANCE: ('shift.variance', Notification.Criticality.CRITICAL, True),
}
