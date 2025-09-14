from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import sqlite3
from datetime import datetime
import logging
import time  # Для имитации задержки

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FSSP-Tracker MVP", version="1.0")

# --- Модель Pydantic для входящих данных ---
class DebtorIn(BaseModel):
    debtor_name: str
    debtor_dob: str  # "1980-01-01"
    ip_number: Optional[str] = None
    client_id: str  # ID из CRM

# --- Модель для ответа ---
class CheckResult(BaseModel):
    status: str
    message: str
    debtor_name: str
    ip_number: Optional[str] = None

# --- Инициализация SQLite БД ---
def init_db():
    """Функция для создания базы данных и таблицы"""
    try:
        conn = sqlite3.connect('fsps.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS debtors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                debtor_name TEXT NOT NULL,
                debtor_dob TEXT NOT NULL,
                ip_number TEXT,
                status TEXT DEFAULT 'Не проверен',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ База данных SQLite инициализирована")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании БД: {e}")

init_db()

# --- Имитация внешних сервисов ---
class MockServices:
    """Класс для имитации работы с внешними API"""
    
    @staticmethod
    def mock_fssp_check(ip_number: str) -> str:
        """
        Имитация запроса к платному агрегатору данных ФССП.
        В реальности здесь был бы HTTP-запрос к API.
        """
        logger.info(f"🔍 Имитация запроса к агрегатору ФССП для ИП: {ip_number}")
        
        # Имитируем задержку сети 1-2 секунды
        time.sleep(1.5)
        
        # Простая логика для определения статуса
        if ip_number and "123" in ip_number:
            return "Исполнено"
        elif ip_number and "456" in ip_number:
            return "Прекращено"
        elif ip_number:
            return "Исполняется"
        else:
            return "Не найден"

    @staticmethod
    def send_to_crm(client_id: str, status: str):
        """Имитация обновления статуса в CRM (например, Bitrix24)"""
        logger.info(f"📊 Имитация вызова CRM: Клиент {client_id} -> Статус {status}")
        # Здесь был бы REST API запрос к CRM:
        # requests.post('https://crm.ru/webhook', json={'client_id': client_id, 'status': status})

    @staticmethod
    def send_to_bot(phone: str, message: str):
        """Имитация вызова API бот-платформы (Aimylogic)"""
        logger.info(f"🤖 Имитация вызова бота: На номер {phone} -> {message}")
        # Здесь был бы запрос к API бот-платформы:
        # requests.post('https://aimylogic.com/api/send', json={'phone': phone, 'text': message})

# --- Основной endpoint для проверки статуса ---
@app.post("/check-status/", response_model=CheckResult)
async def check_fssp_status(debtor: DebtorIn, background_tasks: BackgroundTasks):
    """
    Основной endpoint для проверки статуса исполнительного производства.
    Интегрируется с CRM и бот-платформой через фоновые задачи.
    """
    try:
        logger.info(f"📥 Получен запрос на проверку для: {debtor.debtor_name}")
        
        # 1. Сохраняем запрос в БД
        conn = sqlite3.connect('fsps.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO debtors (client_id, debtor_name, debtor_dob, ip_number)
            VALUES (?, ?, ?, ?)
        ''', (debtor.client_id, debtor.debtor_name, debtor.debtor_dob, debtor.ip_number))
        conn.commit()
        conn.close()

        # 2. Имитируем запрос к агрегатору ФССП
        fssp_status = MockServices.mock_fssp_check(debtor.ip_number)

        # 3. Обновляем статус в БД
        conn = sqlite3.connect('fsps.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE debtors SET status = ? WHERE client_id = ?
        ''', (fssp_status, debtor.client_id))
        conn.commit()
        conn.close()

        # 4. Запускаем фоновые задачи для интеграций
        background_tasks.add_task(MockServices.send_to_crm, debtor.client_id, fssp_status)
        
        # Если долг исполнен, "отправляем" уведомление в бот
        if fssp_status == "Исполнено":
            background_tasks.add_task(
                MockServices.send_to_bot, 
                "+79991234567", # Здесь был бы номер из CRM
                f"Долг по ИП {debtor.ip_number} исполнен. Сумма: 150000 руб."
            )

        return CheckResult(
            status="success",
            message=f"Проверка завершена. Статус: {fssp_status}",
            debtor_name=debtor.debtor_name,
            ip_number=debtor.ip_number
        )

    except Exception as e:
        logger.error(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

# --- GET методы для тестирования ---
@app.get("/add-test-debtor/")
async def add_test_debtor_get():
    """Добавляет тестовую запись в базу данных"""
    try:
        conn = sqlite3.connect('fsps.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO debtors (client_id, debtor_name, debtor_dob, ip_number, status)
            VALUES (?, ?, ?, ?, ?)
        ''', ('test_client_1', 'Иванов Иван Иванович', '1980-01-01', '12345/20/123456-ИП', 'Не проверен'))
        
        conn.commit()
        conn.close()
        
        return {"message": "✅ Тестовая запись добавлена в базу данных"}
    
    except Exception as e:
        return {"error": str(e)}

@app.get("/debtors/")
async def get_all_debtors():
    """Просмотр всех записей в базе данных"""
    try:
        conn = sqlite3.connect('fsps.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM debtors")
        rows = cursor.fetchall()
        conn.close()
        
        debtors = []
        for row in rows:
            debtors.append({
                "id": row[0],
                "client_id": row[1],
                "debtor_name": row[2],
                "debtor_dob": row[3],
                "ip_number": row[4],
                "status": row[5],
                "created_at": row[6]
            })
        
        return {"debtors": debtors}
    
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
async def root():
    return {"message": "FSSP-Tracker MVP работает! Перейдите на /docs для тестирования."}