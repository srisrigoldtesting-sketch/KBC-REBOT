# Authentication and credential flow

## Components

| Component | Identity/credential | Purpose |
|---|---|---|
| Control bot | `BOT_TOKEN` plus `API_ID`/`API_HASH` | Receives commands, checks membership, performs Telegram server-side copies, replies to users |
| Premium worker | `STRING_SESSION` plus `API_ID`/`API_HASH` | Authenticates a Telegram user account over MTProto and transfers files up to the account's supported limit |
| Admin authorization | Numeric `ADMIN_ID` | Restricts `/admin` through an exact Telegram user-ID filter |
| Staging channel | `STAGING_CHAT_ID` and Telegram membership/admin rights | Shared trusted boundary through which bot and Premium worker exchange messages |
| Force-subscription channel | `FORCE_SUB_CHANNEL` | Bot calls `get_chat_member`; no user credential is collected |
| MongoDB | `DATABASE_URL` | Server-to-server database authentication; stores user IDs and job metadata, not Telegram secrets |

## Request flow

1. The process reads mandatory credentials from the runtime environment. Startup fails if a required value is absent.
2. Pyrogram opens two independent authenticated sessions: a bot-token client and a Premium user-session client.
3. A user sends a document to the bot and replies with `/rename New Name.ext`.
4. The bot checks channel membership and validates/sanitizes the requested filename.
5. The bot copies the Telegram message to the private staging channel without downloading the file.
6. The Premium worker, which is a member of that channel, downloads through MTProto, renames the local temporary file, and uploads it to the same channel.
7. The bot copies the resulting message back to the requesting user without re-uploading its bytes.
8. The temporary local file is removed in a `finally` block. MongoDB keeps status and minimal job metadata.

## Credential and token handling

- No production credential has a source-code fallback.
- `.env` and Pyrogram session files are gitignored.
- `.env.example` contains placeholders only.
- `BOT_TOKEN` authenticates only the bot and should be rotated with BotFather if exposed.
- `STRING_SESSION` is equivalent to a logged-in Telegram user session. Revoke it from Telegram **Settings → Devices** if exposed.
- `API_HASH` is treated as a secret and is not logged.
- `DATABASE_URL` should use a least-privilege database user, an IP allowlist, and a rotated password.
- Error logs contain exception type and truncated text; they must never include environment dumps.
- The staging channel must be private. Both identities need access; the bot needs permission to post/copy, and the Premium user needs permission to read/post.

## Trust boundaries and limitations

- `ADMIN_ID` is authorization, not authentication; Telegram has already authenticated the sender of the update.
- A string session does not prove the account has Premium. Validate the account and perform a large-file test before production.
- 4 GiB requires adequate local ephemeral storage, memory-safe streaming in Pyrogram, sufficient host bandwidth, and a Premium Telegram account. Telegram/platform limits can change.
- Never process copyrighted or illegal material. Add retention, abuse-reporting, and privacy policies before public launch.

