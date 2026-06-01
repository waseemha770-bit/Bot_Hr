import sys
import os
import subprocess

# حل مشكلة تعارض pandas و openpyxl برمجياً وتجاوز كاش السيرفر
try:
    import openpyxl
    # إذا كان الإصدار المثبت قديم، يتم تحديثه إجبارياً فور تشغيل السيرفر
    if openpyxl.__version__ < '3.1.5':
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl>=3.1.5"])
        # إعادة تشغيل السكريبت تلقائياً لتطبيق الإصدار الجديد في نفس اللحظة
        os.execv(sys.executable, ['python'] + sys.argv)
except Exception as e:
    print(f"تنبيه تحديث المكتبات: {e}")

# -------------------------------------------------------------
# هنا يبدأ كود البوت الخاص بك كما هو دون أي تغيير:
import pandas as pd
# بقية الـ imports والأوامر الخاصة بالبوت...

import os
import threading
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from models import init_db, SessionLocal, Employee, encrypt_data
from handlers import start, handle_message, handle_location, handle_document, handle_buttons, OWNER_PHONE, OWNER_CHAT_ID

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔑 التوكن الجديد المحدث مباشرة في الكود
TOKEN = os.environ.get("TELEGRAM_TOKEN", "BOT_TOKEN")

class RenderHealthCheckServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"HR System Live with Active Token!")

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), RenderHealthCheckServer)
    logger.info(f"Web health check active on port {port}")
    server.serve_forever()

def seed_initial_owner():
    db = SessionLocal()
    owner = db.query(Employee).filter(Employee.phone_number == OWNER_PHONE).first()
    if not owner:
        db.add(Employee(
            id="101", name="وسيم حمدان (المالك)", phone_number=OWNER_PHONE, telegram_id=str(OWNER_CHAT_ID),
            role="Owner", title="المدير التنفيذي", encrypted_salary=encrypt_data("7500.0"), vacation_balance=30
        ))
        db.commit()
    db.close()

def main():
    init_db()
    seed_initial_owner()
    
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_buttons))
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Starting polling with the active authorized token...")
    application.run_polling()

if __name__ == '__main__':
    main()

