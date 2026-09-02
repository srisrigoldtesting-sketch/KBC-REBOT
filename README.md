# KBC REBOT — Telegram 4GB File Renamer Bot

A secure dual-client Pyrogram bot inspired by the MIT-licensed
[`JishuDeveloper/Rename-Bot-4GB`](https://github.com/JishuDeveloper/Rename-Bot-4GB).
The bot-token client handles commands and Telegram server-side message copies,
while a Telegram Premium MTProto session performs large-file transfers through a
private staging channel.

## Security first

Do not paste real tokens, session strings, or database passwords into source code, chat, commits, Docker images, or deployment logs. If a secret was exposed, rotate it before running this project.

## Setup

1. Create a private Telegram staging channel.
2. Add the bot as an admin with permission to post messages.
3. Add the Premium account represented by `STRING_SESSION` with permission to read and post.
4. Copy `.env.example` to `.env` and enter **newly rotated** credentials.
5. Create a Python 3.12 virtual environment and install `requirements.txt`.
6. Run `python -m app.main`.

## Usage

1. Send a document to the bot.
2. Reply to that document with `/rename New File Name.ext`.
3. Wait for the queued job to finish.

## Deployment

Use a persistent worker/container with at least 6–8 GB of free temporary disk for one concurrent 4 GB job. Keep `MAX_CONCURRENT_JOBS=1` unless storage and bandwidth are sized for more. Supply secrets using the host's secret manager, not Docker build arguments.

## Authentication documentation

See [`docs/AUTHENTICATION.md`](docs/AUTHENTICATION.md) for components, request flow, trust boundaries, credentials, and token handling.

## Required credential safety

- Bot token: generate a fresh token in BotFather and store it only as `BOT_TOKEN`.
- Telegram user session: Telegram → Settings → Devices → terminate the exposed session; generate a fresh string session privately.
- MongoDB: Atlas → Database Access → rotate/delete the exposed database user password; review Network Access and logs.
- API credentials: rotate the app credentials at `my.telegram.org` if possible; otherwise create a new app and stop using the exposed pair.

## GitHub

Create an empty private repository named `KBC-REBOT`, then run:

```bash
git init
git add .
git commit -m "Initial secure 4GB renamer bot"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/YOUR_REPO.git
git push -u origin main
```

Enable GitHub secret scanning and push protection. Keep the repository private until deployment and abuse controls are reviewed.
