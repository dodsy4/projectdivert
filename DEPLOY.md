# Deploy Project Divert

## 1. Prerequisites
- Managed Postgres database
- Google Maps API key
- SendGrid account (or compatible email provider)
- Domain name (optional but recommended)

## 2. Environment Variables
Copy `.env.example` values into your host's environment settings.

Required minimum:
- `SECRET_KEY`
- `DATABASE_URL`
- `GOOGLE_MAPS_API_KEY`

For auth + request-notification emails:
- `MAIL_PROVIDER`
- `MAIL_FROM_EMAIL`
- `SENDGRID_API_KEY`
- `REQUEST_NOTIFICATION_EMAIL`

## 3. Deploy (Render)
Option A: use `render.yaml` Blueprint deploy.
Option B: create a Web Service manually with:
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`

## 4. Database Migration
After first deploy, run:
- `flask db upgrade`

## 5. Verify Production
- Home page loads (`/`)
- Materials list + map render
- Register/login/logout works
- Material request submits
- Request email notification arrives at `REQUEST_NOTIFICATION_EMAIL`

## 6. Security Checklist
- `FLASK_DEBUG=0`
- `SESSION_COOKIE_SECURE=1`
- Rotate `SECRET_KEY` and API keys
- Enable HTTPS custom domain
- Enable DB backups on your provider

## 7. Next Improvements
- Add password reset and email verification
- Add rate limiting / anti-spam on request forms
- Move image storage to S3/Cloudinary for durability
