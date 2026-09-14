from pathlib import Path

ARTIFACTS_DIR = Path("/app/data/artifacts")


def _decode_with_cv2(image_path: Path) -> list:
    import cv2
    import numpy as np

    img = cv2.imread(str(image_path))
    if img is None:
        return []
    detector = cv2.QRCodeDetector()
    data, points, _ = detector.detectAndDecode(img)
    results = []
    if data:
        results.append({
            "content": data,
            "box": points.tolist() if points is not None else None,
            "decoder": "opencv",
        })
    return results


def _otsu_threshold(gray_img) -> int:
    hist = gray_img.histogram()
    total = sum(hist)
    sum_b = 0
    w_b = 0
    maximum = 0.0
    sum1 = sum(i * hist[i] for i in range(256))
    threshold = 128
    for i in range(256):
        w_b += hist[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * hist[i]
        m_b = sum_b / w_b
        m_f = (sum1 - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2
        if between > maximum:
            maximum = between
            threshold = i
    return threshold


def _decode_with_pyzbar(image_path: Path) -> list:
    from pyzbar.pyzbar import decode
    from PIL import Image, ImageOps, ImageFilter

    # Генератор многоэтапной нормализации и шумоподавления
    def _generate_variants(img):
        # 1. Оригинал (быстрый путь)
        yield "original", img

        # 2. Градации серого + автоконтраст
        gray = img.convert("L")
        gray_contrast = ImageOps.autocontrast(gray)
        yield "gray_autocontrast", gray_contrast

        # 3. Шумоподавление: Медианный фильтр 3x3 (удаление шума «соль и перец», артефактов скана)
        denoised = gray_contrast.filter(ImageFilter.MedianFilter(size=3))
        yield "denoised_median", denoised

        # 4. Бинаризация методом Оцу (для неравномерного освещения и теней)
        try:
            th = _otsu_threshold(denoised)
            binarized = denoised.point(lambda p: 255 if p > th else 0)
            yield "binarized_otsu", binarized
        except Exception:
            pass

        # 5. Инверсия (для QR-кодов в темной теме: белый код на темном фоне)
        try:
            inverted = ImageOps.invert(gray_contrast)
            yield "inverted_dark_mode", inverted
        except Exception:
            pass

        # 6. Повышение резкости (Sharpen)
        sharpened = denoised.filter(ImageFilter.SHARPEN)
        yield "sharpened", sharpened

        # 7. Двукратное увеличение (Upscale) для мелких/сжатых QR
        if img.width < 350 or img.height < 350:
            upscaled = denoised.resize((img.width * 2, img.height * 2), Image.Resampling.NEAREST)
            yield "upscaled_2x", upscaled

    with Image.open(image_path) as raw_img:
        for stage_name, variant in _generate_variants(raw_img):
            decoded = decode(variant)
            if decoded:
                results = []
                for obj in decoded:
                    results.append({
                        "content": obj.data.decode("utf-8", errors="replace"),
                        "type": obj.type,
                        "box": [obj.rect.left, obj.rect.top, obj.rect.width, obj.rect.height]
                        if obj.rect else None,
                        "decoder": f"pyzbar_{stage_name}",
                        "normalized": stage_name != "original",
                        "normalization_stage": stage_name,
                    })
                return results

    return []


def extract(payload: dict) -> dict:
    image_path = payload.get("image_path")
    if not image_path:
        return {"ok": False, "error": "image_path обязателен"}

    p = Path(image_path)
    if not p.is_absolute():
        p = ARTIFACTS_DIR / p
    if not p.exists():
        return {"ok": False, "error": f"файл не найден: {p}"}

    # Пробуем pyzbar в приоритете, fallback на OpenCV
    try:
        results = _decode_with_pyzbar(p)
        if results:
            return {"ok": True, "qr_count": len(results), "results": results}
    except ImportError:
        pass

    try:
        results = _decode_with_cv2(p)
        return {"ok": True, "qr_count": len(results), "results": results}
    except ImportError:
        return {"ok": False,
                "error": "нет QR-декодера (ни pyzbar, ни opencv-python)"}
    except Exception as e:  # cv2 может упасть на битых изображениях
        return {"ok": False, "error": f"QR decode error: {e}"}