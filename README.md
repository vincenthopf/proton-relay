# Proton Relay

Forward emails from ProtonMail to another email provider via IMAP/SMTP. Useful for migration or backup.

Uses [hydroxide](https://github.com/emersion/hydroxide) as a local ProtonMail bridge, with automatic authentication handling.

## Features

- Forward incoming ProtonMail emails to any SMTP destination
- Telegram alerts for errors (CAPTCHA, auth failures, rate limits)
- Health check endpoints for monitoring
- Multi-account support with isolated instances
- Browser-in-browser for CAPTCHA clearing from server IP

## Quick Start (Single Account)

```bash
# Clone
git clone https://github.com/vincenthopf/proton-relay.git
cd proton-relay

# Configure
cp .env.example .env
# Edit .env with your credentials

# Run
docker compose up -d

# Check status
docker compose logs -f forwarder
```

## Multi-Account Deployment (4 Accounts)

```bash
cd deploy

# Create instances with staggered intervals
./setup-all.sh

# Configure each instance
cp instances/proton1/.env.example instances/proton1/.env
# Edit .env for each: proton1, proton2, proton3, proton4

# Start with auth delays (first time)
./start-all.sh

# Future restarts (no delay needed)
./start-all.sh --no-delay
```

### Management Commands

| Command | Description |
|---------|-------------|
| `./status.sh` | Health dashboard for all instances |
| `./logs.sh proton1` | Tail logs for specific instance |
| `./stop-all.sh` | Stop all instances |
| `instances/proton1/captcha.sh start` | Launch browser for CAPTCHA (port 5801) |

### Daily Monitoring (4-month migration)

```bash
# Add to crontab for daily Telegram report
crontab -e
0 9 * * * /path/to/deploy/daily-report.sh
```

## Configuration

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `PROTONMAIL_USERNAME` | Your ProtonMail email |
| `PROTONMAIL_PASSWORD` | Your ProtonMail password |
| `SMTP_HOST` | Destination SMTP server |
| `SMTP_PORT` | SMTP port (usually 587) |
| `SMTP_USERNAME` | SMTP login |
| `SMTP_PASSWORD` | SMTP password/app password |
| `FORWARD_TO` | Destination email address |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `CHECK_INTERVAL` | 30 | Seconds between inbox checks |
| `TELEGRAM_BOT_TOKEN` | - | For error alerts |
| `TELEGRAM_CHAT_ID` | - | Telegram chat for alerts |
| `LOG_LEVEL` | INFO | DEBUG, INFO, WARNING, ERROR |

## CAPTCHA Clearing

When ProtonMail requires CAPTCHA verification:

```bash
# Single instance
docker compose --profile captcha up -d captcha-browser
# Open http://your-server:5800

# Multi-instance (proton1)
cd deploy/instances/proton1
./captcha.sh start
# Open http://your-server:5801
```

Log into ProtonMail, complete CAPTCHA, then stop the browser.

## Updating Hydroxide

Hydroxide is pinned to a known-good commit. To update:

```bash
# Rebuild with latest
docker compose build --build-arg HYDROXIDE_VERSION=master hydroxide

# Or pin to specific commit
docker compose build --build-arg HYDROXIDE_VERSION=abc1234 hydroxide
```

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   ProtonMail    │────▶│   Hydroxide  │────▶│    Forwarder    │
│   (remote)      │     │   (bridge)   │     │   (IMAP→SMTP)   │
└─────────────────┘     └──────────────┘     └────────┬────────┘
                                                      │
                              ┌────────────────────────┤
                              ▼                        ▼
                        ┌──────────┐           ┌─────────────┐
                        │ Telegram │           │ Destination │
                        │ (alerts) │           │   (SMTP)    │
                        └──────────┘           └─────────────┘
```

## License

MIT
