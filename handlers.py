import os
import random
import logging
import pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from models import SessionLocal, Employee, Attendance, VacationRequest, HR_Policy, HR_Ticket, encrypt_data, decrypt_data
from utils import calculate_distance, clean_and_format_yemeni_phone, generate_payslip_pdf

logger = logging.getLogger(__name__)

OWNER_PHONE = "+967771954200"
OWNER_CHAT_ID = 892385625
COMPANY_LAT = 15.3562
COMPANY_LON = 44.2075
MAX_DISTANCE_METERS = 500.0

sessions = {}

async def show_admin_menu(bot, chat_id):
    # 🛠️ تم توحيد مسميات الـ Callback Data وإضافة زر الصلاحيات الجديد هنا
    keyboard = [
        [
            InlineKeyboardButton("📤 تصدير", callback_data="admin_export_excel"),
            InlineKeyboardButton("📥 إستيراد", callback_data="admin_import_trigger")
        ],
        [InlineKeyboardButton("🗂️ تنظيم وإدارة المذكرات والشكاوى", callback_data="admin_manage_tickets")],
        [InlineKeyboardButton("📥 مراجعة طلبات الإجازات المعلقة", callback_data="admin_manage_vacations")],
        [InlineKeyboardButton("🔑 إدارة منح وسحب الصلاحيات", callback_data="admin_manage_roles")],
        [InlineKeyboardButton("🧹 تنظيف الشاشة والعودة للبداية", callback_data="clear_and_restart")]
    ]
    await bot.send_message(
        chat_id=chat_id,
        text="⚙️ **لوحة التحكم الإدارية لنظام الموارد البشرية:**\nاختر الإجراء المطلوب من الأزرار أدناه:",
        parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_employee_menu(bot, chat_id, employee_name):
    inline_keyboard = [
        [InlineKeyboardButton("💵 كشف الراتب الرقمي (PDF)", callback_data="emp_salary"), InlineKeyboardButton("📅 رصيد الإجازات الحالي", callback_data="emp_vacation")],
        [InlineKeyboardButton("✈️ تقديم طلب إجازة تفاعلي", callback_data="emp_request_vacation")],
        [InlineKeyboardButton("🎫 إرسال مذكرة / شكوى للمدير", callback_data="emp_ticket")],
        [InlineKeyboardButton("🧹 تنظيف الشاشة والعودة للبداية", callback_data="clear_and_restart")]
    ]
    reply_keyboard = [[KeyboardButton(text="📍 تسجيل الحضور/الانصراف الجغرافي", request_location=True)]]
    await bot.send_message(chat_id=chat_id, text=f"🛡️ مرحباً بك يا سيد: **{employee_name}**", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    await bot.send_message(chat_id=chat_id, text="📋 لوحة الخدمات الذاتية للموظف:", reply_markup=InlineKeyboardMarkup(inline_keyboard))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessions[chat_id] = {"step": "ASK_PHONE"}
    db = SessionLocal()
    current_user = db.query(Employee).filter(Employee.telegram_id == str(chat_id)).first()
    
    if chat_id == OWNER_CHAT_ID or (current_user and current_user.role in ["Owner", "Admin"]):
        await show_admin_menu(context.bot, chat_id)
        db.close()
        return
    
    await update.message.reply_text(
        "🔒 بوابة الخدمات الذاتية الذكية للموظفين.\n\nيرجى إدخال **رقم هاتفك** للتحقق الآمن (مثال: `771954200`):", 
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
            await context.bot.send_message(chat_id=chat_id, text=f"🔐 **رمز التحقق المؤقت (OTP) هو:** `{otp_code}`", parse_mode='Markdown')
            await update.message.reply_text("📲 يرجى إدخال رمز التحقق هنا:")
        else:
            policy = db.query(HR_Policy).filter(HR_Policy.keyword.like(f"%{text}%")).first()
            if policy:
                await update.message.reply_text(policy.response_text)
            else:
                await update.message.reply_text("❌ عذراً، رقم الهاتف غير مسجل بالنظام أو لم أفهم استفسارك.")

    elif step == "ASK_OTP":
        if text == sessions[chat_id]["otp"]:
            sessions[chat_id]["step"] = "AI_CHAT_MODE"
            employee = db.query(Employee).filter(Employee.id == sessions[chat_id]["id"]).first()
            await show_employee_menu(context.bot, chat_id, employee.name)
        else:
            await update.message.reply_text("❌ الرمز غير صحيح، حاول مجدداً.")

    elif step == "RAISE_TICKET":
        ticket = HR_Ticket(employee_id=sessions[chat_id]["id"], details=text)
        db.add(ticket)
        db.commit()
        sessions[chat_id]["step"] = "AI_CHAT_MODE"
        await update.message.reply_text("✅ تم رفع مذكرتك بنجاح وجاري مراجعتها من قبل الإدارة.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة الرئيسية", callback_data="back_to_emp_menu")]]))

    elif step == "INPUT_VACATION_DAYS":
        try:
            days = int(text)
            req = VacationRequest(employee_id=sessions[chat_id]["id"], vacation_type="إجازة اعتيادية", days_count=days)
            db.add(req)
            db.commit()
            await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=f"⚠️ **طلب إجازة جديد معلق:**\nالموظف برقم: {sessions[chat_id]['id']} طلب {days} أيام إجازة.")
            await update.message.reply_text("✅ تم إرسال طلبك للإدارة، وسيتم إشعارك فور اتخاذ القرار.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة الرئيسية", callback_data="back_to_emp_menu")]]))
        except ValueError:
            await update.message.reply_text("❌ يرجى إدخال عدد أيام صحيح (أرقام فقط):")
        sessions[chat_id]["step"] = "AI_CHAT_MODE"

    elif step == "WAITING_FOR_EXCEL_IMPORT":
        await update.message.reply_text("⚠️ يرجى رفع ملف إكسيل حقيقي ينتهي بـ `.xlsx` بدلاً من الرسالة النصية، أو اضغط على إلغاء.")

    db.close()

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db = SessionLocal()
    if chat_id not in sessions or "id" not in sessions[chat_id]:
        await update.message.reply_text("🔒 يرجى تسجيل الدخول أولاً.")
        db.close()
        return
        
    user_lat = update.message.location.latitude
    user_lon = update.message.location.longitude
    distance = calculate_distance(user_lat, user_lon, COMPANY_LAT, COMPANY_LON)
    
    if distance <= MAX_DISTANCE_METERS:
        status = "مقبول ✅"
        msg = f"✅ **تم تسجيل حضورك بنجاح!**\n📏 البعد عن النطاق الجغرافي للمؤسسة: **{distance:.1f} متر**."
    else:
        status = "مرفوض ❌"
        msg = f"❌ **فشل الحضور الجغرافي!**\n📏 أنت على بعد **{distance/1000:.2f} كم** (النطاق المسموح به 500 متر فقط)."
        
    db.add(Attendance(employee_id=sessions[chat_id]["id"], distance_from_company=distance, status=status))
    db.commit()
    db.close()
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db = SessionLocal()
    current_user = db.query(Employee).filter(Employee.telegram_id == str(chat_id)).first()
    
    if chat_id != OWNER_CHAT_ID and (not current_user or current_user.role not in ["Owner", "Admin"]):
        await update.message.reply_text("❌ صلاحيات غير كافية لرفع تعديلات الهيكل التنظيمي.")
        db.close()
        return

    if chat_id in sessions and sessions[chat_id].get("step") != "WAITING_FOR_EXCEL_IMPORT":
        await update.message.reply_text("⚠️ يرجى الضغط على زر 'إستيراد' أولاً من لوحة التحكم قبل رفع الملف لتهيئة النظام.")
        db.close()
        return

    doc = update.message.document
    if not doc.file_name.lower().endswith(('.xlsx', '.xls')):
        await update.message.reply_text("❌ يرجى رفع ملف بصيغة إكسيل فقط تنتهي بـ .xlsx")
        db.close()
        return

    await update.message.reply_text("⏳ جاري قراءة وتدقيق ملف البيانات الجديد واستيراده...")
    try:
        new_file = await context.bot.get_file(doc.file_id)
        file_path = "imported_hr_data.xlsx"
        await new_file.download_to_drive(file_path)
        
        # قراءة مع تنظيف كامل للمسافات المخفية في العناوين لتفادي الأخطاء البنيوية
        df = pd.read_excel(file_path, dtype=str)
        df.columns = [str(col).strip() for col in df.columns]
        
        updated_count = 0
        inserted_count = 0
        
        for index, row in df.iterrows():
            if "الرقم الوظيفي" not in row or pd.isna(row["الرقم الوظيفي"]) or str(row["الرقم الوظيفي"]).strip() == "": 
                continue
                
            emp_id = str(row["الرقم الوظيفي"]).split('.')[0].strip()
            emp_name = str(row["الاسم"]).strip() if "الاسم" in row else "غير معروف"
            emp_phone = clean_and_format_yemeni_phone(row["رقم الهاتف الدولي"]) if "رقم الهاتف الدولي" in row else ""
            emp_role = str(row["الصلاحية"]).strip() if ("الصلاحية" in row and pd.notna(row["الصلاحية"])) else "Employee"
            
            existing = db.query(Employee).filter(Employee.id == emp_id).first()
            if existing:
                existing.name = emp_name
                existing.phone_number = emp_phone
                existing.role = emp_role
                updated_count += 1
            else:
                db.add(Employee(id=emp_id, name=emp_name, phone_number=emp_phone, role=emp_role, encrypted_salary=encrypt_data("1200.0"), vacation_balance=30))
                inserted_count += 1
                
        db.commit()
        sessions[chat_id]["step"] = "AI_CHAT_MODE"
        await update.message.reply_text(f"✅ **تم الإستيراد وتحديث قاعدة البيانات بنجاح!**\n📥 الحسابات الجديدة: {inserted_count}\n🔄 الحسابات المحدثة: {updated_count}")
        if os.path.exists(file_path): os.remove(file_path)
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ حدث خطأ بنيوي أثناء معالجة خلايا الإكسل الحالية. تأكد من مطابقة أسماء الأعمدة.")
    finally:
        db.close()

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    await query.answer()
    db = SessionLocal()
    
    if query.data == "clear_and_restart":
        try: await query.message.delete()
        except Exception: pass
        sessions[chat_id] = {"step": "ASK_PHONE"}
        await context.bot.send_message(chat_id=chat_id, text="🧹 تم تنظيف الجلسة بنجاح.\n\n🔒 يرجى إدخل **رقم هاتفك** من جديد للدخول الموثق:", reply_markup=ReplyKeyboardRemove())
        db.close()
        return

    if query.data == "back_to_admin_menu":
        try: await query.message.delete()
        except Exception: pass
        await show_admin_menu(context.bot, chat_id)
        db.close()
        return

    if query.data == "back_to_emp_menu":
        try: await query.message.delete()
        except Exception: pass
        if chat_id in sessions and "id" in sessions[chat_id]:
            emp = db.query(Employee).filter(Employee.id == sessions[chat_id]["id"]).first()
            if emp: await show_employee_menu(context.bot, chat_id, emp.name)
        db.close()
        return

    # 1. تصدير البيانات إلى إكسل
    if query.data == "admin_export_excel":
        emps = db.query(Employee).all()
        df = pd.DataFrame([{"الرقم الوظيفي": e.id, "الاسم": e.name, "رقم الهاتف الدولي": e.phone_number, "الصلاحية": e.role} for e in emps])
        file_name = "بيانات_الموظفين_المحدثة.xlsx"
        df.to_excel(file_name, index=False)
        kb = [[InlineKeyboardButton("↩️ رجوع للوحة التحكم", callback_data="back_to_admin_menu")]]
        with open(file_name, "rb") as f:
            await context.bot.send_document(chat_id=chat_id, document=f, filename=file_name, caption="📊 ملف إكسل متكامل ومحدث بكامل بيانات الموظفين الحالية في النظام.", reply_markup=InlineKeyboardMarkup(kb))
        if os.path.exists(file_name): os.remove(file_name)

    # 2. تهيئة استقبال ملف الاستيراد
    elif query.data == "admin_import_trigger":
        sessions[chat_id]["step"] = "WAITING_FOR_EXCEL_IMPORT"
        kb = [[InlineKeyboardButton("❌ إلغاء والرجوع", callback_data="back_to_admin_menu")]]
        await query.message.reply_text("📥 النظام في وضع الاستعداد الآمن الآن!\nيرجى سحب وإرسال (Upload) ملف الإكسيل الجديد `.xlsx` في المحادثة مباشرة ليتم اعتماده وتحديث قاعدة البيانات.", reply_markup=InlineKeyboardMarkup(kb))

    # 3. تنظيم وإدارة المذكرات والشكاوى
    elif query.data == "admin_manage_tickets":
        tickets = db.query(HR_Ticket).filter(HR_Ticket.status == "قيد المراجعة").all()
        kb_back = [[InlineKeyboardButton("↩️ رجوع للوحة التحكم", callback_data="back_to_admin_menu")]]
        if not tickets:
            await query.message.reply_text("🗂️ لا توجد مذكرات أو شكاوى معلقة حالياً في النظام.", reply_markup=InlineKeyboardMarkup(kb_back))
        else:
            for t in tickets:
                kb_action = [
                    [InlineKeyboardButton("إغلاق وتصفية المذكرة ✅", callback_data=f"tic_close_{t.id}")],
                    [InlineKeyboardButton("↩️ رجوع", callback_data="back_to_admin_menu")]
                ]
                await query.message.reply_text(f"🎫 **مذكرة من الموظف رقم {t.employee_id}:**\n\n📝 التفاصيل:\n`{t.details}`", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb_action))

    # 4. مراجعة طلبات الإجازات المعلقة
    elif query.data == "admin_manage_vacations":
        reqs = db.query(VacationRequest).filter(VacationRequest.status.like("%انتظار%")).all()
        kb_back = [[InlineKeyboardButton("↩️ رجوع للوحة التحكم", callback_data="back_to_admin_menu")]]
        if not reqs:
            await query.message.reply_text("✅ السجلات نظيفة، لا توجد طلبات إجازة معلقة حالياً.", reply_markup=InlineKeyboardMarkup(kb_back))
        else:
            for r in reqs:
                kb = [[
                    InlineKeyboardButton("موافقة ✅", callback_data=f"vac_approve_{r.id}"),
                    InlineKeyboardButton("رفض ❌", callback_data=f"vac_reject_{r.id}")
                ]]
                await query.message.reply_text(f"✈️ **طلب إجازة معلق:**\nالموظف: {r.employee_id}\nالأيام المطلوبة: {r.days_count} أيام.", reply_markup=InlineKeyboardMarkup(kb))

    # 5. إدارة منح وسحب الصلاحيات الإدارية
    elif query.data == "admin_manage_roles":
        emps = db.query(Employee).all()
        await query.message.reply_text("🔑 **قائمة الموظفين النشطين لتعديل الصلاحيات:**\nاختر الإجراء المطلوب لتحديث رتبة الموظف في النظام:")
        for e in emps:
            target_role = "Employee" if e.role == "Admin" else "Admin"
            action_text = "📥 سحب صلاحية مدير إلى موظف" if e.role == "Admin" else "📤 ترقية إلى مدير (Admin)"
            kb = [
                [InlineKeyboardButton(action_text, callback_data=f"role_{target_role}_{e.id}")],
                [InlineKeyboardButton("↩️ رجوع للوحة التحكم", callback_data="back_to_admin_menu")]
            ]
            await context.bot.send_message(chat_id=chat_id, text=f"👤 **الموظف:** {e.name}\n💼 **الصلاحية الحالية:** {e.role}", reply_markup=InlineKeyboardMarkup(kb))

    # معالجة قرارات الصلاحيات والإجازات والشكاوى
    elif query.data.startswith("role_"):
        parts = query.data.split("_")
        new_role, emp_id = parts[1], parts[2]
        emp = db.query(Employee).filter(Employee.id == emp_id).first()
        if emp:
            emp.role = new_role
            db.commit()
            await query.message.reply_text(f"✅ تم بنجاح تعديل صلاحية **{emp.name}** إلى **{new_role}** المحدثة.")

    elif query.data.startswith("vac_"):
        parts = query.data.split("_")
        action, req_id = parts[1], int(parts[2])
        req = db.query(VacationRequest).filter(VacationRequest.id == req_id).first()
        if req:
            if action == "approve":
                req.status = "مقبولة ✅"
                emp = db.query(Employee).filter(Employee.id == req.employee_id).first()
                if emp: emp.vacation_balance -= req.days_count
                await query.message.reply_text("✅ تم الموافقة على الإجازة وتحديث الرصيد بنجاح.")
            else:
                req.status = "مرفوضة ❌"
                await query.message.reply_text("❌ تم رفض طلب الإجازة بنجاح.")
            db.commit()

    elif query.data.startswith("tic_"):
        parts = query.data.split("_")
        tic_id = int(parts[2])
        ticket = db.query(HR_Ticket).filter(HR_Ticket.id == tic_id).first()
        if ticket:
            ticket.status = "تم الحل والمراجعة ✅"
            db.commit()
            await query.message.reply_text("✅ تم أرشفة وإغلاق المذكرة والمقترح بنجاح.")
            
    # معالجات أزرار الموظف
    elif query.data == "emp_salary":
        emp = db.query(Employee).filter(Employee.id == sessions[chat_id]["id"]).first()
        sal = decrypt_data(emp.encrypted_salary)
        pdf = generate_payslip_pdf(emp.name, emp.id, emp.title, sal)
        with open(pdf, "rb") as f:
            await context.bot.send_document(chat_id=chat_id, document=f, filename=f"Payslip_{emp.id}.pdf")
        if os.path.exists(pdf): os.remove(pdf)
    elif query.data == "emp_vacation":
        emp = db.query(Employee).filter(Employee.id == sessions[chat_id]["id"]).first()
        await query.message.reply_text(f"📅 رصيد إجازاتك الحالي المتبقي: **{emp.vacation_balance} يوماً**.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ رجوع", callback_data="back_to_emp_menu")]]))
    elif query.data == "emp_request_vacation":
        sessions[chat_id]["step"] = "INPUT_VACATION_DAYS"
        await query.message.reply_text("✈️ يرجى كتابة عدد الأيام المراد طلبها للإجازة:")
    elif query.data == "emp_ticket":
        sessions[chat_id]["step"] = "RAISE_TICKET"
        await query.message.reply_text("📝 تفضل بكتابة نص الشكوى أو المقترح بوضوح للمدير:")

    db.close()

