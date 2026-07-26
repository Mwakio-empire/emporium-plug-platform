# POS shift lifecycle

```text
NO OPEN SHIFT
    |
    | cashier enters opening cash
    v
OPEN
    |
    | completed walk-in sales are linked to this shift
    | cash, Paybill and M-Pesa totals remain separate
    v
CLOSE REQUEST (cashier counts drawer)
    |
    | expected cash = opening cash + completed cash sales
    v
CLOSED + RECONCILIATION
    |                         |
    | variance <= KES 50      | variance > KES 50
    v                         v
NO MANAGER QUEUE          MANAGER REVIEW REQUIRED
                              |
                              | same-branch manager supplies reason
                              v
                         VERIFIED + AUDITED
```

Rules:

- One cashier can have only one open shift.
- New POS sales require the cashier's open shift at the same branch.
- A shift closes once; retries cannot create another reconciliation.
- Only completed sales linked to that shift affect its totals.
- Closed-shift sales are not voided through the normal POS void route.
