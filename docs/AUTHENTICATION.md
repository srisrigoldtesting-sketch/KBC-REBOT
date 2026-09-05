# Authentication and request flow

## Components

| Component | Code | Role |
|---|---|---|
| Configuration | `app/config.py`, `app/configure.py` | Root `.env` followed by environment overrides; validated formats, masked inputs, no secret values in Settings repr |
| Bot identity | `app/clients.py:build_clients`, `connect_client` | API_ID/API_HASH plus BOT_TOKEN; explicit bot sign-in, in-memory storage |
| Optional user identity | `app/clients.py` | Enabled only by TRANSFER_MODE=user; STRING_SESSION authenticates a normal or Premium user |
| User session generation | `app/generate_session.py` | Local phone/code/optional two-step verification; exports directly to `.env`; Premium is not required |
| Request authorization | `app/handlers.py`, `app/security.py` | Telegram sender ID, optional join check, exact ADMIN_ID restriction on `/admin` |
| File transfers | `app/worker.py` | Bot directly handles default mode; optional user mode uses a private staging channel |
| Multipart files | `app/parts.py`, `app/parts_tool.py` | Streamed splitting and local checksum-verified joining; no Telegram authorization needed for local tools |
| Metadata | `app/database.py` | SQLite by default, optional MongoDB URI authentication |
| Process lock | `app/runlock.py` | Prevents simultaneous START/CHECK/session operations in one installation |

## Startup and permissions

`Settings.load()` reads `.env` without dotenv interpolation and then applies runtime environment overrides. `TRANSFER_MODE` defaults to `bot`. In that mode STRING_SESSION and STAGING_CHAT_ID are ignored, including invalid values left in an older `.env`. Optional subscription/log channels remain independent features.

`connect_client()` connects and explicitly signs in the bot with BOT_TOKEN. Bot mode creates no user client, asks for no phone login and performs no staging-channel checks. User mode additionally authenticates an existing user session and verifies that both identities can post and delete in a private broadcast staging channel. The generator accepts existing standard and Premium user accounts; it never creates a new account or purchases Premium.

`upload_limit_bytes()` reads the authenticated identity returned by Telegram. A bot or standard user gets a 2000 MiB single-file limit; a user whose live `is_premium` is true gets 4000 MiB. No environment flag, edited session string or made-up size attribute grants Premium. The same limits are enforced by the pinned Pyrofork upload code and Telegram.

There is no inbound web server, webhook login, OAuth refresh token, JWT or browser authentication in this application. Connections are outgoing Telegram MTProto connections. Desktop local split/join tools perform no Telegram calls.

## Default bot request flow

1. The user sends/forwards a document, video or audio and replies `/rename New Name.ext` or `/splitrename New Name.ext`.
2. Telegram supplies the authenticated sender ID. The handler checks optional subscription membership and validates the target filename. The worker checks size, per-user duplication and queue capacity.
3. Ordinary `/rename` rejects files above the identity's upload limit before downloading and explains the multipart command. `/splitrename` explicitly permits larger inputs, up to 4000 MiB total. A normal command is never silently converted into parts.
4. The bot fetches the source using its own `get_messages` and downloads into an isolated temporary job directory. No channel is needed and no account-scoped file ID is passed between identities.
5. After verifying the downloaded size, the worker renames locally and uses the bot to upload directly to the requesting chat. The output is a document with unchanged bytes.
6. For multipart output, the worker reads bounded chunks into one part file at a time, uploads each file within the normal limit, and removes the temporary part before making the next. Finally it sends a JSON manifest with filenames, byte sizes and SHA-256 checksums. Partial output does not constitute a complete joined file.
7. The recipient downloads every part plus the manifest and uses JOIN_PARTS locally. The joiner validates the manifest, rejects path traversal, checks sizes/checksums and refuses to overwrite an existing destination. It removes an incomplete joined output on errors; downloaded parts remain.

## Optional user request flow

The bot copies the input to the private staging channel. The user client fetches that message with its own identity before downloading, because file references are account-bound. The user uploads the result or individual parts/manifest into staging, then the bot copies each message to the requesting chat. Created staging message IDs are tracked for best-effort cleanup. A standard user session is valid but still has the 2000 MiB single-file limit. Premium affects upload capacity, not the ability to generate a session.

## Credentials and data

- Production credentials are never included in source, example files, ZIPs or GitHub Actions. Non-secret example IDs are only defaults.
- Settings are written atomically into a plaintext local `.env`. The OS account/folder permissions protect that file; this is not an encrypted credential vault. POSIX writes request mode 0600.
- Runtime Telegram sessions use in-memory storage. In user mode, STRING_SESSION persists the authorization key in `.env` or the environment. Treat it like a logged-in account; revoke exposed sessions in Telegram Settings > Devices. Replace exposed bot tokens through BotFather.
- Session generation collects codes and optional two-step passwords locally and does not persist them. The session itself is saved directly rather than printed or sent to a chat. Failed generation attempts try to log out the newly created authorization.
- Git ignores private environment files, session files, local environments and data. The Docker context excludes private settings. GitHub secrets do not automatically become laptop settings.
- SQLite/MongoDB records IDs, target filenames, status, timestamps and error classes. It stores neither credentials nor media bytes. Application logs/notifications avoid raw SDK/database exception messages.
- The operator can access local downloads and multipart data. In user mode, staging channel admins can also access staged files. Bot chats and channels are not Telegram secret chats.

## Limits and verification

ADMIN_ID restricts only `/admin`; renaming is available to other Telegram users subject to optional join checks and per-user queue limits. Users can cancel only their own job. A single transfer consumer processes up to ten queued jobs, with a six-hour per-job deadline and bounded FloodWait retries. The in-memory queue does not resume after restarts.

Temporary files are removed on completion, failures and cooperative cancellation. Power loss/forced kill can leave local job folders for the next startup to remove. User-mode staging cleanup can fail when the network or permissions change. Multipart jobs can leave already delivered pieces when later steps fail; users must retry a complete set and not mix attempts.

Free Telegram users can download files uploaded by Premium users, but cannot upload a new single 4GB file themselves. Forwarding an existing eligible file, or splitting a local original with SPLIT_LOCAL before uploading individual parts, preserves those limits. Joining creates a full file on local disk; it does not upload it back as a single Telegram file.

Tests use synthetic credentials, fake Telegram clients and real local files/SQLite. They verify standard session generation, account-dependent limits, transfer routing, split/join integrity, validation, cancellation and cleanup. They do not establish that the user's real token, channel, network or a live 4GB transfer works. Run CHECK and a real file trial on the laptop.
