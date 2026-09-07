"""Bot subscriptions are separate from Telegram account upload entitlements."""
import math
import time
from datetime import datetime, timezone

from .config import MAX_FILE_BYTES, SetupError

TRIAL_SECONDS = 6 * 60 * 60
DEFAULT_CAPACITY_MIB = 2000


def plan_state(profile, now=None):
    now = time.time() if now is None else now
    premium = profile["premium_until"] > now
    until = profile["premium_until"] if premium else profile["trial_started"] + TRIAL_SECONDS
    limit = profile["capacity_mib"]
    active = until > now and limit > 0
    name = "Premium" if premium else ("Free trial" if until > now else "Expired")
    if limit == 0:
        name = "Disabled by admin"
    return name, active, limit * 1024**2, until


async def require_access(db, user_id, admin_id, size=0):
    profile = await db.get_profile(user_id)
    if user_id == admin_id:
        return profile
    _, active, capacity, _ = plan_state(profile)
    if not active:
        raise SetupError("Your trial/plan has ended or access is disabled. Use /myplan and /upgrade to contact the admin.")
    if size > min(capacity, MAX_FILE_BYTES):
        raise SetupError(f"Your plan allows inputs up to {capacity // 1024**2} MiB. Use /upgrade for a higher capacity.")
    return profile


def describe_plan(profile, user_id, admin_id, upload_limit):
    name, _, capacity, until = plan_state(profile)
    if user_id == admin_id:
        return f"Administrator: no trial expiry. Input limit: 4000 MiB.\nSingle-file Telegram upload limit: {upload_limit // 1024**2} MiB."
    remaining = max(0, math.ceil((until - time.time()) / 60))
    expiry = datetime.fromtimestamp(until, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (f"Your ID: {user_id}\nPlan: {name}\nInput capacity: {capacity // 1024**2} MiB\n"
            f"Expires: {expiry}\nRemaining: {remaining} minutes\n"
            f"Single-file Telegram upload limit: {upload_limit // 1024**2} MiB.\n"
            "Larger permitted inputs need /splitrename. Bot Premium does not buy Telegram Premium.")


def validate_caption(value):
    if not value.strip() or len(value.encode('utf-16-le')) // 2 > 700:
        raise SetupError("Caption must contain 1–700 characters (emoji may count as two). Use {filename} and {filesize} if needed.")
    return value


def render_caption(template, filename, size):
    if not template:
        return filename
    # Literal replacements only: no evaluation, attribute access or arbitrary formatting.
    text = template.replace("{filename}", filename).replace("{filesize}", f"{size / 1024**2:.1f} MiB")
    return text.encode('utf-16-le')[:1800].decode('utf-16-le', errors='ignore')
