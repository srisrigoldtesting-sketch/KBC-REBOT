from __future__ import annotations

import argparse
import asyncio
import shutil
import tempfile
import uuid
from contextlib import aclosing
from pathlib import Path

from .config import DISK_RESERVE, MAX_FILE_BYTES, SetupError
from .parts import join_parts, split_file, write_manifest
from .security import safe_filename


async def split_local(source: Path, name: str) -> Path:
    size = source.stat().st_size
    if not 0 < size <= MAX_FILE_BYTES:
        raise SetupError("Choose a non-empty local file up to 4000 MiB.")
    if shutil.disk_usage(source.parent).free < size + DISK_RESERVE:
        raise SetupError("Free enough space beside the original file for a complete set of parts plus 1 GiB.")
    target = source.parent / ("KBC-parts-" + uuid.uuid4().hex[:10])
    with tempfile.TemporaryDirectory(prefix=".kbc-split-", dir=source.parent) as temporary:
        directory = Path(temporary)
        parts = []
        async with aclosing(split_file(source, directory, name)) as iterator:
            async for part in iterator:
                parts.append(part)
                print(f"Prepared part {len(parts)}.", flush=True)
        if sum(part.size for part in parts) != size:
            raise SetupError("The source changed while splitting. Close programs using it and try again.")
        write_manifest(directory, name, parts)
        # Create the output only after all parts are complete; never overwrite originals.
        directory.rename(target)
    return target


def main():
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog
    parser = argparse.ArgumentParser(description="Local splitting/joining; no Telegram login or Premium required.")
    parser.add_argument("operation", choices=("split", "join"))
    args = parser.parse_args()
    window = tk.Tk()
    window.withdraw()
    try:
        if args.operation == "join":
            selected = filedialog.askopenfilename(title="Select the downloaded KBC parts manifest", filetypes=[("KBC parts manifest", "*.kbc-parts.json")])
            if not selected:
                return 0
            print("Joining and verifying parts. Keep this console open; Ctrl+C cancels.", flush=True)
            output = join_parts(Path(selected))
            messagebox.showinfo("File joined", f"Your complete renamed file is ready:\n{output}\n\nThe downloaded parts were preserved.")
        else:
            selected = filedialog.askopenfilename(title="Select a local file up to 4000 MiB")
            if not selected:
                return 0
            source = Path(selected)
            requested = simpledialog.askstring("New filename", "Filename to restore after joining:", initialvalue=source.name)
            if requested is None:
                return 0
            name = safe_filename(requested, source.suffix)
            print("Splitting into files up to 2000 MiB. Keep this console open; Ctrl+C cancels.", flush=True)
            output = asyncio.run(split_local(source, name))
            messagebox.showinfo("Parts ready", f"Parts and manifest are ready:\n{output}\n\nSend every part and the .kbc-parts.json file in Telegram. Use JOIN_PARTS.cmd to restore the complete renamed file. Your original was preserved.")
        return 0
    except KeyboardInterrupt:
        print("Cancelled. Incomplete output removed.")
        return 1
    except Exception as exc:
        text = str(exc) if isinstance(exc, (SetupError, ValueError)) else f"Operation failed ({type(exc).__name__}). Check file permissions and available space."
        messagebox.showerror("Could not finish", text)
        return 1
    finally:
        window.destroy()


if __name__ == "__main__":
    raise SystemExit(main())
