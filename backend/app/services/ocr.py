from pathlib import Path

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

            self._engine = PaddleOCR(use_angle_cls=True, lang="ch")
            return self._engine
        except Exception as exc:  # PaddleOCR is optional during early development.
            self._load_error = str(exc)
            return None

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

        result = engine.ocr(str(image_path), cls=True)
        blocks: list[OCRBlock] = []
        lines: list[str] = []

        for page in result or []:
            for item in page or []:
                box = item[0]
                text = item[1][0]
                confidence = float(item[1][1])
                blocks.append(OCRBlock(text=text, confidence=confidence, box=box))
                lines.append(text)

        return OCRResponse(
            upload_id=upload_id,
            text="\n".join(lines),
            blocks=blocks,
            engine="paddleocr",
        )


ocr_service = PaddleOCRService()

