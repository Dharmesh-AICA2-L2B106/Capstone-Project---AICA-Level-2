# -*- coding: utf-8 -*-
"""DPDP Lens OCR helper: reads one image file, prints the recognised text (UTF-8) to stdout.
Runs as its own program so the OCR engine never shares a process with Qt (DLL clash)."""
import sys, io


def main():
    from PIL import Image, ImageSequence
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    eng = RapidOCR()
    if len(sys.argv) < 2 or sys.argv[1] == "--selftest":
        sys.stdout.write("OCR_WORKER_OK\n")
        return 0
    data = open(sys.argv[1], "rb").read()
    Image.MAX_IMAGE_PIXELS = 80000000
    out = []
    with Image.open(io.BytesIO(data)) as im:
        for i, frame in enumerate(ImageSequence.Iterator(im)):
            if i >= 3:
                break
            fr = frame.convert("RGB")
            fr.thumbnail((2600, 2600))
            res = eng(np.array(fr))
            if hasattr(res, "txts"):
                out.extend(res.txts or [])
            else:
                out.extend(r[1] for r in (res[0] or []))
    sys.stdout.buffer.write("\n".join(str(x) for x in out).encode("utf-8"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        sys.stderr.write("ocr_worker error: %s\n" % e)
        sys.exit(2)
