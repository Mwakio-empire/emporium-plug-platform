# Security incident and personal-data breach runbook

This is an operational starting point, not legal advice. The client must name owners and obtain qualified advice before launch.

## Immediate response

1. Open an incident record with discovery time, reporter, systems and suspected data affected.
2. Page the incident lead, technical lead, privacy contact and client decision-maker.
3. Preserve evidence: relevant immutable application logs, provider IDs, deployment revision and database/access logs. Do not paste secrets or full personal data into chat/tickets.
4. Contain using the smallest reversible action: revoke exposed credentials, disable an affected provider/endpoint, invalidate sessions/tokens, isolate a worker or restrict edge access.
5. Do not destroy evidence, mass-delete records, rotate every credential blindly or notify customers before scope/facts are reviewed.

## Assess

- What happened and is it ongoing?
- Which people/data categories/record counts and time range are affected?
- Were data encrypted/pseudonymised, accessed, altered, lost or made unavailable?
- What harm is reasonably possible and which groups are vulnerable?
- Which processor/controller systems and jurisdictions are involved?
- Are payments, stock, audit records or backups affected?

## Notify and communicate

- Escalate immediately; do not wait for complete certainty where statutory time limits may apply.
- The Kenya Data Protection Act includes a 72-hour notification requirement to the Data Commissioner where unauthorized access creates a real risk of harm. Qualified privacy/legal personnel must determine applicability and content.
- Processors must notify the controller without delay under their contractual/statutory obligations.
- Customer communication must be clear, factual, approved, provide protective steps/contact details and avoid exposing additional personal data.
- Record every notification decision, authority/customer contact and reason, including a decision not to notify.

## Recover and learn

1. Remove persistence/root cause, patch, test and deploy through the normal controlled process.
2. Validate payment/inventory/report integrity and restore only from verified backups if needed.
3. Increase focused monitoring and document recovery evidence.
4. Complete a blameless post-incident review: timeline, cause, impact, controls that failed, corrective owners/dates and client communication.
5. Update threat model, runbooks, tests, processor register and retention rules where necessary.

## Contacts to fill before launch

- Incident lead:
- Client executive decision-maker:
- Privacy contact/DPO:
- Hosting/database emergency support:
- Safaricom/Daraja support:
- Africa's Talking/WhatsApp support:
- External security adviser:
- Qualified Kenyan privacy/legal adviser:
