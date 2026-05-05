import os
from pathlib import Path

from PIL import Image, ImageOps

from app.models.schemas import OCRBlock, OCRResponse


class PaddleOCRService:
    def __init__(self) -> None:
        self._engine = None
        self._load_error: str | None = None

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        if self._load_error:
            return None

        try:
            from paddleocr import PaddleOCR

            self._engine = self._build_engine(PaddleOCR)
            return self._engine
        except Exception as exc:  # PaddleOCR is optional during early development.
            self._load_error = str(exc)
            return None

    def _build_engine(self, paddle_ocr_class):
        device = os.getenv("OCR_DEVICE", "cpu")
        cpu_threads = int(os.getenv("OCR_CPU_THREADS", "2"))

        configs = [
            {
                "lang": "ch",
                "device": device,
                "ocr_version": os.getenv("OCR_VERSION", "PP-OCRv5"),
                "text_detection_model_name": os.getenv("OCR_DET_MODEL", "PP-OCRv5_mobile_det"),
                "text_recognition_model_name": os.getenv("OCR_REC_MODEL", "PP-OCRv5_mobile_rec"),
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
                "cpu_threads": cpu_threads,
            },
            {
                "lang": "ch",
                "device": device,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
                "cpu_threads": cpu_threads,
            },
            {
                "lang": "ch",
                "use_angle_cls": True,
                "show_log": False,
            },
        ]

        errors: list[str] = []
        for config in configs:
            try:
                return paddle_ocr_class(**config)
            except TypeError as exc:
                errors.append(str(exc))

        raise RuntimeError("; ".join(errors) or "PaddleOCR 初始化失败")

    def recognize(self, upload_id: str, image_path: Path) -> OCRResponse:
        engine = self._get_engine()
        if engine is None:
            fallback = (
                "OCR 引擎尚未就绪，请在这里粘贴或校正题干与选项。\n"
                "示例：下列哪项最能体现阴阳互根关系？\n"
                "A. 阴阳对立\nB. 阴阳互根\nC. 阴阳消长\nD. 阴阳转化"
            )
            return OCRResponse(
                upload_id=upload_id,
                text=fallback,
                blocks=[OCRBlock(text=fallback, confidence=None, box=None)],
                engine="paddleocr-fallback",
                warning=f"PaddleOCR 未加载成功：{self._load_error or '未安装或环境未配置'}",
            )

        prepared_path = self._prepare_image(image_path)
        result = self._run_engine(engine, prepared_path)
        blocks: list[OCRBlock] = []
        lines: list[str] = []

        if hasattr(engine, "predict"):
            lines, blocks = self._parse_v3_result(result)
        else:
            lines, blocks = self._parse_v2_result(result)

        return OCRResponse(
            upload_id=upload_id,
            text="\n".join(line for line in lines if line.strip()),
            blocks=blocks,
            engine="paddleocr",
        )

    def _prepare_image(self, image_path: Path) -> Path:
        max_side = int(os.getenv("OCR_MAX_IMAGE_SIDE", "1600"))
        prepared_path = image_path.with_name(f"{image_path.stem}_ocr.jpg")

        with Image.open(image_path) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")
            width, height = image.size
            longest = max(width, height)
            if longest > max_side:
                scale = max_side / longest
                image = image.resize(
                    (int(width * scale), int(height * scale)),
                    Image.Resampling.LANCZOS,
                )
            image.save(prepared_path, "JPEG", quality=92, optimize=True)

        return prepared_path

    def _run_engine(self, engine, image_path: Path):
        if hasattr(engine, "predict"):
            return engine.predict(str(image_path))
        return engine.ocr(str(image_path), cls=True)

    def _parse_v3_result(self, result) -> tuple[list[str], list[OCRBlock]]:
        lines: list[str] = []
        blocks: list[OCRBlock] = []

        for page in result or []:
            payload = getattr(page, "json", None)
            if callable(payload):
                payload = payload()
            if payload is None and isinstance(page, dict):
                payload = page
            if not isinstance(payload, dict):
                continue

            data = payload.get("res", payload)
            texts = data.get("rec_texts", []) or []
            scores = self._to_list(data.get("rec_scores", []))
            boxes = self._to_list(data.get("rec_polys", data.get("rec_boxes", [])))

            for index, text in enumerate(texts):
                confidence = self._safe_float(scores[index]) if index < len(scores) else None
                box = boxes[index] if index < len(boxes) else None
                blocks.append(OCRBlock(text=str(text), confidence=confidence, box=box))
                lines.append(str(text))

        return lines, blocks

    def _parse_v2_result(self, result) -> tuple[list[str], list[OCRBlock]]:
        lines: list[str] = []
        blocks: list[OCRBlock] = []

        for page in result or []:
            for item in page or []:
                box = item[0]
                text = item[1][0]
                confidence = float(item[1][1])
                blocks.append(OCRBlock(text=text, confidence=confidence, box=box))
                lines.append(text)

        return lines, blocks

    def _to_list(self, value):
        if hasattr(value, "tolist"):
            return value.tolist()
        return value or []

    def _safe_float(self, value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


ocr_service = PaddleOCRService()
