# api/templates

[#api-templates](#api-templates)

Jinja2 HTML templates for outbound email, rendered by `api/utils/email_utils.py` and sent via SMTP.

## What's here

- **`sync_notification_template.html`** — sent when a document's Knowledge Base sync completes (or fails), letting the uploader know their document is searchable.
- **`share_llm_summary_template.html`** — sent when a user shares an agent's answer/summary with a teammate via email.

## Conventions

- Keep templates self-contained (inline CSS) — most email clients strip `<style>` blocks or external stylesheets.
- Use Jinja2 variables for anything domain-specific (agent name, document name, team name, sender name) rather than hardcoding "Document AI" — this is one of the first things to update when forking for a new vertical, since it's user-facing branding.
- Test rendered output in at least one real email client (Gmail web + Outlook, ideally) — HTML email rendering is inconsistent enough that "looks fine in the browser" isn't sufficient.
- If you add a new notification type, add its template here and its send function in `api/utils/email_utils.py`, following the existing naming pattern (`<event>_template.html`).
