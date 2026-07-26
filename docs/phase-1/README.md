# Phase 1 — Domain and Data-Integrity Foundations

Status: implemented and locally verified on SQLite. PostgreSQL concurrency certification remains outstanding.

## Delivered

- Database constraints for non-negative order money, bounded discounts, valid order-item identity, valid stock identity, valid transfers, and non-negative M-Pesa amounts.
- One `OrderTransitionService` policy boundary that locks the order row, rejects invalid transitions, persists the new state, and writes status history atomically.
- Payment settlement, payment failure, POS completion/void, abandoned-order cancellation, pickup cancellation, delivery assignment, rider delivery updates, and pickup confirmation now use that policy.
- A delivery attempt marked `FAILED` no longer incorrectly terminates the order. The delivery assignment can be reassigned or returned as its own state machine specifies.
- Tests proving database enforcement and invalid order-transition rejection.

## Phase gate

Phase 1 is complete only when all of these pass:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py test
.\venv\Scripts\python.exe -m compileall apps config
.\venv\Scripts\python.exe -m pip check
```

See:

- [domain-model.md](domain-model.md)
- [state-machines.md](state-machines.md)
- [role-matrix.md](role-matrix.md)
- [constraints-and-concurrency.md](constraints-and-concurrency.md)

