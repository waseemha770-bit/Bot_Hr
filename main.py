import os
import threading
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# استيراد المكونات المقسمة والمحدثة من الملفات الأخرى
from models import init_db, SessionLocal, Employee, encrypt_data
from handlers import start, handle_message, handle_location, handle_document, handle_buttons, OWNER_PHONE, OWNER_CHAT_ID

# إعداد السجلات ومراقبة الأخطاء
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔑 التوكن الجديد والمحدث الخاص بك لحل مشكلة التعارض (Conflict) نهائياً
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8678088302:AAGric3vB8UQQ391f_u6_NP_zyQfgl1STdw")

class RenderHealthCheckServer(BaseHTTPRequestHandler):
    """خادم ويب مصغر للرد على فحص الحالة (Health Check) الخاص بمنصة Render لمنع الـ Timeout"""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"HR System Live with New Token and Advanced Features!")

def run_web_server():
    """تشغيل خادم الويب على المنفذ المطلوب من منصة Render"""
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), RenderHealthCheckServer)
    logger.info(f"Web health check active on port {port}")
    server.serve_forever()

def seed_initial_owner():
    """تأسيس حساب مالك النظام في قاعدة البيانات إذا لم يكن موجوداً"""
    db = SessionLocal()
    owner = db.query(Employee).filter(Employee.phone_number == OWNER_PHONE).first()
    if not owner:
        db.add(Employee(
            id="101", 
            name="وسيم حمدان (المالك)", 
            phone_number=OWNER_PHONE, 
            telegram_id=str(OWNER_CHAT_ID),
            role="Owner", 
            title="المدير التنفيذي", 
            encrypted_salary=encrypt_data("7500.0"), 
            vacation_balance=30
        ))
        db.commit()
    db.close()

def main():
    # 1. تهيئة جداول قاعدة البيانات والبيانات التأسيسية للمالك
    init_db()
    seed_initial_owner()
    
    # 2. تشغيل خادم الويب فوراً في الخلفية لمنع منصة Render من إغلاق السيرفر
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    # 3. بناء وتدشين تطبيق تليجرام بالتوكن الجديد
    application = Application.builder().token(TOKEN).build()
    
    # 4. تسجيل كافة دالات المعالجة (Handlers) الموزعة
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_buttons))
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # 5. بدء استقبال الرسائل من تليجرام بسلاسة ونظافة
    logger.info("Starting polling with the brand new API token...")
    application.run_polling()

if __name__ == '__main__':
    main()

