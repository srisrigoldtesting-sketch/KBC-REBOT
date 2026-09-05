from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .config import ENV_FILE, ROOT, Settings, SetupError, read_values
from .runlock import RunLock

FIELDS = [
    ("API_ID", "Telegram API ID", False), ("API_HASH", "Telegram API hash", True),
    ("BOT_TOKEN", "Fresh bot token", True), ("ADMIN_ID", "Your Telegram user ID", False),
    ("TRANSFER_MODE", "Transfer mode", False),
    ("STRING_SESSION", "User session (user mode only)", True), ("STAGING_CHAT_ID", "Staging channel (user mode only)", False),
    ("FORCE_SUB_CHANNEL", "Join channel (optional)", False), ("LOG_CHANNEL_ID", "Log channel ID (optional)", False),
    ("DATABASE_URL", "MongoDB URI (blank = local)", True), ("DATABASE_NAME", "Database name", False),
    ("START_PIC", "Welcome picture URL (optional)", False), ("WORK_DIR", "Local data folder", False),
]


def write_values(values: dict[str, str], path: Path = ENV_FILE):
    """Atomic dotenv update. Never interpolate shell syntax or print values."""
    content = "# Private KBC REBOT settings. Never upload or share this file.\n"
    for key, value in values.items():
        if not key.replace("_", "").isalnum():
            continue
        escaped = str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\r", "").replace("\n", "")
        content += f"{key}='{escaped}'\n"
    fd, temporary = tempfile.mkstemp(prefix=".kbc-env-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    import tkinter as tk
    from tkinter import messagebox, ttk
    values = read_values(ROOT / ".env.example")
    saved = read_values()
    for old, new in (("ADMIN", "ADMIN_ID"), ("FORCE_SUBS", "FORCE_SUB_CHANNEL"), ("LOG_CHANNEL", "LOG_CHANNEL_ID")):
        if old in saved and new not in saved:
            saved[new] = saved[old]
    values.update(saved)
    window = tk.Tk()
    window.title("KBC REBOT - Private local settings")
    window.resizable(True, False)
    frame = ttk.Frame(window, padding=18)
    frame.grid(sticky="nsew")
    ttk.Label(frame, text="KBC REBOT", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
    ttk.Label(frame, text="Choose bot mode: no Premium, user session or staging channel needed.\nSingle files up to 2000 MiB; /splitrename sends larger files as parts.").grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 15))
    inputs = {}
    for row, (key, label, secret) in enumerate(FIELDS, start=2):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
        variable = tk.StringVar(value=values.get(key, "bot" if key == "TRANSFER_MODE" else ""))
        widget = (ttk.Combobox(frame, textvariable=variable, values=("bot", "user"), state="readonly", width=52)
                  if key == "TRANSFER_MODE" else ttk.Entry(frame, textvariable=variable, width=55, show="*" if secret else ""))
        widget.grid(row=row, column=1, sticky="ew", pady=5)
        inputs[key] = variable

    def save():
        updated = {**saved, **{k: v.get().strip() for k, v in inputs.items()}, "MAX_CONCURRENT_JOBS": "1"}
        try:
            with RunLock(ROOT / ".kbc.lock"):
                write_values(updated)
        except Exception as exc:
            messagebox.showerror("Could not save", str(exc) if isinstance(exc, SetupError) else "Use a writable folder such as C:\\KBC-REBOT.")
            return
        try:
            Settings.from_values(updated)
        except SetupError as exc:
            messagebox.showinfo("Saved - setup incomplete", f"Settings saved locally.\n\n{exc}\n\nYou can return to CONFIGURE.cmd later.")
        else:
            messagebox.showinfo("Saved", "Settings saved locally. Close this window and run CHECK.cmd, then START.cmd.")
            window.destroy()

    ttk.Button(frame, text="Save settings", command=save).grid(row=len(FIELDS) + 2, column=1, sticky="e", pady=(15, 0))
    window.mainloop()


if __name__ == "__main__":
    main()
