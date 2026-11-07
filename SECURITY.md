# Security policy

## Reporting a vulnerability

Do not open a public issue. Use GitHub's private vulnerability reporting
("Security" tab, "Report a vulnerability") on this repository. Include the affected component, steps
to reproduce and the impact. You will get an acknowledgement within a few days.

## Secrets

- Secrets live only in `.env` on the server (`chmod 600`). `.env` is git-ignored; `.env.example`
  contains no values.
- No AWS access keys are used. On EC2, the application uses the instance role through IMDSv2.
- API keys are shown once at creation and stored as SHA-256 hashes.
- `pre-commit install` enables gitleaks locally; CI runs gitleaks on the full history.

If a secret is ever committed: revoke or rotate it first, then remove it from history. Removing the
commit alone is not enough.

## Personal data

Sma3ni processes citizen voice notes and phone numbers. Contacts are encrypted at application level,
audio is deleted after the retention period, transcripts and contacts are never logged, and every read
of a request is recorded in `audit_log`. See section 12 of [docs/TECHNICAL.md](docs/TECHNICAL.md).
