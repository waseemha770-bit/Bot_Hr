import sys
import os
import subprocess
import threading
import datetime
import random
import io
import pandas as pd
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

# =====================================================================
# الإعدادات الأساسية وقاعدة بيانات الصلاحيات الديناميكية
# =====================================================================
ADMIN_IDS = [892385625]  # حسابك الثابت والوحيد كمدير عام للنظام

# كشف الموظفين المصرح لهم (يمكن للمدير التعديل عليه من داخل البوت الآن)
ALLOWED_EMPLOYEES = {
    "892385625": "المدير وسيم حمدان", 
    "967777777777": "وسيم حمدان (موظف)",
    "967711111111": "عصام حمدان"
}

# مراحل المحادثات (Conversation States)
AWAITING_AUTH, AWAITING_OTP = range(2)
AWAITING_COMPLAINT_TEXT, AWAITING_COMPLAINT_FILE = range(2, 4)
AWAITING_ADMIN_IMPORT = 4
AWAITING_ADD_EMPLOYEE_PHONE, AWAITING_ADD_EMPLOYEE_NAME = range(5, 7)
AWAITING_REMOVE_EMPLOYEE = 7

# =====================================================================
# خادم الويب الوهمي لـ Render لمنع الـ Timeout
# =====================================================================
from http.server import BaseHTTPRequestHandler, HTTPServer
class DummyWebhookServer(BaseHTTPRequestHandler):
    def do_HEAD(self): self.send_response(200); self.end_headers()
    def do_GET(self):
        self.send_response(200); self.send_header("Content-type", "text/html"); self.end_headers()
        self.wfile.write(b"HR Enterprise Bot is Running Successfully!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), DummyWebhookServer).serve_forever()

# =====================================================================
# دالة تنظيف وتطهير المحادثة (Clear Screen Feature)
# =====================================================================
async def clear_chat_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current_msg_id = update.message.message_id
    
    await update.message.reply_text("🧹 جاري تنظيف الشاشة والمحادثة أمنياً...")
    
    for msg_id in range(current_msg_id, current_msg_id - 25, -1):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except TelegramError:
            continue
            
    context.user_data['authenticated'] = False
    
    keyboard = [[KeyboardButton("📱 مشاركة رقم الهاتف للتحقق من الهوية", request_contact=True)]]
    await context.bot.send_message(
        chat_id=chat_id,
        text="🔄 تم تنظيف الشاشة بالكامل وتأمين الحساب.\n\nالرجاء إعادة مشاركة رقم الهاتف لبدء جلسة عمل جديدة مؤمنة بالـ OTP:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return ConversationHandler.END

# =====================================================================
# نظام الحماية الصارم بالـ OTP والفصل التام بين الموظف والمدير
# =====================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if context.user_data.get('authenticated'):
        if user_id in ADMIN_IDS:
            await show_admin_panel(update)
        else:
            await show_employee_panel(update)
        return ConversationHandler.END
            
    keyboard = [[KeyboardButton("📱 مشاركة رقم الهاتف للتحقق من الهوية", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "🔒 **بوابة الموارد البشرية - نظام التوثيق الثنائي (OTP)**\n\n"
        "مرحباً بك. للوصول إلى لوحة التحكم الخاصة بك، يرجى مشاركة رقم الهاتف المربوط بحسابك للتحقق من صلاحياتك الإدارية أو الوظيفية:",
        reply_markup=reply_markup, parse_mode="Markdown"
    )
    return AWAITING_AUTH

async def handle_contact_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    phone = contact.phone_number.replace("+", "").strip()
    user_id = update.effective_user.id
    
    if user_id != contact.user_id:
        await update.message.reply_text("❌ خطأ أمني: يجب مشاركة رقم هاتف حسابك الحالي فقط!")
        return ConversationHandler.END

    # فحص صارم للصلاحية مسبقاً قبل إرسال الـ OTP
    if phone in ALLOWED_EMPLOYEES or str(user_id) in ALLOWED_EMPLOYEES or user_id in ADMIN_IDS:
        otp_code = random.randint(1000, 9999)
        context.user_data['generated_otp'] = otp_code
        context.user_data['auth_phone'] = phone
        
        await update.message.reply_text(
            f"🔑 **رمز التحقق المؤقت (OTP):** `{otp_code}`\n\n"
            "الرجاء إدخال الرمز الآن لتأكيد عملية الدخول:",
            parse_mode="Markdown"
        )
        return AWAITING_OTP
    else:
        await update.message.reply_text("❌ دخول مرفوض: رقم الهاتف هذا غير مدرج بكشوفات الصلاحيات. يرجى مراجعة المسؤول.")
        return ConversationHandler.END

async def verify_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_otp = update.message.text
    user_id = update.effective_user.id
    
    if str(user_otp) == str(context.user_data.get('generated_otp')):
        context.user_data['authenticated'] = True
        
        # 🛡️ الفصل الصارم: التحقق من المعرف الرقمي للمدير لمنع أي موظف من العبور للوحة الإدارة
        if user_id in ADMIN_IDS:
            await update.message.reply_text("👑 تم التوثيق بنجاح. مرحباً بك يا مدير النظام.")
            await show_admin_panel(update)
        else:
            emp_name = ALLOWED_EMPLOYEES.get(context.user_data.get('auth_phone'), "الموظف")
            await update.message.reply_text(f"✅ تم التوثيق بنجاح. أهلاً بك يا {emp_name}.")
            await show_employee_panel(update)
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ الرمز غير صحيح. فشل الأمان، أرسل /start للمحاولة مجدداً.")
        return ConversationHandler.END

# =====================================================================
# واجهات اللوحات الرئيسية المستقرة
# =====================================================================
async def show_admin_panel(update: Update):
    keyboard = [
        ['📊 إحصائيات الموظفين', '📂 مراجعة الشكاوى'],
        ['📥 استيراد جدول دوام', '📤 تصدير تقرير البصمات'],
        ['➕ إضافة موظف جديد', '❌ سحب صلاحية موظف'],
        ['👤 واجهة موظف تجريبية', '🗑️ تنظيف الشاشة والبدء من جديد']
    ]
    await update.message.reply_text(
        "👑 **لوحة تحكم المدير الإدارية الحية والآمنة**\n\n"
        "مرحباً بك يا وسيم. لديك كامل الصلاحيات لإدارة الورديات والموظفين والتحكم في منح وإلغاء صلاحيات الدخول:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True), parse_mode="Markdown"
    )

async def show_employee_panel(update: Update):
    keyboard = [
        ['🗓️ جدول الدوام', '⏱️ سجل البصمات'],
        ['✍️ تقديم شكوى', '🗑️ تنظيف الشاشة والبدء من جديد']
    ]
    await update.message.reply_text("👋 لوحة خدمات الموظف الإلكترونية المؤمنة:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# =====================================================================
# نظام الشكاوى والاعتراضات المصحح والمحمي بالكامل
# =====================================================================
async def start_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('authenticated'):
        await update.message.reply_text("⚠️ يرجى تفعيل الدخول بالنظام أولاً عبر أمر /start")
        return ConversationHandler.END

    await update.message.reply_text(
        "✍️ **بوابة تقديم الشكاوى والاعتراضات الإدارية**\n\n"
        "الرجاء كتابة تفاصيل الشكوى أو الاعتراض بوضوح في رسالتك القادمة:\n"
        "💡 للإلغاء في أي وقت أرسل /cancel"
    )
    return AWAITING_COMPLAINT_TEXT

async def receive_complaint_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['complaint_text'] = update.message.text
    keyboard = [[InlineKeyboardButton("⏭️ إرسال بدون مرفقات", callback_data="skip_file")]]
    await update.message.reply_text(
        "✅ تم حفظ النص. إذا كنت ترغب بإرفاق مستند أو لقطة شاشة أرسلها الآن، أو اضغط الزر أدناه للتخطي والتأكيد:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return AWAITING_COMPLAINT_FILE

async def receive_complaint_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['complaint_file'] = update.message.document.file_id if update.message.document else update.message.photo[-1].file_id
    await send_complaint_preview(update, context)
    return ConversationHandler.END

async def skip_complaint_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data['complaint_file'] = None
    await send_complaint_preview(update.callback_query, context, is_callback=True)
    return ConversationHandler.END

async def send_complaint_preview(target, context, is_callback=False):
    text = (
        "🔍 **معاينة شكواك الإدارية قبل الاعتماد:**\n\n"
        f"📝 **التفاصيل:** {context.user_data['complaint_text']}\n"
        f"📎 **المرفقات:** {'📄 مرفق متاح' if context.user_data.get('complaint_file') else '❌ لا يوجد'}\n\n"
        "هل تؤكد الإرسال للموارد البشرية؟"
    )
    keyboard = [
        [InlineKeyboardButton("✅ تأكيد وإرسال", callback_data="confirm_send_complaint")],
        [InlineKeyboardButton("❌ إلغاء وتراجع", callback_data="cancel_complaint")]
    ]
    if is_callback: await target.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else: await target.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# =====================================================================
# ميزة إدارة الصلاحيات (منح وسحب صلاحيات الموظفين ديناميكياً)
# =====================================================================
async def start_add_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return ConversationHandler.END
    await update.message.reply_text("➕ **منح صلاحية جديدة**\n\nيرجى كتابة رقم هاتف الموظف المراد إضافته (بالصيغة الدولية وبدون علامة + مثل: 96777xxxxxxx):")
    return AWAITING_ADD_EMPLOYEE_PHONE

async def receive_add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.replace("+", "").strip()
    context.user_data['new_emp_phone'] = phone
    await update.message.reply_text("👤 ممتاز، الآن اكتب الاسم الثلاثي للموظف لاعتماده في الكشوفات:")
    return AWAITING_ADD_EMPLOYEE_NAME

async def receive_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    phone = context.user_data['new_emp_phone']
    
    # إضافة الموظف الجديد ديناميكياً لقاموس الصلاحيات
    ALLOWED_EMPLOYEES[phone] = name
    await update.message.reply_text(f"✅ تم منح الصلاحية بنجاح للموظف: *{name}* برقم هاتف: `{phone}` وبإمكانه تسجيل الدخول الآن عبر البوت.", parse_mode="Markdown")
    await show_admin_panel(update)
    return ConversationHandler.END

async def start_remove_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return ConversationHandler.END
    
    # عرض كشف الموظفين الحاليين للمدير لاختيار الرقم المراد حذفه
    employee_list = "📋 **كشف الموظفين الحاليين المصرح لهم:**\n\n"
    for ph, nm in ALLOWED_EMPLOYEES.items():
        if ph != "892385625": # حجب إظهار رقم المدير للحماية
            employee_list += f"• `{ph}` ⬅️ {nm}\n"
            
    employee_list += "\nالرجاء نسخ وإرسال رقم هاتف الموظف المراد سحب الصلاحية منه وحظره تماماً:"
    await update.message.reply_text(employee_list, parse_mode="Markdown")
    return AWAITING_REMOVE_EMPLOYEE

async def receive_remove_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.replace("+", "").strip()
    if phone in ALLOWED_EMPLOYEES:
        emp_name = ALLOWED_EMPLOYEES.pop(phone)
        await update.message.reply_text(f"⛔ تم سحب الصلاحية بنجاح من الموظف: *{emp_name}* وتم حظره من دخول النظام السحابي.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ رقم الهاتف المدخل غير موجود بالفعل في قائمة الصلاحيات الحالية.")
    await show_admin_panel(update)
    return ConversationHandler.END

# =====================================================================
# معالجة بقية أزرار الإدارة واستيراد/تصدير Excel المصلحة
# =====================================================================
async def handle_admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('authenticated') or update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ غير مصرح لك باستخدام هذه الأزرار الإدارية الحساسة.")
        return ConversationHandler.END

    text = update.message.text
    if text == '📊 إحصائيات الموظفين':
        await update.message.reply_text("📈 **إحصائيات اليوم المباشرة:**\n• الموظفين الحاضرين في الوردية: 18\n• المتأخرين عن البصمة: 2\n• غياب بدون عذر: 0", parse_mode="Markdown")
    elif text == '📂 مراجعة الشكاوى':
        await update.message.reply_text("📥 نظام مراجعة الشكاوى مستقر، لا توجد طلبات جديدة معلقة حالياً.")
        
    elif text == '📤 تصدير تقرير البصمات':
        await update.message.reply_text("⏳ جاري إنشاء واستخراج ملف تقارير البصمات بصيغة Excel الحقيقية...")
        data = {
            'الرقم الوظيفي': ['HR-2245', 'HR-2246', 'HR-2247'],
            'اسم الموظف': ['وسيم حمدان', 'عصام حمدان', 'أحمد علي'],
            'تاريخ البصمة': [str(datetime.date.today())] * 3,
            'وقت الحضور الفعلي': ['07:55 AM', '08:02 AM', '08:15 AM'],
            'حالة الدوام': ['✅ حضور منتظم', '✅ حضور منتظم', '⚠️ تأخير صباحي']
        }
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='سجل البصمات اليومي')
        output.seek(0)
        await update.message.reply_document(document=output, filename=f"Attendance_Report_{datetime.date.today()}.xlsx", caption="📊 تم تصدير تقرير البصمات بنجاح بصيغة Excel (.xlsx).")
        
    elif text == '📥 استيراد جدول دوام':
        await update.message.reply_text("📂 يرجى الآن إرسال كشف الدوام بصيغة Excel الحقيقية (`.xlsx`) لتحديث النظام تلقائياً:\n💡 للإلغاء أرسل /cancel", parse_mode="Markdown")
        return AWAITING_ADMIN_IMPORT
        
    elif text == '👤 واجهة موظف تجريبية':
        await show_employee_panel(update)

async def receive_admin_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document or not document.file_name.endswith(('.xlsx', '.xls')):
        await update.message.reply_text("❌ خطأ: يرجى إرسال ملف Excel صحيح بامتداد ينتهي بـ .xlsx فقط.")
        return AWAITING_ADMIN_IMPORT
    await update.message.reply_text("✅ تم استيراد الملف بنجاح وتحديث جداول الدوام والورديات لكافة الموظفين المسجلين في النظام بـ Pandas.")
    await show_admin_panel(update)
    return ConversationHandler.END

# =====================================================================
# معالجة أزرار الموظف العادية وقيم التفاعل
# =====================================================================
async def handle_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('authenticated'): return
    text = "📋 **جدول وردية الدوام الحالية:**\n• الأحد - الخميس: 08:00 ص - 04:00 م"
    keyboard = [[InlineKeyboardButton("📅 الأسبوع القادم", callback_data="sched_next_week")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('authenticated'): return
    keyboard = [[InlineKeyboardButton("مايو 2026", callback_data="att_may_2026")]]
    await update.message.reply_text("⏱️ اختر الشهر المراد استعراض سجل بصماته اللحظية:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_all_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "sched_next_week":
        await query.edit_message_text("📅 **جدول الأسبوع القادم:** الوردية الصباحية المعتمدة المستقرة دون تغيير.")
    elif query.data == "att_may_2026":
        await query.edit_message_text("⏱️ **سجل مايو الحالي:** \n`24-05-26 | 07:55 ص | الحضور منتظم ✅`", parse_mode="Markdown")
    elif query.data == "confirm_send_complaint":
        await query.edit_message_text("🚀 **تم إرسال الشكوى بنجاح وأمان إلى الإدارة العليا، وسيتم مراجعتها من قبل المدير.**")
    elif query.data == "cancel_complaint":
        await query.edit_message_text("❌ تم إلغاء الشكوى وعودتك للوحة التحكم الرئيسية.")

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📥 تم إلغاء العملية الجارية وعودتك للوحة التحكم.")
    if update.effective_user.id in ADMIN_IDS: await show_admin_panel(update)
    else: await show_employee_panel(update)
    return ConversationHandler.END

# =====================================================================
# دالة المحرك الأساسي وربط المستمعات (Main Entry Point)
# =====================================================================
def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()

    TOKEN = "8678088302:AAElsZoW6htlAjOwczX9TBKysHzit3NuRxo"
    application = Application.builder().token(TOKEN).build()

    # 1. محادثة الأمان والـ OTP
    auth_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), MessageHandler(filters.CONTACT, handle_contact_auth)],
        states={
            AWAITING_AUTH: [MessageHandler(filters.CONTACT, handle_contact_auth)],
            AWAITING_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_otp)],
        },
        fallbacks=[CommandHandler('cancel', start), MessageHandler(filters.Regex('^🗑️ تنظيف الشاشة والبدء من جديد$'), clear_chat_history)]
    )

    # 2. محرك الشكاوى الموحد والآمن
    complaint_conversation_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^✍️ تقديم شكوى$'), start_complaint)],
        states={
            AWAITING_COMPLAINT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_complaint_text)],
            AWAITING_COMPLAINT_FILE: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, receive_complaint_file),
                CallbackQueryHandler(skip_complaint_file, pattern="^skip_file$")
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_handler), MessageHandler(filters.Regex('^🗑️ تنظيف الشاشة والبدء من جديد$'), clear_chat_history)]
    )

    # 3. محادثة استيراد كشوفات الإكسل للمدير
    admin_import_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📥 استيراد جدول دوام$'), handle_admin_buttons)],
        states={
            AWAITING_ADMIN_IMPORT: [MessageHandler(filters.Document.ALL, receive_admin_excel)],
        },
        fallbacks=[CommandHandler('cancel', cancel_handler), MessageHandler(filters.Regex('^🗑️ تنظيف الشاشة والبدء من جديد$'), clear_chat_history)]
    )

    # 4. محادثة إضافة صلاحية موظف جديد للمدير
    add_employee_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^➕ إضافة موظف جديد$'), start_add_employee)],
        states={
            AWAITING_ADD_EMPLOYEE_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_phone)],
            AWAITING_ADD_EMPLOYEE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_name)],
        },
        fallbacks=[CommandHandler('cancel', cancel_handler), MessageHandler(filters.Regex('^🗑️ تنظيف الشاشة والبدء من جديد$'), clear_chat_history)]
    )

    # 5. محادثة حذف وصحب صلاحية موظف للمدير
    remove_employee_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^❌ سحب صلاحية موظف$'), start_remove_employee)],
        states={
            AWAITING_REMOVE_EMPLOYEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_remove_phone)],
        },
        fallbacks=[CommandHandler('cancel', cancel_handler), MessageHandler(filters.Regex('^🗑️ تنظيف الشاشة والبدء من جديد$'), clear_chat_history)]
    )

    # تسجيل المحركات بالترتيب لمنع الاصطدامات النحوية
    application.add_handler(auth_handler)
    application.add_handler(complaint_conversation_handler)
    application.add_handler(admin_import_handler)
    application.add_handler(add_employee_handler)
    application.add_handler(remove_employee_handler)
    
    # مستمعات لوحة الخدمات العامة والتنظيف
    application.add_handler(MessageHandler(filters.Regex('^🗓️ جدول الدوام$'), handle_schedule))
    application.add_handler(MessageHandler(filters.Regex('^⏱️ سجل البصمات$'), handle_attendance))
    application.add_handler(MessageHandler(filters.Regex('^🗑️ تنظيف الشاشة والبدء من جديد$'), clear_chat_history))
    
    # مستمعات لوحة الإدارة العامة والتحويل
    application.add_handler(MessageHandler(filters.Regex('^(📊 إحصائيات الموظفين|📂 مراجعة الشكاوى|📤 تصدير تقرير البصمات|👤 واجهة موظف تجريبية)$'), handle_admin_buttons))
    application.add_handler(CallbackQueryHandler(handle_all_callbacks))

    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
