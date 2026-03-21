# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it responsibly. **Do not open a public issue.**

Use [GitHub's private vulnerability reporting](https://github.com/pablocaeg/sloptotal/security/advisories/new) to submit a report.

We will acknowledge receipt within 48 hours and aim to provide a fix within 7 days for critical issues.

## Scope

The following are in scope for security reports:

- Backend API injection or authentication bypass
- Chrome extension permission escalation or data leakage
- Data exfiltration from submitted text
- Denial of service vectors
- Cross-site scripting (XSS) in the web frontend
- Insecure handling of user-submitted content

## Out of Scope

- AI detection accuracy (false positives/negatives are not security issues)
- Rate limiting bypass on the Cloudflare proxy (report to Cloudflare)
- Vulnerabilities in upstream dependencies (report to those projects directly)

## Design Principles

SlopTotal is designed with privacy as a core principle:

- All AI detection runs locally on your hardware
- No text is sent to third-party AI services
- No cookies or tracking scripts
- Reports are auto-deleted after 30 days
- The Chrome extension only communicates with your configured SlopTotal instance
