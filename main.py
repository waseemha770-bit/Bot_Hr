import os
import logging
import random
import math
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import pandas as pd
from sqlalchemy import create_engine, Column, String, Float, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# مكتبات التشفير وتوليد الـ PDF المتقدمة
from cryptography.fernet import Fernet
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# 1. الإعدادات وتأمين البيئة
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔑 التوكن الجديد والمحدث الذي أرسلته
TOKEN = "8678088302:AAGEH9d7Q3jOexuVB5W152yRA3JDZxu-BsY"
DATABASE_URL = "sqlite:///hr_enterprise_database.db"

# ✅ البيانات الثابتة وإحداثيات الشركة (نطاق 500 متر)
OWNER_PHONE = "+967771954200"
OWNER_CHAT_ID = 892385625  
COMPANY_LAT = 15.3562   
COMPANY_LON = 44.2075   
MAX_DISTANCE_METERS = 500.0  

# 🔒 مفتاح تشفير ثابت لبيانات الرواتب
STATIC_KEY = b'uF8gK3m_Xz9-v1WpQLr4TY7N2sEb6GcHvA1jD4xO5k8='
cipher_suite = Fernet(STATIC_KEY)

# 2. بناء بنية قاعدة البيانات
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Employee(Base):
    __tablename__ = "employees"
    id = Column(String, primary_key=True, index=True) 
    name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False, unique=True) 
    telegram_id = Column(String, nullable=True)   
    role = Column(String, default="Employee") 
    department = Column(String)
    title = Column(String)
    encrypted_salary = Column(String) 
    vacation_balance = Column(Integer, default=30)
    performance_review = Column(String, default="ممتاز")

class Attendance(Base):
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String, ForeignKey("employees.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    distance_from_company = Column(Float)
    status = Column(String) 

class VacationRequest(Base):
    __tablename__ = "vacation_requests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String, ForeignKey("employees.id"))
    vacation_type = Column(String) 
    days_count = Column(Integer)
    status = Column(String, default="قيد الانتظار ⏳") 
    created_at = Column(DateTime, default=datetime.utcnow)

class HR_Policy(Base):
    __tablename__ = "hr_policies"
    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword = Column(String, unique=True)
    response_text = Column(Text, nullable=False)

class HR_Ticket(Base):
    __tablename__ = "hr_tickets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String, ForeignKey("employees.id"))
    details = Column(Text)
    priority = Column(String, default="عادي") 
    status = Column(String, default="قيد المراجعة") 
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# 🛠️ دالات مساعدة
def encrypt_data(data: str) -> str:
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(data: str) -> str:
    try:
        if not data: return "0.0"
        return cipher_suite.decrypt(data.encode()).decode()
    except Exception as e:
        logger.error(f"Error decrypting data: {e}")
        return "0.0"

def calculate_distance(lat1, lon1, lat2, lon2) -> float:
    R = 6371000  
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def clean_and_format_yemeni_phone(raw_phone: str) -> str:
    cleaned = str(raw_phone).strip().replace(" ", "").split('.')[0]
    if cleaned.startswith("+967"): return cleaned
    if cleaned.startswith("967"): return "+" + cleaned
    if cleaned.startswith("0"): cleaned = cleaned[1:]
    return "+967" + cleaned

def generate_payslip_pdf(emp_name, emp_id, title, salary) -> str:
    filename = f"payslip_{emp_id}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, spaceAfter=20, alignment=1)
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontSize=12, spaceAfter=10)
    
    story = [
        Paragraph("<b>🏢 ENTERPRISE HR SYSTEM - OFFICIAL PAYSLIP</b>", title_style),
        Spacer(1, 15),
        Paragraph(f"<b>Employee Name:</b> {emp_name}", normal_style),
        Paragraph(f"<b>Employee ID:</b> {emp_id}", normal_style),
        Paragraph(f"<b>Job Title:</b> {title}", normal_style),
        Spacer(1, 10),
        Paragraph(f"<b>Net Salary:</b> ${float(salary):,.2f}", title_style),
        Spacer(1, 15),
        Paragraph(f"<i>Generated Securely via HR Bot on: {datetime.now().strftime('%Y-%m-%d')}</i>", normal_style)
    ]
    doc.build(story)
    return filename

def seed_enterprise_data():
    db = SessionLocal()
    owner_emp = db.query(Employee).filter(Employee.phone_number == OWNER_PHONE).first()
    if not owner_emp:
        new_owner = Employee(
            id="101", name="وسيم حمدان (المالك)", phone_number=OWNER_PHONE, telegram_id=str(OWNER_CHAT_ID),
            role="Owner", department="الإدارة العليا", title="مالك النظام والموارد", 
            encrypted_salary=encrypt_data("52000.0"), vacation_balance=30
        )
        db.add(new_owner)
    
    if not db.query(HR_Policy).first():
        db.add_all([
            HR_Policy(keyword="مرضية", response_text="🩺 السياسة الطبية: تمنح الشركة إجازة مرضية مدفوعة الأجر بالكامل لمدة تصل إلى 15 يوماً في السنة بشرط تقديم تقرير طبي معتمد."),
            HR_Policy(keyword="تأمين", response_text="🏥 التأمين الصحي: تغطية التأمين تشمل الموظف وعائلته بنسبة 100% وفق الفئة الفضية للمؤسسة.")
        ])
    db.commit()
    db.close()

sessions = {}

async def show_admin_menu(bot, chat_id):
    keyboard = [
        [InlineKeyboardButton("📊 تصدير البيانات الحاليّة إلى excel", callback_data="admin_export_import")],
        [InlineKeyboardButton("🗂️ تنظيم وإدارة المذكرات والشكاوى", callback_data="admin_manage_tickets")],
        [InlineKeyboardButton("📥 مراجعة طلبات الإجازات المعلقة", callback_data="admin_manage_vacations")]
    ]
    if chat_id == OWNER_CHAT_ID:
        keyboard.append([InlineKeyboardButton("👥 🛠️ إدارة صلاحيات المشرفين", callback_data="owner_manage_roles")])
        
    await bot.send_message(
        chat_id=chat_id,
        text="⚙️ **لوحة التحكم الإدارية للموارد البشرية:**\n*(ملاحظة: لتحديث بيانات الموظفين، قم برفع ملف الـ Excel الجديد مباشرة إلى الشات هنا)*",
        parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_employee_menu(bot, chat_id, employee_name):
    inline_keyboard = [
        [InlineKeyboardButton("💵 كشف الراتب الرقمي (PDF)", callback_data="emp_salary"), InlineKeyboardButton("📅 رصيد الإجازات الحالي", callback_data="emp_vacation")],
        [InlineKeyboardButton("✈️ تقديم طلب إجازة تفاعلي", callback_data="emp_request_vacation")],
        [InlineKeyboardButton("🎫 إرسال مذكرة / شكوى للمدير", callback_data="emp_ticket")],
        [InlineKeyboardButton("🚪 تسجيل الخروج الآمن", callback_data="emp_logout")]
    ]
    reply_keyboard = [[KeyboardButton(text="📍 تسجيل الحضور/الانصراف الجغرافي", request_location=True)]]
    
    await bot.send_message(
        chat_id=chat_id,
        text=f"🛡️ تم التحقق بنجاح من الهوية.\nمرحباً بك يا سيد: **{employee_name}**",
        parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    )
    await bot.send_message(chat_id=chat_id, text="📋 لوحة الخدمات الذاتية للموظف:", reply_markup=InlineKeyboardMarkup(inline_keyboard))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessions[chat_id] = {"step": "ASK_PHONE"}
    db = SessionLocal()
    current_user = db.query(Employee).filter(Employee.telegram_id == str(chat_id)).first()
    
    if chat_id == OWNER_CHAT_ID or (current_user and current_user.role in ["Owner", "Admin"]):
        await show_admin_menu(context.bot, chat_id)
    
    await update.message.reply_text(
        "🔒 بوابة الخدمات الذاتية المؤتمتة للموظفين.\n\nيرجى إدخال **رقم هاتفك** لبدء التحقق السريع (مثال: `771954200`):",
        parse_mode='Markdown', reply_markup=ReplyKeyboardRemove()
    )
    db.close()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip() if update.message.text else ""
    db = SessionLocal()
    
    if chat_id not in sessions: sessions[chat_id] = {"step": "ASK_PHONE"}
    step = sessions[chat_id].get("step")

    if step == "ASK_PHONE":
        formatted_phone = clean_and_format_yemeni_phone(text)
        employee = db.query(Employee).filter(Employee.phone_number == formatted_phone).first()
        
        if employee:
            otp_code = str(random.randint(100000, 999999))
            sessions[chat_id] = {"step": "ASK_OTP", "id": employee.id, "otp": otp_code}
            employee.telegram_id = str(chat_id)
            db.commit()
            
            await context.bot.send_message(chat_id=chat_id, text=f"🔐 **رمز التحقق الخاص بك هو:** `{otp_code}`", parse_mode='Markdown')
            await update.message.reply_text("📲 تم إرسال الرمز بنجاح. يرجى كتابته هنا:")
        else:
            policy = db.query(HR_Policy).filter(HR_Policy.keyword.like(f"%{text}%")).first()
            if policy:
                await update.message.reply_text(policy.response_text)
            else:
                await update.message.reply_text("❌ رقم هاتف غير مسجل، أو استفسار غير مفهوم.")

    elif step == "ASK_OTP":
        if text == sessions[chat_id]["otp"]:
            sessions[chat_id]["step"] = "AI_CHAT_MODE"
            employee = db.query(Employee).filter(Employee.id == sessions[chat_id]["id"]).first()
            await show_employee_menu(context.bot, chat_id, employee.name)
        else:
            await update.message.reply_text("❌ الرمز خاطئ.")

    elif step == "RAISE_TICKET":
        if "id" not in sessions[chat_id]:
            await update.message.reply_text("⚠️ انتهت صلاحية الجلسة، يرجى إرسال /start لتسجيل الدخول مجدداً.")
            db.close()
            return
        ticket = HR_Ticket(employee_id=sessions[chat_id]["id"], details=text)
        db.add(ticket)
        db.commit()
        sessions[chat_id]["step"] = "AI_CHAT_MODE"
        
        keyboard = [[InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data="back_to_emp_menu")]]
        await update.message.reply_text("✅ تم رفع مذكرتك للمدير بنجاح.", reply_markup=InlineKeyboardMarkup(keyboard))

    elif step == "INPUT_VACATION_DAYS":
        if "id" not in sessions[chat_id]:
            await update.message.reply_text("⚠️ انتهت صلاحية الجلسة، يرجى إرسال /start لتسجيل الدخول مجدداً.")
            db.close()
            return
        try:
            days = int(text)
            req = VacationRequest(employee_id=sessions[chat_id]["id"], vacation_type="إجازة اعتيادية سنوية", days_count=days)
            db.add(req)
            db.commit()
            
            await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=f"✈️ **طلب إجازة جديد معلق لـ:** {sessions[chat_id]['id']} ({days} أيام).")
            keyboard = [[InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data="back_to_emp_menu")]]
            await update.message.reply_text("✅ تم إرسال طلب الإجازة بنجاح.", reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            await update.message.reply_text("❌ يرجى إدخال رقم صحيح لعدد الأيام:")
        sessions[chat_id]["step"] = "AI_CHAT_MODE"

    db.close()

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db = SessionLocal()
    current_user = db.query(Employee).filter(Employee.telegram_id == str(chat_id)).first()
    
    if chat_id != OWNER_CHAT_ID and (not current_user or current_user.role not in ["Owner", "Admin"]):
        await update.message.reply_text("❌ عذراً، لا تمتلك الصلاحيات المطلوبة لتعديل ملفات النظام.")
        db.close()
        return

    doc = update.message.document
    if not doc.file_name.endswith('.xlsx') and not doc.file_name.endswith('.xls'):
        await update.message.reply_text("❌ يرجى رفع ملف بصيغة Excel الصحيحة فقط (تنتهي بـ .xlsx)")
        db.close()
        return

    await update.message.reply_text("⏳ جاري قراءة ملف الـ Excel وتحديث البيانات...")
    
    try:
        new_file = await context.bot.get_file(doc.file_id)
        file_path = "imported_hr_data.xlsx"
        await new_file.download_to_drive(file_path)
        
        df = pd.read_excel(file_path)
        required_columns = ["الرقم الوظيفي", "الاسم", "رقم الهاتف الدولي", "الصلاحية"]
        if not all(col in df.columns for col in required_columns):
            await update.message.reply_text("❌ فشل التحديث: بنية الجدول والتحقق داخل ملف الـ Excel غير متطابقة.")
            os.remove(file_path)
            db.close()
            return
            
        updated_count = 0
        inserted_count = 0
        
        for index, row in df.iterrows():
            emp_id = str(row["الرقم الوظيفي"]).split('.')[0].strip()
            emp_name = str(row["الاسم"]).strip()
            raw_phone = str(row["رقم الهاتف الدولي"])
            emp_phone = clean_and_format_yemeni_phone(raw_phone)
            emp_role = str(row["الصلاحية"]).strip() if pd.notna(row["الصلاحية"]) else "Employee"
            
            existing_emp = db.query(Employee).filter(Employee.id == emp_id).first()
            if existing_emp:
                existing_emp.name = emp_name
                existing_emp.phone_number = emp_phone
                existing_emp.role = emp_role
                updated_count += 1
            else:
                new_emp = Employee(id=emp_id, name=emp_name, phone_number=emp_phone, role=emp_role, encrypted_salary=encrypt_data("1000.0"))
                db.add(new_emp)
                inserted_count += 1
                
        db.commit()
        await update.message.reply_text(f"✅ **تم تحديث قاعدة بيانات الموظفين بالكامل!**\n\n🔄 الموظفين المحدثين: {updated_count}\n📥 الموظفين الجدد المضافين: {inserted_count}")
        os.remove(file_path)
        
    except Exception as e:
        logger.error(f"Error importing excel: {e}")
        await update.message.reply_text("❌ حدث خطأ داخلي أثناء معالجة وقراءة ملف الإكسل.")
    finally:
        db.close()

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db = SessionLocal()
    if chat_id not in sessions or "id" not in sessions[chat_id]:
        await update.message.reply_text("🔒 انتهت صلاحية الجلسة، يرجى كتابة رقم هاتفك لتسجيل الدخول أولاً.")
        db.close()
        return
        
    user_lat = update.message.location.latitude
    user_lon = update.message.location.longitude
    distance = calculate_distance(user_lat, user_lon, COMPANY_LAT, COMPANY_LON)
    
    if distance <= MAX_DISTANCE_METERS:
        status = "مقبول ✅"
        msg = f"✅ **تم الحضور بنجاح!**\n📏 البعد عن الشركة: **{distance:.1f} متر**."
    else:
        status = "مرفوض ❌"
        msg = f"❌ **فشل تسجيل الحضور!**\n📏 البعد عن الشركة: **{distance/1000:.2f} كم** (المسموح 500 متر)."
        
    db.add(Attendance(employee_id=sessions[chat_id]["id"], distance_from_company=distance, status=status))
    db.commit()
    db.close()
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    await query.answer()
    db = SessionLocal()
    
    if query.data == "back_to_admin_menu":
        await query.message.delete()
        await show_admin_menu(context.bot, chat_id)
        db.close()
        return
    elif query.data == "back_to_emp_menu":
        await query.message.delete()
        if chat_id in sessions and "id" in sessions[chat_id]:
            employee = db.query(Employee).filter(Employee.id == sessions[chat_id]["id"]).first()
            if employee:
                await show_employee_menu(context.bot, chat_id, employee.name)
        db.close()
        return

    if query.data.startswith("emp_"):
        if chat_id not in sessions or "id" not in sessions[chat_id]:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ **انتهت صلاحية الجلسة بسبب تحديث النظام.**\n\nيرجى إدخال رقم الهاتف مجدداً.")
            sessions[chat_id] = {"step": "ASK_PHONE"}
            db.close()
            return

        employee = db.query(Employee).filter(Employee.id == sessions[chat_id]["id"]).first()
        if not employee:
            await context.bot.send_message(chat_id=chat_id, text="❌ لم يتم العثور على بياناتك.")
            db.close()
            return
        
        if query.data == "emp_salary":
            decrypted_sal = decrypt_data(employee.encrypted_salary)
            pdf_path = generate_payslip_pdf(employee.name, employee.id, employee.title or "موظف", decrypted_sal)
            with open(pdf_path, "rb") as file:
                await context.bot.send_document(chat_id=chat_id, document=file, filename=f"Payslip_{employee.id}.pdf")
            os.remove(pdf_path)
        elif query.data == "emp_vacation":
            kb = [[InlineKeyboardButton("↩️ رجوع", callback_data="back_to_emp_menu")]]
            await query.message.reply_text(f"📅 رصيدك المتاح: **{employee.vacation_balance} يوماً**.", reply_markup=InlineKeyboardMarkup(kb))
        elif query.data == "emp_request_vacation":
            sessions[chat_id]["step"] = "INPUT_VACATION_DAYS"
            await query.message.reply_text("✈️ كم عدد أيام الإجازة المطلوبة؟")
        elif query.data == "emp_ticket":
            sessions[chat_id]["step"] = "RAISE_TICKET"
            await query.message.reply_text("📝 اكتب تفاصيل مذكرتك ومطالبك حالياً في رسالة نصية واحدة:")
        elif query.data == "emp_logout":
            sessions[chat_id] = {"step": "ASK_PHONE"}
            await query.message.reply_text("🔒 تم تسجيل الخروج بنجاح.", reply_markup=ReplyKeyboardRemove())

    elif query.data.startswith("admin_"):
        if query.data == "admin_export_import":
            employees = db.query(Employee).all()
            data = [{"الرقم الوظيفي": e.id, "الاسم": e.name, "رقم الهاتف الدولي": e.phone_number, "الصلاحية": e.role} for e in employees]
            df = pd.DataFrame(data)
            df.to_excel("hr_report.xlsx", index=False)
            kb = [[InlineKeyboardButton("↩️ رجوع للقائمة", callback_data="back_to_admin_menu")]]
            with open("hr_report.xlsx", "rb") as file:
                await context.bot.send_document(chat_id=chat_id, document=file, filename="بيانات_الموظفين.xlsx", reply_markup=InlineKeyboardMarkup(kb))
            os.remove("hr_report.xlsx")
            
        elif query.data == "admin_manage_vacations":
            reqs = db.query(VacationRequest).filter(VacationRequest.status == "قيد الانتظار ⏳").all()
            if not reqs:
                kb = [[InlineKeyboardButton("↩️ رجوع", callback_data="back_to_admin_menu")]]
                await query.message.reply_text("✅ لا توجد طلبات إجازة معلقة.", reply_markup=InlineKeyboardMarkup(kb))
                db.close()
                return
            for r in reqs:
                kb = [[InlineKeyboardButton("موافقة ✅", callback_data=f"vac_approve_{r.id}"), InlineKeyboardButton("رفض ❌", callback_data=f"vac_reject_{r.id}")]]
                kb.append([InlineKeyboardButton("↩️ رجوع", callback_data="back_to_admin_menu")])
                await query.message.reply_text(f"✈️ طلب إجازة للموظف {r.employee_id} لمدة {r.days_count} أيام.", reply_markup=InlineKeyboardMarkup(kb))

        elif query.data == "admin_manage_tickets":
            tickets = db.query(HR_Ticket).filter(HR_Ticket.status == "قيد المراجعة").all()
            if not tickets:
                kb = [[InlineKeyboardButton("↩️ رجوع للقائمة الرئيسية", callback_data="back_to_admin_menu")]]
                await query.message.reply_text("🗂️ لا توجد مذكرات أو شكاوى معلقة بحاجة لمراجعة المالك حالياً.", reply_markup=InlineKeyboardMarkup(kb))
                db.close()
                return
            for t in tickets:
                kb = [[InlineKeyboardButton("إغلاق المذكرة (تم الحل) ✅", callback_data=f"tic_close_{t.id}")]]
                kb.append([InlineKeyboardButton("↩️ رجوع", callback_data="back_to_admin_menu")])
                await query.message.reply_text(f"🎫 **مذكرة من موظف برقم {t.employee_id}:**\n\n📝 التفاصيل:\n{t.details}", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

    elif query.data.startswith("tic_"):
        parts = query.data.split("_")
        action = parts[1]
        tic_id = int(parts[2])
        ticket = db.query(HR_Ticket).filter(HR_Ticket.id == tic_id).first()
        if ticket and action == "close":
            ticket.status = "تم الحل والمراجعة ✅"
            db.commit()
            kb = [[InlineKeyboardButton("↩️ رجوع للقائمة", callback_data="back_to_admin_menu")]]
            await query.message.reply_text("✅ تم أرشفة الشكوى بنجاح.", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data.startswith("vac_"):
        parts = query.data.split("_")
        action = parts[1]
        req_id = int(parts[2])
        req = db.query(VacationRequest).filter(VacationRequest.id == req_id).first()
        if req:
            emp = db.query(Employee).filter(Employee.id == req.employee_id).first()
            if action == "approve":
                req.status = "مقبولة ✅"
                if emp: emp.vacation_balance -= req.days_count
                msg = "✅ تم قبول الطلب وخصم الأيام تلقائياً."
            else:
                req.status = "مرفوضة ❌"
                msg = "❌ تم رفض طلب الإجازة."
            db.commit()
            kb = [[InlineKeyboardButton("↩️ رجوع للمدير", callback_data="back_to_admin_menu")]]
            await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))

    db.close()

# 🌐 خادم الويب المدمج لربط الـ Port في Render ومنع الـ Timeout
class DummyWebServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"HR Enterprise Bot is online and healthy!")

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), DummyWebServer)
    logger.info(f"Web server active on port {port}")
    server.serve_forever()

def main():
    seed_enterprise_data()
    
    # تشغيل خادم الويب في خلفية السكربت لربط المنفذ بنجاح
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    # بدء اتصال البوت بنظام Polling
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_buttons))
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.run_polling()

if __name__ == '__main__':
    main()
