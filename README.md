# glideCast (Django)

## Local dev

Create a `.env` file (or set env vars):

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=1`
- `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1`
- `DATABASE_URL=postgres://...` (or omit for sqlite in dev)
- `APP_BASE_URL=http://localhost:8000`
- Stripe:
  - `STRIPE_SECRET_KEY`
  - `STRIPE_PUBLISHABLE_KEY`
  - `STRIPE_WEBHOOK_SECRET`
  - `STRIPE_PRICE_ID` (the $40/mo price)
  - `STRIPE_BILLING_PORTAL_RETURN_URL` (optional)

Run:

```bash
python3 -m pip install -r requirements.txt
python3 manage.py migrate
python3 manage.py createsuperuser
python3 manage.py runserver
```

## Stripe webhooks

Point Stripe at:

- `POST /billing/webhook/`

## Notes on the engine

Your original calculation code is kept untouched. Django uses `calculator/engine_loader.py` to load only the non-UI portion safely.

