import base64
import os
import time
from pathlib import Path
from threading import Lock

import requests
from PIL import Image, ImageOps

from app.models.schemas import OCRBlock, OCRResponse


class PaddleOCRService:
    def __init__(self) -> None:
        self._engine = None
        self._engine_lock = Lock()
        self._load_error: str | None = None
        self._warming = False
        self._baidu_token: str | None = None
        self._baidu_token_expires_at = 0.0

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        if self._load_error:
            return None

        with self._engine_lock:
            if self._engine is not None:
                return self._engine
            if self._load_error:
                return None

            try:
                os.environ.setdefault("DISABLE_MODEL_SOURCE_CHECK", "True")
                from paddleocr import PaddleOCR

                self._engine = self._build_engine(PaddleOCR)
                return self._engine
            except Exception as exc:  # PaddleOCR is optional during early development.
                self._load_error = str(exc)
                return None

    def warmup(self) -> None:
        if self._provider() == "baidu":
            return

        self._warming = True
        try:
            self._get_engine()
        finally:
            self._warming = False

    def status(self) -> dict[str, str | bool | None]:
        if self._provider() == "baidu":
            configured = bool(os.getenv("BAIDU_OCR_API_KEY") and os.getenv("BAIDU_OCR_SECRET_KEY"))
            return {
                "engine": "baidu-ocr",
                "ready": configured,
                "warming": False,
                "load_error": None if configured else "缺少 BAIDU_OCR_API_KEY 或 BAIDU_OCR_SECRET_KEY",
            }

        return {
            "engine": "paddleocr" if self._engine is not None else "paddleocr-fallback",
            "ready": self._engine is not None,
            "warming": self._warming,
            "load_error": self._load_error,
        }

    def _provider(self) -> str:
        return os.getenv("OCR_PROVIDER", "paddle").strip().lower()

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
        if self._provider() == "baidu":
            return self._recognize_with_baidu(upload_id, image_path)

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

    def _recognize_with_baidu(self, upload_id: str, image_path: Path) -> OCRResponse:
        try:
            prepared_path = self._prepare_image(image_path)
            token = self._get_baidu_access_token()
            endpoint = os.getenv("BAIDU_OCR_ENDPOINT", "general_basic")
            timeout = int(os.getenv("BAIDU_OCR_TIMEOUT", "90"))
            url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/{endpoint}"

            image_base64 = base64.b64encode(prepared_path.read_bytes()).decode("utf-8")
            response = requests.post(
                url,
                params={"access_token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "image": image_base64,
                    "language_type": "CHN_ENG",
                    "detect_direction": "true",
                    "paragraph": "false",
                },
                timeout=(10, timeout),
            )
            response.raise_for_status()
            payload = response.json()
            if "error_code" in payload:
                raise RuntimeError(f"{payload.get('error_code')}: {payload.get('error_msg')}")

            blocks: list[OCRBlock] = []
            lines: list[str] = []
            for item in payload.get("words_result", []) or []:
                text = str(item.get("words", "")).strip()
                if not text:
                    continue
                location = item.get("location")
                box = [location] if location else None
                blocks.append(OCRBlock(text=text, confidence=None, box=box))
                lines.append(text)

            return OCRResponse(
                upload_id=upload_id,
                text="\n".join(lines),
                blocks=blocks,
                engine="baidu-ocr",
            )
        except Exception as exc:
            fallback = "OCR 服务暂时不可用，请在这里粘贴或校正题干与选项。"
            return OCRResponse(
                upload_id=upload_id,
                text=fallback,
                blocks=[OCRBlock(text=fallback, confidence=None, box=None)],
                engine="baidu-ocr-fallback",
                warning=f"百度 OCR 调用失败：{exc}",
            )

    def _get_baidu_access_token(self) -> str:
        api_key = os.getenv("BAIDU_OCR_API_KEY")
        secret_key = os.getenv("BAIDU_OCR_SECRET_KEY")
        if not api_key or not secret_key:
            raise RuntimeError("缺少 BAIDU_OCR_API_KEY 或 BAIDU_OCR_SECRET_KEY")

        now = time.time()
        if self._baidu_token and now < self._baidu_token_expires_at:
            return self._baidu_token

        with self._engine_lock:
            now = time.time()
            if self._baidu_token and now < self._baidu_token_expires_at:
                return self._baidu_token

            response = requests.post(
                "https://aip.baidubce.com/oauth/2.0/token",
                params={
                    "grant_type": "client_credentials",
                    "client_id": api_key,
                    "client_secret": secret_key,
                },
                timeout=(10, 30),
            )
            response.raise_for_status()
            payload = response.json()
            if "access_token" not in payload:
                raise RuntimeError(payload.get("error_description") or payload.get("error") or "获取 access_token 失败")

            self._baidu_token = str(payload["access_token"])
            expires_in = int(payload.get("expires_in", 2592000))
            self._baidu_token_expires_at = time.time() + max(expires_in - 300, 60)
            return self._baidu_token

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
