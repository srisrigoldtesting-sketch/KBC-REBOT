from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import DISK_RESERVE, FREE_UPLOAD_BYTES, MAX_FILE_BYTES, SetupError
from .security import safe_filename

MANIFEST_SUFFIX = ".kbc-parts.json"
BLOCK_SIZE = 4 * 1024 * 1024


@dataclass(frozen=True)
class Part:
    name: str
    size: int
    sha256: str


async def split_file(source: Path, directory: Path, name: str, limit: int = FREE_UPLOAD_BYTES):
    """Yield closed part files. The caller uploads/removes each before the next part."""
    if limit <= 0 or limit > FREE_UPLOAD_BYTES:
        raise SetupError("Part size must be positive and at most 2000 MiB.")
    safe_filename(name)
    with source.open("rb") as stream:
        index = 1
        while True:
            first = stream.read(min(BLOCK_SIZE, limit))
            if not first:
                return
            path = directory / f"{name}.part{index:03d}"
            digest = hashlib.sha256()
            size = 0
            with path.open("xb") as output:
                chunk = first
                while chunk:
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                    await asyncio.sleep(0)  # Keep cancellation and Telegram updates responsive.
                    chunk = stream.read(min(BLOCK_SIZE, limit - size)) if size < limit else b""
            yield Part(path.name, size, digest.hexdigest())
            index += 1


def write_manifest(directory: Path, name: str, parts: list[Part]) -> Path:
    path = directory / (name + MANIFEST_SUFFIX)
    path.write_text(json.dumps({"format": "kbc-parts-v1", "filename": name,
                               "size": sum(p.size for p in parts), "parts": [asdict(p) for p in parts]},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_manifest(path: Path) -> dict:
    try:
        if path.stat().st_size > 65536:
            raise ValueError
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError
        name, parts = value["filename"], value["parts"]
        if not isinstance(name, str) or not isinstance(parts, list):
            raise ValueError
        if value["format"] != "kbc-parts-v1" or safe_filename(name) != name or not 1 <= len(parts) <= 32:
            raise ValueError
        total = 0
        for index, part in enumerate(parts, 1):
            if (part["name"] != f"{name}.part{index:03d}" or type(part["size"]) is not int
                    or not 0 < part["size"] <= FREE_UPLOAD_BYTES or not re.fullmatch(r"[a-f0-9]{64}", part["sha256"])):
                raise ValueError
            total += part["size"]
        if type(value["size"]) is not int or value["size"] != total or not 0 < total <= MAX_FILE_BYTES:
            raise ValueError
        return value
    except (KeyError, TypeError, ValueError):
        raise SetupError("Invalid parts manifest. Download the original .kbc-parts.json sent with the parts.") from None


def join_parts(manifest_path: Path) -> Path:
    value = load_manifest(manifest_path)
    directory = manifest_path.parent
    target = directory / value["filename"]
    if target.exists():
        raise SetupError("The joined filename already exists. Move the parts and manifest to a new folder first.")
    if shutil.disk_usage(directory).free < value["size"] + DISK_RESERVE:
        raise SetupError("Free enough disk space for the joined file plus 1 GiB, then try again.")
    for part in value["parts"]:
        path = directory / part["name"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != part["size"]:
            raise SetupError("A part is missing or incomplete. Download all parts into the manifest folder with their original names.")
    created = False
    try:
        with target.open("xb") as output:
            created = True
            for part in value["parts"]:
                digest = hashlib.sha256()
                size = 0
                with (directory / part["name"]).open("rb") as stream:
                    while chunk := stream.read(BLOCK_SIZE):
                        size += len(chunk)
                        if size > part["size"]:
                            raise SetupError("A part changed during joining. Download it again.")
                        digest.update(chunk)
                        output.write(chunk)
                if size != part["size"] or digest.hexdigest() != part["sha256"]:
                    raise SetupError("A part's checksum did not match. Download the parts again.")
        return target
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise
