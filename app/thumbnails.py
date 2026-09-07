"""Convert Telegram photos into small, metadata-free upload thumbnails."""
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import SetupError

MAX_PHOTO_BYTES = 10 * 1024 * 1024


def normalize_thumbnail(data: bytes) -> bytes:
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise SetupError("Send a photo smaller than 10 MiB.")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width * source.height > 20_000_000:
                raise SetupError("Photo is too large. Send it as a compressed Telegram photo.")
            source.seek(0)
            resized = ImageOps.exif_transpose(source)
            resized.thumbnail((320, 320))
            rgba = resized.convert("RGBA")
            result = Image.new("RGB", rgba.size, "white")
            result.paste(rgba, mask=rgba.getchannel("A"))
            output = BytesIO()
            result.save(output, format="JPEG", quality=85, optimize=True)
            jpeg = output.getvalue()
            if len(jpeg) >= 200_000:
                raise SetupError("Unable to make a small thumbnail. Try another photo.")
            return jpeg
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        if isinstance(exc, SetupError):
            raise
        raise SetupError("This photo could not be read. Send a different JPG or PNG as a photo.") from None
