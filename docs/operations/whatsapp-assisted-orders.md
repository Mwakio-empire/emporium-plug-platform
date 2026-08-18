# WhatsApp-assisted orders

## Supported workflow

The public WhatsApp button starts a conversation; it does not itself reserve stock, prove payment, or create an order. A signed-in S18 staff member records an agreed pickup using **Orders → Record WhatsApp pickup**.

1. Confirm the exact product or variant, quantity and current price in the business WhatsApp conversation.
2. Add those items to the storefront cart while signed in as staff.
3. Open the fulfilment workspace and select **Record WhatsApp pickup**.
4. Record the recipient name, normalized Kenyan phone, optional email, active pickup time and only necessary staff notes.
5. Reconfirm the basket total, S18 pickup location, cash-on-collection method and collection terms.
6. Submit once. The service atomically revalidates and reserves stock, locks item prices, creates an order/status history and records the staff member.
7. Send the private tracking link from the success page to the customer in the same conversation. Email also receives it when supplied.
8. Pack and collect the order through the ordinary fulfilment workspace. The pickup code and attempt controls remain unchanged.

## Boundaries

- The assisted flow is marked `WHATSAPP_ASSISTED`; website checkout and walk-in POS remain separately reportable.
- Assisted intake is limited to 20 attempts per staff account per hour and to the staff member's branch. Super administrators retain cross-branch oversight.
- It currently supports approved S18 cash-on-collection pickup only.
- A screenshot, forwarded payment message or typed M-Pesa reference is not proof of payment.
- Customers who want to prepay should use normal website M-Pesa checkout.
- Town parcel pricing and acceptance remain manual until the client approves the route, operator, collection point, fee, weight rule and expected travel time. Staff must not invent these values.
- Direct WhatsApp Cloud API ingestion is deferred; it requires Meta business setup, approved templates, consent/retention decisions, webhook security and provider monitoring.

## Manual acceptance test

1. Sign in as an S18 staff account and add an in-stock simple product to the storefront cart.
2. Open `/orders/assisted/whatsapp/` and verify the basket, total and S18 branch appear.
3. Submit without the confirmation checkbox; no order or stock reservation may be created.
4. Submit valid details and verify the success page shows an order number and private tracking link.
5. In admin or the fulfilment workspace, verify `sales_channel=WHATSAPP_ASSISTED`, `payment_method=COD`, `processed_by` is the signed-in staff member and stock is reserved once.
6. Open the tracking link in a private browser. It should display only that order.
7. Attempt the page as a customer and as staff assigned to another branch; both must be denied.
