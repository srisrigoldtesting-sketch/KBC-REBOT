# KBC REBOT — file renaming without Premium

**Default bot mode needs no Telegram Premium, user session, phone login or staging channel.** It uses your Telegram app API ID/hash and bot token over MTProto. Standard renaming returns a single file up to **2000 MiB**. For larger inputs already in Telegram, `/splitrename` returns smaller parts; `JOIN_PARTS.cmd` restores the complete renamed file locally.

Telegram limits normal uploads to its 2GB tier and Premium uploads to its 4GB tier. A session string does not grant Premium. This project cannot upload a single 4GB file from a non-Premium identity. Splitting changes the output into separate files; it does not raise that limit.

Inspired by [JishuDeveloper/Rename-Bot-4GB](https://github.com/JishuDeveloper/Rename-Bot-4GB). Original MIT attribution is preserved in LICENSE.

## Update an earlier installation

1. Stop the old START window with Ctrl+C and close the old CONFIGURE window.
2. Extract the updated ZIP into a new short folder, such as `C:\KBC-REBOT`. Do not run from inside the ZIP.
3. If you want to reuse private settings, copy your old `.env` into the new folder **locally only**. Do not upload it. The new ZIP contains no credentials.
4. Run **INSTALL.cmd**. In the settings window choose **Transfer mode: bot**. API_ID, API_HASH, BOT_TOKEN and ADMIN_ID are the required settings. Leave STRING_SESSION and STAGING_CHAT_ID blank; bot mode also ignores old invalid values in those two fields.
5. Leave DATABASE_URL blank for SQLite. FORCE_SUB_CHANNEL and LOG_CHANNEL_ID are optional; leave them blank if you do not use channels. Save, close settings, run **CHECK.cmd**, then **START.cmd**.

The installer finds Python 3.12/3.13 64-bit or attempts a user-only Python 3.13 install through Microsoft WinGet. It installs dependencies and runs offline tests. If WinGet is unavailable, it gives the official Python download link. No Docker, SSH, cloud account or administrator terminal is needed for bot mode.

## Rename a normal file

1. Open the bot in Telegram and send `/start`.
2. Send a small document, video or audio.
3. Reply to that message with `/rename New Name.ext`.
4. The bot downloads, renames and uploads the document directly, without a user session or staging channel.

Start with a small file to confirm your token and connection work. Free mode supports one returned file up to 2000 MiB (2,097,152,000 bytes). Use a short Windows-safe filename. Files are returned as documents; content is not transcoded.

## Handle larger files without Premium

**If the original large file is already in Telegram:** forward it to your bot, provided forwarding is allowed. Reply `/splitrename New Name.ext`. The bot accepts input up to 4000 MiB (4,194,304,000 bytes), downloads it and returns parts of at most 2000 MiB plus a small `.kbc-parts.json` manifest. For a maximum-size input there are two parts. Smaller files sent to `/splitrename` can still return as one file if they fit the selected account's limit.

Download **all parts and the manifest into the same folder**, keeping their original filenames. Run **JOIN_PARTS.cmd**, select the manifest, and wait. The tool checks part sizes and SHA-256 checksums and produces the complete file with the requested name. Parts are plain binary pieces, not independently playable videos and not ZIP archives. The joiner preserves the parts and refuses to overwrite an existing output file. Checksums detect corruption; they do not authenticate who supplied a manifest.

**If the large file exists only on your laptop:** a free Telegram account cannot initially upload it as one 4GB file. Run **SPLIT_LOCAL.cmd**, select the file, and enter the desired final filename. It creates a new folder with parts and a manifest beside the original. Send those files through Telegram separately. The recipient joins them with JOIN_PARTS. The original local file is preserved. This route is local splitting and renaming, not a single-file 4GB Telegram upload.

Do not mix parts from different attempts. If a job fails or is cancelled after some parts arrive, discard that incomplete set and retry. Only a completed set with the final manifest can be reliably joined. Receiving a manifest is not a substitute for checksum verification.

## Optional user sessions

Most users should keep `TRANSFER_MODE=bot`. **GENERATE_SESSION.cmd is optional.** It now accepts both normal and Premium Telegram user accounts.

To use a user identity, save API_ID/API_HASH in CONFIGURE, close that window, and run GENERATE_SESSION. Enter your own phone number, login code and optional two-step password only in that local console. Hidden typing is normal. The session is written directly into the private `.env`, never printed or sent to a chat. A standard session allows 2000 MiB uploads; an account with active Premium allows 4000 MiB.

Then choose `TRANSFER_MODE=user`, set STAGING_CHAT_ID to a private broadcast channel, and add both identities as admins with Post Messages and Delete Messages permissions. Turn off protected content there. CHECK validates permissions. Generating a session does not automatically change transfer mode or subscribe your account to Premium.

## Settings

| Variable | Purpose |
|---|---|
| `API_ID`, `API_HASH` | Your app credentials from [my.telegram.org](https://my.telegram.org) |
| `BOT_TOKEN` | One fresh bot token from BotFather; no angle brackets or duplicate copies |
| `ADMIN_ID` | Your numeric Telegram ID; only `/admin` is restricted to it |
| `TRANSFER_MODE` | `bot` by default; optional `user` mode enables the second identity |
| `STRING_SESSION` | Used only in user mode; normal and Premium user sessions accepted |
| `STAGING_CHAT_ID` | Required only in user mode; private broadcast channel shared by both identities |
| `FORCE_SUB_CHANNEL` | Optional channel/group users must join; bot must be admin. A bot username is not a subscription channel. |
| `LOG_CHANNEL_ID` | Optional destination for job IDs and error classes |
| `DATABASE_URL` | Blank uses local SQLite; optional MongoDB URI |
| `DATABASE_NAME` | MongoDB name, default `cluster0` |
| `WORK_DIR` | Data folder, default `data` beside the code |
| `START_PIC` | Optional welcome image; text fallback if it fails |
| `MAX_CONCURRENT_JOBS` | `1` in the laptop edition |

Runtime environment variables override the private `.env`. GitHub secrets are not automatically copied to a laptop. Old `ADMIN`, `FORCE_SUBS` and `LOG_CHANNEL` aliases work when their newer names are absent. No built-in secret values are supplied. Replace previously disclosed bot tokens and revoke exposed Telegram sessions; rotate an exposed MongoDB password if still using that database. Never paste replacements into chat or public source files.

## Running and storage

Use Windows 10/11 x64 with Python 3.12/3.13, pip and tkinter. Keep about 3 GiB free for standard 2GB renaming. A maximum-size split job needs about 7 GiB free while downloading and creating one part at a time; 10 GiB is recommended. Local splitting needs free space for another full copy plus a reserve, and joining needs space for the restored file. Disk capacity is checked before processing; other programs can still consume free space afterward.

Keep the laptop powered, connected to the internet and START open. The running bot temporarily prevents idle sleep; manual sleep, lid closure, power loss or shutdown still interrupt service. Run START again after a reboot. Local hosting has no hosting subscription; electricity/internet are separate costs. Premium is optional and only needed for a single returned file above the normal account limit.

One job per user, one active transfer, and at most ten waiting jobs. `/status` shows queue counts, `/cancel` stops your own job, and `/admin` shows metadata counts for ADMIN_ID. Anyone who can reach the bot may use it, subject to optional subscription checking; ADMIN_ID does not make all commands owner-only.

Temporary files are cleaned up after completion, exceptions and cooperative cancellation. User-mode staging messages are deleted where possible. Network failure, forced termination or lost channel rights may leave messages for the channel owner to remove. The app removes old temporary job folders at the next start; do not put personal files in `data/jobs`. The in-memory queue is not resumed after a restart. Metadata stays in SQLite/MongoDB until removed. `/cancel` does not retract files already delivered.

## Verification and development

Run `python -m unittest discover -s tests -v`. Tests cover bot-only transfers, normal/Premium account limits, standard session generation, split/join byte integrity, corruption detection, filename safety, overwrite prevention, Windows cleanup on cancellation, and queue recovery. GitHub Actions runs Linux and Windows with Python 3.12/3.13 and checks Windows installation/settings startup. Telegram clients are mocked in transfer tests: only a live CHECK and file trial on your host can confirm your account and network work together.

For Linux/Docker, supply the same settings at runtime and run `python -m app.main`; desktop split/join dialogs are intended for Windows. `.env` is excluded from the Docker context. The code uses Telegram MTProto directly, so the hosted HTTP Bot API's media limits are not the interface used here.

Read [START_HERE_TE.md](START_HERE_TE.md) for Telugu steps and [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md) for code-level details.

## Primary references

- [Telegram FAQ: normal 2GB and Premium 4GB file tiers](https://telegram.org/faq).
- [Telegram Premium FAQ: everyone can download Premium-uploaded files](https://telegram.org/faq_premium).
- [Pyrofork 2.3.69 upload implementation: 2000/4000 MiB](https://github.com/Mayuri-Chan/pyrofork/blob/v2.3.69/pyrogram/methods/advanced/save_file.py).
- [Pyrofork package](https://pypi.org/project/pyrofork/2.3.69/) and [Windows crypto wheels](https://pypi.org/project/TgCrypto-pyrofork/1.2.8/).
- [Microsoft WinGet options](https://learn.microsoft.com/en-us/windows/package-manager/winget/install).
