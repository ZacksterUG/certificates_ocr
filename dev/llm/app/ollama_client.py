"""
Ollama клиент для структурирования текста сертификатов

Извлекает из сырого текста:
- Название мероприятия/курса
- Организация
- Дата выдачи
- ФИО получателя
- Тип достижения
"""

import json
import logging
from typing import Optional, Dict, Any

import ollama
from ollama import ResponseError

from app.database import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)


# Промпт для извлечения структурированных данных
STRUCTURE_PROMPT = """
Ты — профессиональный экстрактор данных из студенческих сертификатов, грамот и дипломов.
Твоя задача — извлечь ВСЕ доступные поля из текста и вернуть СТРОГО валидный JSON.

### ВАЖНЫЕ ПРАВИЛА:
1. Возвращай ТОЛЬКО JSON без markdown, без пояснений, без ```json
2. Если поле не найдено — укажи null (не пропускай поля!)
3. Исправляй очевидные ошибки OCR (повторы слов, опечатки, разрывы)
4. ФИО приводи к именительному падежу если возможно
5. Даты приводи к формату YYYY-MM-DD
6. Оценивай уверенность извлечения (0.0-1.0)
7. Определяй язык документа (ru/en/mixed)

### КРИТИЧЕСКИ ВАЖНЫЕ ПОЛЯ:

#### 1. personal_data
- full_name: ФИО в именительном падеже ("Сальков Михаил Сергеевич")
- full_name_raw: ФИО как в документе ("Салькову Михаилу Сергеевичу")
- is_team: true если награждается команда (ACM ICPC, хоккей, хор и т.д.)
- team_name: название команды ("La squadra", "Политехник", "Deep Vision")
- team_members: массив ФИО участников команды если указаны
- course: курс обучения ("3 курс", "1-го курса", "студент группы АС-322")
- group: учебная группа ("СГ-306", "ЭУ-354", "КТУР-401")
- university: вуз получателя ("ЮУрГУ", "МГУ", "Samara State Technical University")
- faculty: факультет/институт ("Факультет Экономики", "Архитектурно-строительный институт")
- educational_level: бакалавриат|специалитет|магистратура|аспирантура|другое

#### 2. document_info
- doc_type: диплом|грамота|сертификат|свидетельство|благодарность|дипломный лист|удостоверение|другое
- doc_number: номер документа ("NePS-D2e-012", "21 Х002423056")
- doc_degree: I степени|II степени|III степени|Third degree|null
- issue_date: дата выдачи в YYYY-MM-DD
- year: год проведения (число 4 цифры)
- city: город проведения
- country: страна (по умолчанию "Россия" для русских документов)
- language: ru|en|mixed

#### 3. event_info
- event_name: полное название мероприятия
- event_type: конференция|олимпиада|фестиваль|соревнования|конкурс|турнир|смена|форум|чемпионат|другое
- event_level: вузовский|региональный|всероссийский|международный
- edition: номер/версия ("68-я", "X", "VII", "II тур", "4 этап")
- nomination: номинация ("Шрифты", "Уличный танец", "Технические науки")
- section: секция конференции ("Защита информации", "Экономика и управление")
- direction: направление/профиль ("Строительство", "предпринимательства и менеджмента")

#### 4. achievement
- has_place: boolean, есть ли призовое место
- place_number: число (1, 2, 3) или null
- place_text: как написано ("1 место", "І место", "Third degree", "ПЕРВОЕ место")
- degree: степень диплома ("I степени", "II степени", "Third degree")
- prize_name: название приза ("специальный приз «Дебют сезона»", "лучший доклад")
- result_details: конкретные результаты ("230 КГ", "4x400м", "157.53 очк WILKS", "4.34.0", "127,5 KG")
- category: категория ("до 83 КГ", "девушки", "младшие курсы", "JUNIOR", "W/C: 67,5 KG")
- is_participant_only: true если только участие без призового места

#### 5. work_info
- work_title: название работы/проекта/доклада (в кавычках если есть)
- work_type: ВКР|курсовой проект|научная работа|доклад|проект|исследование|статья|другое
- isbn: ISBN если указан ("978-5-906G26-52-3")
- scientific_supervisor: ФИО научного руководителя
- supervisor_degree: учёная степень ("к.э.н.", "д-р ист. наук", "профессор", "к.т.н., доцент")

#### 6. organization
- primary_org: основной организатор ("ЮУрГУ", "Финансовый университет", "Society of Bulgarian Tribologists")
- partner_orgs: массив партнёрских организаций
- sponsors: массив спонсоров ("Яндекс", "СКБ КОНТУР", "МТС", "Райфайзенбанк", "EY")
- university_org: вуз организатор если отличается от primary_org

#### 7. signatories
- Массив объектов с полями:
- position: должность ("Председатель жюри", "Ректор", "Декан", "Научный руководитель центра")
- name: ФИО подписанта
- degree: учёная степень если указана
- signature_present: true если есть подпись/инициалы

#### 8. metadata
- needs_review: true если есть проблемы с извлечением
- review_reason: причина для проверки
- confidence: уверенность извлечения (0.0-1.0)
- ocr_quality: high|medium|low
- ocr_issues: массив проблем OCR (["повторы слов", "разрывы строк", "смешение регистров", "ошибки распознавания"])
- extraction_notes: дополнительные заметки

### ТИПИЧНЫЕ ОШИБКИ OCR ДЛЯ ИСПРАВЛЕНИЯ:
- "олимпияды" → "олимпиады"
- "НАТРАЖДАЕТСЯ" → "НАГРАЖДАЕТСЯ"
- "учасив" → "участие"
- "Гомельск" × 40 раз → удалить повторы
- "специ альный" → "специальный"
- "внеуч ебной" → "внеучебной"
- "амлепике" → "атлетике"
- "мемров" → "метров"
- "областной" × 40 раз → удалить повторы
- "смуденческой" → "студенческой"
- "ъжъэ" (кракозябры) → пропустить

### ПРИМЕРЫ КОМАНДНЫХ СЕРТИФИКАТОВ:
- ACM ICPC: команда + список участников + coach
- Хоккей: команда + список игроков + даты рождения
- Хоры/танцы: коллектив + руководитель + участники

### ТЕКСТ ДОКУМЕНТА:
"100+ FORUM RUSSIA\nГОРДЕЕВА\nМАРИЯ ПЕТРОВНА\nСТУДЕНТ\nЮУРГУ\nУЧАСТНИК"
### ОТВЕТ (ТОЛЬКО JSON):

"""


class OllamaClient:
    """Клиент для работы с Ollama API"""
    
    def __init__(self):
        self.host = OLLAMA_HOST
        self.model = OLLAMA_MODEL
        self.timeout = OLLAMA_TIMEOUT
        
        logger.info(f"🤖 Ollama клиент инициализирован: {self.host}, модель: {self.model}")
    
    async def check_connection(self) -> bool:
        """Проверка подключения к Ollama"""
        try:
            client = ollama.AsyncClient(host=self.host, timeout=self.timeout)
            await client.list()
            logger.info("✅ Подключение к Ollama успешно")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Ollama: {e}")
            return False
    
    async def structure_certificate(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """
        Структурирование сырого текста сертификата
        
        Args:
            raw_text: Текст из OCR
            
        Returns:
            Dict со структурированными данными или None при ошибке
        """
        try:
            client = ollama.AsyncClient(host=self.host, timeout=self.timeout)
            
            # Формирование промпта
            prompt = STRUCTURE_PROMPT.format(text=raw_text)
            
            # Запрос к модели
            response = await client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                options={
                    "temperature": 0.1,  # Низкая температура для детерминированности
                    "top_p": 0.9,
                }
            )
            
            # Извлечение ответа
            result_text = response["message"]["content"].strip()
            logger.info(f"📝 Ответ модели: {result_text[:200]}...")
            
            # Парсинг JSON из ответа
            structured_data = self._parse_json_response(result_text)
            
            if structured_data:
                # Валидация полей
                structured_data = self._validate_structure(structured_data)
                logger.info("✅ Данные структурированы успешно")
            
            return structured_data
            
        except ResponseError as e:
            logger.error(f"❌ Ollama API error: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка структурирования: {e}", exc_info=True)
            return None
    
    def _parse_json_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Парсинг JSON из текстового ответа"""
        # Поиск JSON в тексте (может быть обрамлен markdown)
        import re
        
        # Удаляем markdown code blocks если есть
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        
        # Поиск JSON объекта
        json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if json_match:
            text = json_match.group()
        
        try:
            data = json.loads(text)
            return data
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            logger.error(f"Текст для парсинга: {text}")
            return None
    
    def _validate_structure(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация и нормализация структурированных данных"""
        valid_types = {"olympiad", "course", "conference", "workshop", "competition", "other"}
        
        result = {
            "event_name": data.get("event_name"),
            "organization": data.get("organization"),
            "issue_date": data.get("issue_date"),
            "recipient_name": data.get("recipient_name"),
            "achievement_type": data.get("achievement_type", "other"),
        }
        
        # Валидация типа достижения
        if result["achievement_type"] not in valid_types:
            result["achievement_type"] = "other"
        
        return result


# Глобальный экземпляр
ollama_client: Optional[OllamaClient] = None


def get_ollama_client() -> OllamaClient:
    """Получение экземпляра клиента"""
    global ollama_client
    if ollama_client is None:
        ollama_client = OllamaClient()
    return ollama_client
