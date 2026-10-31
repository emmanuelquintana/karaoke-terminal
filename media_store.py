"""Private Blob persistence; files are streamed and restored atomically."""
import os
import tempfile
from pathlib import Path


class BlobUploadError(IOError):
    pass


def enabled() -> bool:
    return bool(os.environ.get("BLOB_READ_WRITE_TOKEN"))


def put_file(key: str, local_path: Path, content_type: str) -> str | None:
    if not enabled():
        return None
    try:
        from vercel.blob.sync import put_blob

        with local_path.open("rb") as body:
            result = put_blob(key, body, access="private", content_type=content_type,
                              content_length=local_path.stat().st_size, allow_overwrite=True)
        if not result.url:
            raise ValueError("Missing blob URL")
        return result.url
    except Exception as exc:
        raise BlobUploadError("No pude guardar el archivo. Revisa la disponibilidad y cuota de Blob.") from exc


def restore_file(url: str, dest_path: Path) -> bool:
    if not enabled():
        return False
    temporary = None
    try:
        from vercel.blob.sync import stream_blob

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        # A unique temporary file keeps concurrent readers from sharing a partial download.
        with tempfile.NamedTemporaryFile(dir=dest_path.parent, delete=False) as output:
            temporary = Path(output.name)
            with stream_blob(url, access="private") as chunks:
                for chunk in chunks:
                    output.write(chunk)
        temporary.replace(dest_path)
        return True
    except Exception:
        return False
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
