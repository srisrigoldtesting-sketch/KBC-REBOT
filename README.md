# KBC REBOT — Windows 4GB file renamer

A Telegram bot with a separate Premium user client for large-file transfers. Inspired by [JishuDeveloper/Rename-Bot-4GB](https://github.com/JishuDeveloper/Rename-Bot-4GB); the original MIT attribution is preserved in LICENSE.

## Start on your Windows laptop

1. Extract the ZIP to a short writable folder, for example `C:\KBC-REBOT`. Do not run files from inside the ZIP.
2. Double-click **INSTALL.cmd**. It finds Python 3.12/3.13 64-bit or installs Python 3.13 for your user through Microsoft WinGet, installs the pinned dependencies, and runs the offline tests. No Docker, SSH, rented VM or administrator terminal is required. If WinGet is unavailable, the script gives the official Python download link.
3. The local settings window opens. Enter the credentials there and press **Save settings**. Save partial settings if necessary; reopen **CONFIGURE.cmd** later. Credentials are stored in the private `.env` beside the scripts.
4. If you need a new Premium session, save your API ID/hash, close the settings window, then run **GENERATE_SESSION.cmd**. Enter your own phone number, login code and two-step verification password only in that local console. The session is saved directly; it is never printed or sent to a chat.
5. In Telegram, create a **private broadcast channel**, add the bot and Premium user account as admins, and allow **Post Messages** and **Delete Messages** for both. Turn off protected content for that staging channel. Save its `-100...` ID as `STAGING_CHAT_ID`. The prefilled ID is from your configuration and still needs to belong to the channel you control.
6. Stop any existing copy of the bot, then run **CHECK.cmd**. It checks configuration, disk, database, bot login, Premium status and channel permissions without uploading test files.
7. Run **START.cmd**. When the console says the bot is running, open the bot in Telegram, send `/start`, send a small document, and reply `/rename My New Name.pdf`. After that succeeds, test a larger file.

Keep the laptop connected to power and the internet, with START open. Automatic idle sleep is prevented while START runs and restored when it exits; closing the lid or manually sleeping/shutting down still stops service. Press Ctrl+C to stop cleanly. Run START again after a reboot. This is local hosting with no hosting subscription; electricity, internet and Telegram Premium are separate costs. No cloud provider or uptime is promised.

See [START_HERE_TE.md](START_HERE_TE.md) for Telugu instructions.

## Requirements and file limits

- Windows 10/11 x64; Python 3.12 or 3.13 with pip and tkinter.
- An existing Telegram bot and an account with **active Telegram Premium** for the transfer client.
- At least 5 GiB free on the data drive; 10 GiB free and 4 GB system RAM are practical starting points. Other apps and network conditions affect performance.
- This pinned library supports up to **4000 MiB (4,194,304,000 bytes)** for Premium uploads. This is Telegram's advertised 4GB tier, not an exact 4 GiB file (4,294,967,296 bytes). Larger files are rejected before downloading.
- Transfers stream to disk. Files return as documents; contents are not transcoded. Documents, videos and audio are accepted.

## Settings

| Variable | Purpose |
|---|---|
| `API_ID`, `API_HASH` | Telegram app credentials from your account at [my.telegram.org](https://my.telegram.org) |
| `BOT_TOKEN` | One fresh token from BotFather, no angle brackets or duplicated copies |
| `ADMIN_ID` | Your numeric Telegram ID; restricts `/admin` |
| `STRING_SESSION` | A production Pyrogram/Pyrofork user session with active Premium |
| `STAGING_CHAT_ID` | Private broadcast channel shared by both clients |
| `FORCE_SUB_CHANNEL` | Optional channel/group users must join; bot must be an admin there. Blank disables it. A bot username cannot be used as a subscription channel. |
| `LOG_CHANNEL_ID` | Optional destination for error classes and job IDs; blank disables it |
| `DATABASE_URL` | Optional MongoDB URI; **blank uses free local SQLite** |
| `DATABASE_NAME` | Mongo database name, default `cluster0` |
| `WORK_DIR` | Data location, default `data` beside the code |
| `START_PIC` | Optional welcome image; bot falls back to text if it fails |
| `MAX_CONCURRENT_JOBS` | `1` for the laptop edition |

Legacy `ADMIN`, `FORCE_SUBS`, and `LOG_CHANNEL` are accepted when their newer names are absent. Runtime environment variables override `.env`; the local settings window edits the file only. GitHub Actions secrets are not automatically available on your laptop. Never commit `.env` to GitHub or include it in a ZIP you share.

The supplied example includes only non-secret IDs/settings. Join checking starts disabled because the previously supplied username has not been verified as a channel. If you want it, set a real channel and CHECK will validate access. The database URI starts blank so SQLite works without an external service.

The earlier credentials were disclosed in chat. Replace the bot token through BotFather, terminate the exposed Telegram user session under Settings > Devices, and generate a new session locally. Rotate the disclosed MongoDB password if that database is still in use. Do not paste replacements into chat.

## Commands and behavior

- `/start` or `/help`: usage instructions.
- `/rename New Name.ext`: reply to a document, video or audio.
- `/status`: your job ID and queue counts.
- `/cancel`: cancel your queued/active job.
- `/admin`: metadata counts, only for `ADMIN_ID`.

One job per user, one active transfer and at most ten waiting jobs. Each job has its own temporary directory so identical names cannot collide. The worker re-fetches the staged source with the Premium identity, checks downloaded size, and copies the result back using the bot. Telegram rate limits get bounded retries; a transfer, notification or metadata failure does not intentionally stop the queue.

Temporary files and the two staging messages are cleaned up after each job where possible. A power cut, forced process termination, lost connection or revoked delete permission can leave staging messages; the channel owner should remove those. Interrupted local job directories are removed at the next start. Job metadata (user IDs, filenames, status, timestamps and error class) stays in SQLite/MongoDB until you remove it. The queue is not durable: after a restart, resend interrupted jobs. `/cancel` cannot retract a file already delivered.

Any Telegram user who can reach the bot may use `/rename` (subject to optional join checking). `ADMIN_ID` only restricts `/admin`. Do not publish the bot widely unless your laptop bandwidth and disk can support that usage.

## Troubleshooting

| Message/problem | Action |
|---|---|
| Missing or malformed setting | Open CONFIGURE, paste each value once, save and run CHECK |
| Premium/session error | Stop other copies; use an active Premium account and generate a fresh session locally |
| Channel/private/peer error | Correct the channel ID; both accounts must join and have the required admin permissions |
| Membership check fails | Use a real channel/group, make the bot admin, or leave FORCE_SUB_CHANNEL blank |
| MongoDB unavailable | Check URI/network access, or leave DATABASE_URL blank for SQLite |
| Already running | Stop the old START window; do not launch concurrent copies with the same session |
| Network interruption/FloodWait | Restore the connection, allow Telegram's rate limit to expire, and retry |
| No disk space | Free space on the WORK_DIR drive; do not put your own documents in data/jobs |
| Filename rejected | Use a short filename without Windows reserved names, slashes or forbidden symbols |

## Developers

`python -m unittest discover -s tests -v` runs credential-free tests using fake Telegram clients and real local SQLite. GitHub Actions is configured for Linux and Windows, Python 3.12 and 3.13, with a Windows launcher/settings smoke test. These tests do not prove a live 4GB transfer or validate your account credentials; CHECK and the real small/large file trial are required on the host.

For Linux/Docker, provide settings as environment variables (or a private local `.env` when running Python directly) and run `python -m app.main`. The Docker image does not contain `.env`; use `docker run --env-file .env ...` with persistent storage if needed. The Windows launchers are the intended route for this package.

Read [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md) for the code-level authentication and request flow.

## Dependency references

- [Pyrofork 2.3.69](https://pypi.org/project/pyrofork/2.3.69/) and [its upload implementation](https://github.com/Mayuri-Chan/pyrofork/blob/v2.3.69/pyrogram/methods/advanced/save_file.py). Imports retain the `pyrogram` name; the original Pyrogram project is archived.
- [TgCrypto-pyrofork Windows wheels](https://pypi.org/project/TgCrypto-pyrofork/1.2.8/).
- [Telegram file transfer limits](https://core.telegram.org/api/files).
- [Microsoft WinGet installation options](https://learn.microsoft.com/en-us/windows/package-manager/winget/install).
