# Authentication and request flow

## Components tied to code

| Component | Code | Authentication/authorization |
|---|---|---|
| Configuration | `app/config.py`, `app/configure.py` | Reads root `.env`, then environment overrides; validates required formats, masks secret fields in the settings UI, excludes secrets from Settings repr |
| Bot identity | `app/clients.py:build_clients`, `connect_client` | Telegram app API_ID/API_HASH plus BOT_TOKEN; explicit `sign_in_bot` rather than interactive user login |
| Transfer identity | `app/clients.py:connect_client`, `verify_telegram` | Serialized user authorization in STRING_SESSION; checks `get_me().is_premium` and that it is not a bot |
| Session creation | `app/generate_session.py` | Phone/code/optional two-step password entered locally; in-memory session exported directly into `.env` |
| Telegram authorization | `app/handlers.py`, `app/security.py` | Telegram sender user ID, exact admin ID filter, optional channel membership check |
| Job processing | `app/worker.py` | Shared private staging channel; each client uses its own authenticated Telegram connection |
| Metadata | `app/database.py` | Local OS access for SQLite, or credentials in optional MongoDB URI |
| Process isolation | `app/runlock.py` | An OS-held lock prevents simultaneous START/CHECK/session setup from this folder |

## Startup

1. `Settings.load()` reads `.env` beside the application, without dotenv variable interpolation, and overlays runtime environment variables. Values are trimmed; missing credentials, malformed or duplicated tokens, invalid session formats, unsupported concurrency and bad IDs fail with messages that name the field but do not echo its value.
2. `main()` takes the local process lock. `run()` opens SQLite by default or MongoDB when a URI is supplied, pings it, and marks previous nonterminal jobs interrupted. Old temporary folders under the app-owned `data/jobs` directory are removed.
3. `connect_client()` connects each in-memory client. The bot explicitly imports the bot authorization. The user client requires a stored authorization; it never asks a bot operator for a phone number during normal startup. Telegram validates each credential remotely; local format validation alone is not authentication.
4. `verify_telegram()` checks active Premium, resolves the user account's private channel through its dialogs, and verifies both identities can post and delete there. If join checking is enabled, the destination must be a group/channel where the bot is admin.
5. Handlers and the single transfer worker are enabled. There is no inbound HTTP server, webhook secret, website password, JWT, OAuth refresh token or browser login in this application. Both clients use outbound Telegram MTProto connections.

## Request sequence

1. A user sends the bot a file and replies `/rename New Name.ext`. Telegram supplies the authenticated sender ID; the bot does not collect that user's password or token.
2. The handler checks optional subscription membership, validates a Windows-safe filename and file size, and rejects duplicate per-user work or a full queue. The database records the job ID, user ID, target filename and status.
3. The bot copies the original message into the private staging channel on Telegram's servers. This step does not upload/download all file bytes through the bot identity.
4. The Premium client calls `get_messages` for that new staging message. This matters because message/file references belong to the account that retrieved them. It downloads that Premium-visible message into a unique local job directory.
5. The worker verifies the local byte count, renames the file within the same directory, then uploads it as a document through the Premium identity. This pinned implementation caps uploads at 4000 MiB. Setting a made-up `Session.MAX_FILE_SIZE` attribute cannot grant Premium or bypass Telegram limits; this application does not do that.
6. The bot uses `copy_message` to copy the newly uploaded result from staging into the user's chat. Pyrofork's copy method obtains the message for the bot identity. The bot does not re-upload the large file from disk.
7. The worker records success and attempts to delete both staging messages. The temporary directory is removed on normal completion, exceptions and cooperative cancellation. Failure to clean Telegram messages is logged by exception class for the channel owner to investigate.

## Credential lifecycle

- There are no built-in production tokens, API hashes, session strings or MongoDB passwords. `.env.example` includes non-secret defaults only.
- The local settings editor writes `.env` atomically and masks credential inputs. The file remains plaintext on disk; the Windows user account and folder permissions protect it. POSIX writes request mode 0600. No encryption-at-rest claim is made.
- The generator uses the supplied app credentials to authenticate an existing user account. It never prints the session or sends it into Saved Messages/another chat. Codes and two-step passwords are not persisted. If setup fails before saving, it attempts to log out that newly created authorization.
- BOT_TOKEN controls the bot; replace an exposed token with BotFather. STRING_SESSION contains an authorization key equivalent to a logged-in user session: revoke an exposed session through Telegram Settings > Devices. Two-step verification does not make an already stolen session harmless.
- Both runtime clients use in-memory Pyrofork storage. No `.session` SQLite file is intentionally written; STRING_SESSION remains in `.env` or the environment between runs.
- `.env`, session files, data, local environments and ZIPs are excluded from Git. The Docker context additionally excludes credential files. The delivered ZIP contains no private `.env`.
- Database records include only metadata, not tokens or file bytes. Raw SDK/MongoDB exception messages are neither stored nor sent to chats. Application logs report error classes/job IDs; controlled SetupError messages provide corrective instructions.
- GitHub Actions runs only synthetic offline tests. GitHub repository secrets are not fetched, embedded in packages or automatically transferred to a laptop.

## Scope and remaining limits

`ADMIN_ID` authorizes `/admin`; it does not make the entire bot owner-only. Each user can cancel only the job associated with their Telegram sender ID. Optional join checking controls membership, not identity authentication. The app's operator and staging channel admins can access staged documents and local temporary files; bot conversations and staging channels are not Telegram secret chats.

One transfer runs at a time, with a ten-job waiting queue and a six-hour per-job deadline. Rate-limit retries are bounded. A forced kill or power failure can leave Telegram staging messages, and the in-memory queue is not resumed. Startup removes interrupted local job folders; users must resubmit jobs after restarts. A lost network response can leave the outcome of a server-side copy uncertain, so blind network retries of message creation are avoided.

Only live CHECK plus an actual file transfer can confirm a particular bot token, Premium subscription, staging permissions and network work together. Mocked tests and syntax compilation do not establish successful 4GB service on a real laptop.
