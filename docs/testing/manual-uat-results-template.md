# Manual UAT results

## Test cycle

| Field | Value |
|---|---|
| Environment | Local / Staging / Migration rehearsal |
| Build or commit | |
| Test start/end (Africa/Nairobi) | |
| Lead tester | |
| Business approver | |
| Browser/device | |
| Database snapshot/backup reference | |
| Synthetic dataset reference | |

## Results

| Case ID | Tester/role/branch | Expected | Actual | Reference and before/after totals | Evidence path | Result | Defect ID | Retest |
|---|---|---|---|---|---|---|---|---|
| UAT-EXAMPLE-01 | | | | | | Not Run | | |

Allowed results: `Pass`, `Fail`, `Blocked`, `Not Applicable`, `Not Run`.

## Defects

| Defect ID | Severity | Business/security impact | Reproduction | Expected/actual | Evidence | Owner | State | Retest evidence |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |

Severity definitions:

- **Critical:** financial/data corruption, privilege bypass, secret exposure,
  unrecoverable outage or unsafe payment/stock behavior.
- **High:** critical journey unavailable or materially wrong with no safe
  workaround.
- **Medium:** incorrect secondary behavior with a controlled workaround.
- **Low:** cosmetic or minor usability/documentation problem.

## Reconciliation summary

| Area | Expected | Actual | Difference | Evidence | Accepted by |
|---|---:|---:|---:|---|---|
| S18 stock | | | | | |
| B03 stock | | | | | |
| OTC stock | | | | | |
| Recognized revenue | | | | | |
| Cash/shift total | | | | | |
| M-Pesa total | | | | | |
| Discounts | | | | | |
| Voids/reversals | | | | | |
| Returns/refunds pending | | | | | |

## Exit decision

- [ ] All planned cases have a final result.
- [ ] No Critical or High defect remains open.
- [ ] Money, stock, shifts and reports reconcile.
- [ ] PostgreSQL concurrency cases pass.
- [ ] M-Pesa sandbox certification passes.
- [ ] Backup and restore pass.
- [ ] Monitoring and alerts are proven.
- [ ] Privacy/legal/provider decisions are approved.
- [ ] Client accepts documented limitations.

Decision: `GO` / `NO-GO`

Business approver/name/date:  
Technical approver/name/date:  
Notes and accepted limitations:

