# Persistent catalog-media runbook

Catalog product and gallery images use Cloudinary. Local filesystem media is
permitted only in development and tests. Staging and production refuse to start
without either `CLOUDINARY_URL` or all three individual Cloudinary credentials.

## Secret configuration

- Prefer the single client-owned `CLOUDINARY_URL` value in Render.
- Set the identical secret on web, worker and Beat. Never commit it or paste it
  into tickets, logs, screenshots or test evidence.
- Render prompts for service-level `sync: false` values only when a Blueprint is
  first created. Add or rotate the secret manually on existing services.
- Rotate the API secret immediately if it is exposed, then update all three
  services together and verify before removing the previous credential.

## Controlled verification

Run only against the intended Cloudinary product environment:

```powershell
python manage.py verify_cloudinary_media --confirm-remote-write
```

The command creates a uniquely named 1×1 synthetic PNG, requires HTTPS delivery,
caps the response body, and deletes the asset in a `finally`-style cleanup path.
It prints the cloud and delivery host but never credentials. A cleanup failure is
an operational incident: remove the tagged verification asset from Cloudinary's
Media Library and investigate before repeating the command.

On 2026-07-28 the configured client account passed upload, HTTPS delivery and
deletion; 68 bytes were delivered from `res.cloudinary.com`. The local catalog
contained no product or gallery images requiring migration.

## Staging acceptance

1. Upload a synthetic product image through the authorized staff interface.
2. Confirm the original and storefront renditions load over HTTPS and contain
   meaningful alt text.
3. Redeploy web, worker and Beat without changing the database.
4. Confirm the same image still renders and no local `/media/` path is required.
5. Replace the image and confirm the current record renders correctly. Review
   old-asset retention manually; do not bulk-delete by folder without an
   approved retention and rollback decision.
6. Record account usage/quota, transformation use, error evidence, revision,
   operator and timestamp.

Cloudinary availability, quota exhaustion or account suspension can make images
unavailable even while orders remain operational. Monitor provider status and
usage, keep original supplier images under the client's approved retention
policy, and define an export/migration procedure before provider lock-in becomes
material.
