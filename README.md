# Local Shop Concierge

An AI-assisted front desk for local shops (salons, tutors, repair shops, clinics). A shop owner registers, pastes a price list, and gets a public page, a chat widget, lead capture and email alerts. Claude answers only from the shop's own data.

**Live site:** https://shopconcierge.online

**The full project is in [`shop_concierge_starter_kit/`](shop_concierge_starter_kit/).** Start with its [README](shop_concierge_starter_kit/README.md).

| Document | What it covers |
|---|---|
| [README](shop_concierge_starter_kit/README.md) | Problem, architecture, how Claude and GoDaddy are used, evidence |
| [DEMO](shop_concierge_starter_kit/DEMO.md) | Three-minute walkthrough |
| [SECURITY](shop_concierge_starter_kit/SECURITY.md) | Security review and accepted risks |
| [OPERATIONS](shop_concierge_starter_kit/OPERATIONS.md) | Running and maintaining the live site |
| [DECISIONS](shop_concierge_starter_kit/DECISIONS.md) | Design decisions and assumptions |

Built with Claude Code. Runs on a GoDaddy VPS with Docker, Caddy (HTTPS), FastAPI, SQLite and a Microsoft 365 mailbox on the domain.
