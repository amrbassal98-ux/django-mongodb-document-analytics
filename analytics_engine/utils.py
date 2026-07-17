import base64
import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)

IMAGE_EXTS = {"png", "jpg", "jpeg", "bmp", "tiff", "tif", "webp"}
VISION_EXTS = IMAGE_EXTS | {"pdf"}


def extract_text(filename: str, content: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        return _extract_pdf_text(content)

    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning("Fallback to latin-1 for %s", filename)
        return content.decode("latin-1", errors="replace")


def is_vision_file(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in VISION_EXTS


def encode_for_vision(filename: str, content: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        return _pdf_page_to_base64(content)
    return _image_bytes_to_base64(content)


def _image_bytes_to_base64(content: bytes) -> str:
    try:
        img = Image.open(io.BytesIO(content))
    except Exception as exc:
        raise ValueError(f"Failed to open image: {exc}") from exc

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def _pdf_page_to_base64(content: bytes) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise ImportError("PyMuPDF required for PDF-to-image conversion") from exc

    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Failed to open PDF stream: {exc}") from exc

    if len(doc) == 0:
        doc.close()
        raise ValueError("PDF has no pages")

    try:
        pix = doc[0].get_pixmap()
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    except Exception as exc:
        doc.close()
        raise ValueError(f"Failed to render PDF page: {exc}") from exc

    doc.close()

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def _extract_pdf_text(content: bytes) -> str:
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF not installed — falling back to raw decode for PDF")
        return content.decode("latin-1", errors="replace")

    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        logger.exception("Failed to open PDF stream")
        return content.decode("latin-1", errors="replace")

    pages = []
    for page_num in range(len(doc)):
        try:
            text = doc[page_num].get_text()
            if text.strip():
                pages.append(text)
        except Exception as exc:
            logger.warning("Failed to extract text from PDF page %d: %s", page_num, exc)

    doc.close()

    if not pages:
        logger.warning("No text extracted from PDF — falling back to raw decode")
        return content.decode("latin-1", errors="replace")

    return "\n\n".join(pages)
