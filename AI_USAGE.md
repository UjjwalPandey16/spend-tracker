# AI usage

I used Codex to draft the FastAPI/SQLite API, minimal UI, tests, documentation, and a separate Cloudflare deployment adapter. I reviewed the database records directly and checked the month-over-month calculation and category alert against sample expenses.
I chose Cloudflare Workers with D1 for the free public demo, then verified the hosted UI and API with sample data. I kept the tested SQLite implementation on `main` and the deployment code on a local branch; I deferred authentication, a gateway, and an ORM because they would add complexity to this single-user task.
