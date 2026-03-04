import io
import time
from typing import Tuple, Dict, Any, List
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, AutoModelForImageTextToText

from app.database import MODEL_PATH, MODEL_NAME, DEVICE, MAX_NEW_TOKENS


class PaddleOCRVLService:
    """
    Сервис для извлечения текста из изображений и PDF 
    с использованием PaddleOCR-VL 1.5 (мультимодальная модель)
    """
    
    SUPPORTED_IMAGE_FORMATS = {'.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.webp'}
    SUPPORTED_PDF_FORMATS = {'.pdf'}
    
    PROMPTS = {
        "ocr": "OCR:",
        "table": "Table Recognition:",
        "formula": "Formula Recognition:",
        "chart": "Chart Recognition:",
    }
    
    def __init__(self):
        self.device = DEVICE
        self.max_new_tokens = MAX_NEW_TOKENS
        
        # Определение источника модели
        if MODEL_PATH and Path(MODEL_PATH).exists():
            model_source = MODEL_PATH
            print(f"📂 Загрузка модели из локальной папки: {MODEL_PATH}")
        else:
            model_source = MODEL_NAME
            print(f"🌐 Загрузка модели из HuggingFace: {MODEL_NAME}")
        
        # Загрузка модели и процессора
        print(f"🔄 Загрузка модели {model_source}...")
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_source,
            torch_dtype=torch.bfloat16 if self.device == "cuda" else torch.float32,
        ).to(self.device).eval()
        
        self.processor = AutoProcessor.from_pretrained(model_source)
        print(f"✅ Модель загружена на устройство: {self.device}")
    
    def is_supported_file(self, file_path: str) -> bool:
        """Проверка поддерживаемого формата файла"""
        suffix = Path(file_path).suffix.lower()
        return suffix in self.SUPPORTED_IMAGE_FORMATS | self.SUPPORTED_PDF_FORMATS
    
    def _load_image(self, file_path: Path) -> Image.Image:
        """Загрузка изображения или PDF"""
        suffix = file_path.suffix.lower()
        
        if suffix in self.SUPPORTED_IMAGE_FORMATS:
            return Image.open(file_path).convert("RGB")
        
        elif suffix in self.SUPPORTED_PDF_FORMATS:
            # Конвертация первой страницы PDF в изображение
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            page = doc[0]
            
            # Рендер с высоким разрешением (300 DPI)
            mat = fitz.Matrix(300/72, 300/72)
            pix = page.get_pixmap(matrix=mat)
            
            # Конвертация в PIL Image
            img_data = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_data)).convert("RGB")
            
            doc.close()
            return image
        
        else:
            raise ValueError(f"Неподдерживаемый формат файла: {suffix}")
    
    def _count_pdf_pages(self, file_path: Path) -> int:
        """Подсчет страниц в PDF"""
        import fitz
        doc = fitz.open(file_path)
        page_count = len(doc)
        doc.close()
        return page_count
    
    def _process_single_image(self, image: Image.Image, task: str = "ocr") -> str:
        """Обработка одного изображения через PaddleOCR-VL"""
        orig_w, orig_h = image.size
        
        # Логика масштабирования из notebook
        spotting_upscale_threshold = 1500
        if task == "spotting" and orig_w < spotting_upscale_threshold and orig_h < spotting_upscale_threshold:
            image = image.resize(
                (orig_w * 2, orig_h * 2),
                Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
            )
        
        # Параметры обработки
        max_pixels = 2048 * 28 * 28 if task == "spotting" else 1280 * 28 * 28
        
        # Формирование сообщения
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": self.PROMPTS[task]},
                ]
            }
        ]
        
        # Подготовка входов
        inputs = self.processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            images_kwargs={
                "size": {
                    "shortest_edge": 28 * 28,
                    "longest_edge": max_pixels
                }
            },
        ).to(self.device)
        
        # Генерация текста
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=self.max_new_tokens
        )
        
        # Декодирование результата
        result = self.processor.decode(
            outputs[0][inputs["input_ids"].shape[-1]:-1]
        )
        
        return result.strip()
    
    async def process_file(self, file_path: str) -> Dict[str, Any]:
        """
        Универсальный метод обработки файла
        
        Returns:
            dict с результатами OCR
        """
        start_time = time.time()
        path = Path(file_path)
        suffix = path.suffix.lower()
        
        if suffix in self.SUPPORTED_PDF_FORMATS:
            # Обработка PDF - каждая страница отдельно
            import fitz
            doc = fitz.open(file_path)
            page_texts = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                mat = fitz.Matrix(300/72, 300/72)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_data)).convert("RGB")
                
                page_text = self._process_single_image(image, "ocr")
                page_texts.append(f"=== Страница {page_num + 1} ===\n{page_text}")
            
            doc.close()
            
            full_text = "\n\n".join(page_texts)
            page_count = len(page_texts)
            
        elif suffix in self.SUPPORTED_IMAGE_FORMATS:
            image = self._load_image(path)
            full_text = self._process_single_image(image, "ocr")
            page_count = 1
        
        else:
            raise ValueError(f"Неподдерживаемый формат файла: {suffix}")
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        return {
            "extracted_text": full_text,
            "confidence_score": None,
            "page_count": page_count,
            "processing_time_ms": processing_time_ms,
        }


# Глобальный экземпляр сервиса
ocr_service: PaddleOCRVLService | None = None


def get_ocr_service() -> PaddleOCRVLService:
    """Получение экземпляра сервиса (ленивая инициализация)"""
    global ocr_service
    if ocr_service is None:
        ocr_service = PaddleOCRVLService()
    return ocr_service
