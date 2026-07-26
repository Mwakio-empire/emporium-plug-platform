# Dynamic Retail System

Commercial Django retail platform for a multi-branch Kenyan retailer. The current codebase covers a customer storefront, branch inventory, POS sales, online orders, M-Pesa integration, delivery/pickup operations, notifications, reconciliation, and reporting.

The project is under active development. A passing automated suite does not mean the system is approved for live payments or production use. Use the [current traceability matrix](docs/phase-15/requirements-traceability.md), [known limitations](docs/phase-15/known-limitations.md) and [release checklist](docs/phase-15/release-checklist.md) for current status; Phase 0 and later phase records are dated implementation evidence.

## Local setup

1. Install Python 3.13+ and Node.js. This release was locally verified with Python 3.14.3 and Node 24.14.0.
2. Create and activate a virtual environment:

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   ```

3. Install locked Python and frontend dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   npm.cmd ci
   npm.cmd run build
   ```

4. Create local configuration and replace only development values. Never commit credentials:

   ```powershell
   Copy-Item .env.example .env
   ```

5. Apply migrations:

   ```powershell
   python manage.py migrate
   ```

6. Start the development server:

   ```powershell
   python manage.py runserver
   ```

Redis and Celery are needed for development flows that enqueue background work. For isolated UI work, `LOCAL_CACHE_ONLY=True` uses in-memory cache/broker settings; the application rejects that flag outside development/test. Ordinary automated tests do not require Redis.

For full asynchronous local operation, start Redis, then run worker and scheduler in separate terminals:

```powershell
celery -A config worker --loglevel=INFO --pool=solo
celery -A config beat --loglevel=INFO
```

Run exactly one Beat scheduler. Development data must be synthetic and provider settings must remain sandbox/console-safe.

## Verification

Run these before proposing a change:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python -m compileall -q apps config
python -m pip check
npm.cmd run build
npm.cmd audit
```

## Safety boundaries

- Automated tests must not call live Daraja, Africa's Talking, WhatsApp, Cloudinary, or AWS endpoints.
- Do not use real customer information in development or tests.
- Production payment activation requires explicit client authorization and controlled verification.
- The PostgreSQL-native backup procedure is not disaster recovery until managed PITR and a controlled restore are proven on the selected host.

## Documentation

- [Phase 0 audit, traceability and defect register](docs/phase-0/README.md)
- [Phase 1 domain and data-integrity foundation](docs/phase-1/README.md)
- [Phase 1.5 inventory semantics](docs/phase-1-5/README.md)
- [Phase 2 identity, authentication and authorization](docs/phase-2/README.md)
- [Phase 3 catalog and storefront](docs/phase-3/README.md)
- [Phase 4 checkout](docs/phase-4/README.md)
- [Phase 5 M-Pesa and cash payments](docs/phase-5/README.md)
- [Phase 6 POS and staff accountability](docs/phase-6/README.md)
- [Phase 7 inventory operations and transfers](docs/phase-7/README.md)
- [Phase 8 order fulfilment](docs/phase-8/README.md)
- [Phase 9 promotions, reviews and returns](docs/phase-9/README.md)
- [Phase 10 reports and client operations](docs/phase-10/README.md)
- [Phase 11 durable notifications](docs/phase-11/README.md)
- [Phase 12 security and privacy](docs/phase-12/README.md)
- [Phase 13 production engineering](docs/phase-13/README.md)
- [Phase 14 testing strategy](docs/phase-14/README.md)
- [Phase 15 client and engineering handover](docs/phase-15/README.md)
- [Known limitations](docs/phase-15/known-limitations.md)
- [Release checklist](docs/phase-15/release-checklist.md)
- [Business context](C:/Users/hp/Desktop/Business%20ContextDNT.docx) is an external local source document and is not stored in this repository.
