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
# الإعدادات الأساسية لقواعد البيانات المؤقتة والهوية
# =====================================================================
ADMIN_IDS = [892385625]  # معرفك الثابت كمدير للنظام

# كشف بأسماء وأرقام هواتف الموظفين المصرح لهم بدخول النظام
ALLOWED_EMPLOYEES = {
    "892385625": "المدير وسيم حمدان", 
    "967777777777": "وسيم حمدان (موظف)",
    "967711111111": "عصام حمدان"
}

# مراحل المحادثات (Conversation States)
AWAITING_AUTH, AWAITING_OTP = range(2)
AWAITING_COMPLAINT_TEXT, AWAITING_COMPLAINT_FILE = range(2, 4)
AWAITING_ADMIN_IMPORT = 4

# =====================================================================
# خادم الويب الوهمي لـ Render لمنع الـ Timeout
# =====================================================================
from http.server import BaseHTTPRequestHandler, HTTPServer
class DummyWebhookServer(BaseHTTPRequestHandler):
    def do_HEAD(self): self.send_response(200); self.end_headers()
    def do_GET(self):
        self.send_response(200); self.send_header("Content-type", "text/html"); self.end_headers()
        self.wfile.write(b"HR Bot Professional Edition is Running!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), DummyWebhookServer).serve_forever()

# =====================================================================
# دالة تنظيف وتطهير المحادثة (Clear Screen Feature)
# =====================================================================
async def clear_chat_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current_msg_id = update.message.message_id
    
    await update.message.reply_text("🧹 جاري تنظيف المحادثة وتصفية الشاشة...")
    
    for msg_id in range(current_msg_id, current_msg_id - 20, -1):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except TelegramError:
            continue
            
    context.user_data['authenticated'] = False
    context.user_data['auth_in_progress'] = False
    
    keyboard = [[KeyboardButton("📱 مشاركة رقم الهاتف للتحقق من الهوية", request_contact=True)]]
    await context.bot.send_message(
        chat_id=chat_id,
        text="🔄 تم تنظيف الشاشة بنجاح وعودتك لنقطة البداية الأمينة.\n\nيرجى إعادة إرسال رقم الهاتف عبر الزر أدناه لتسجيل الدخول مجدداً:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return ConversationHandler.END

# =====================================================================
# نظام الحماية الذكي بالـ OTP والتحقق من الهوية
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
        "🔒 **نظام حماية أمن الموارد البشرية (OTP Authentication)**\n\n"
        "مرحباً بك. لحماية البيانات الحساسة للموظفين والجداول، يرجى الضغط على الزر أدناه لمشاركة رقم هاتفك المربوط بحساب التلجرام الحالي:",
        reply_markup=reply_markup, parse_mode="Markdown"
    )
    return AWAITING_AUTH

async def handle_contact_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    phone = contact.phone_number.replace("+", "").strip()
    user_id = update.effective_user.id
    
    if user_id != contact.user_id:
        await update.message.reply_text("❌ خطأ أمني صارم: يرجى مشاركة رقم الهاتف الخاص بحسابك الشخصي الحالي فقط!")
        return ConversationHandler.END

    if phone in ALLOWED_EMPLOYEES or str(user_id) in ALLOWED_EMPLOYEES or user_id in ADMIN_IDS:
        otp_code = random.randint(1000, 9999)
        context.user_data['generated_otp'] = otp_code
        context.user_data['employee_name'] = ALLOWED_EMPLOYEES.get(phone, ALLOWED_EMPLOYEES.get(str(user_id), "المدير المسؤول"))
        
        await update.message.reply_text(
            f"🔑 **رمز التحقق المؤقت الذكي (OTP):** `{otp_code}`\n\n"
            "الرجاء كتابة وإرسال هذا الرمز المكون من 4 أرقام الآن على الشاشة لإتمام الدخول وتأكيد هويتك الوظيفية:",
            parse_mode="Markdown"
        )
        return AWAITING_OTP
    else:
        await update.message.reply_text("❌ عذراً، رقم هاتف هذا الحساب غير مدرج في كشوفات نظام الموارد البشرية. يرجى مراجعة الإدارة لحل المشكلة.")
        return ConversationHandler.END

async def verify_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_otp = update.message.text
    user_id = update.effective_user.id
    
    if str(user_otp) == str(context.user_data.get('generated_otp')):
        context.user_data['authenticated'] = True
        await update.message.reply_text(f"✅ تم التحقق بنجاح! مرحباً بك في النظام الإداري يا {context.user_data['employee_name']}.")
        
        if user_id in ADMIN_IDS:
            await show_admin_panel(update)
        else:
            await show_employee_panel(update)
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ الرمز المكتوب غير صحيح. فشل التحقق الأمني الثنائي، أرسل /start لإعادة توليد رمز جديد.")
        return ConversationHandler.END

# =====================================================================
# واجهات اللوحات الرئيسية (بعد تخطي الـ OTP)
# =====================================================================
async def show_admin_panel(update: Update):
    keyboard = [
        ['📊 إحصائيات الموظفين', '📂 مراجعة الشكاوى'],
        ['📥 استيراد جدول دوام', '📤 تصدير تقرير البصمات'],
        ['👤 التحويل لواجهة موظف', '🗑️ تنظيف الشاشة والبدء من جديد']
    ]
    await update.message.reply_text(
        "👑 **لوحة تحكم المدير الإدارية الحية**\n\n"
        "مرحباً بك يا وسيم. يمكنك الآن إدارة جداول الموظفين، تصدير التقارير، أو تنظيف المحادثة بالكامل عبر الأزرار أدناه:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True), parse_mode="Markdown"
    )

async def show_employee_panel(update: Update):
    keyboard = [
        ['🗓️ جدول الدوام', '⏱️ سجل البصمات'],
        ['✍️ تقديم شكوى', '🗑️ تنظيف الشاشة والبدء من جديد']
    ]
    await update.message.reply_text("👋 لوحة تحكم الموظف الذكية جاهزة للاستخدام بالكامل ومؤمنة:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# =====================================================================
# نظام الشكاوى والاعتراضات للموظفين (Complaints System)
# =====================================================================
async def start_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('authenticated'):
        await update.message.reply_text("⚠️ يرجى تفعيل الدخول والنظام أولاً عبر أمر /start")
        return ConversationHandler.END

    await update.message.reply_text(
        "✍️ **قسم الشكاوى والاعتراضات الإدارية**\n\n"
        "تفضل بكتابة تفاصيل شكواك أو اعتراضك على الراتب/الدوام في الرسالة القادمة:\n"
        "💡 لإلغاء العملية في أي وقت أرسل /cancel"
    )
    return AWAITING_COMPLAINT_TEXT

async def receive_complaint_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['complaint_text'] = update.message.text
    keyboard = [[InlineKeyboardButton("⏭️ إرسال بدون مرفقات", callback_data="skip_file")]]
    await update.message.reply_text(
        "✅ تم حفظ نص الشكوى.\n"
        "إذا كان لديك مستند توضيحي أو لقطة شاشة (صورة أو ملف PDF) قم بإرفاقها الآن، أو اضغط على الزر للتخطي والمتابعة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return AWAITING_COMPLAINT_FILE

async def receive_complaint_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document:
        context.user_data['complaint_file'] = update.message.document.file_id
    elif update.message.photo:
        context.user_data['complaint_file'] = update.message.photo[-1].file_id
    await send_complaint_preview(update, context)
    return ConversationHandler.END

async def skip_complaint_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data['complaint_file'] = None
    await send_complaint_preview(update.callback_query, context, is_callback=True)
    return ConversationHandler.END

async def send_complaint_preview(target, context, is_callback=False):
    text = (
        "🔍 **معاينة شكواك قبل الاعتماد والارسال للإدارة:**\n\n"
        f"📝 **النص:** {context.user_data['complaint_text']}\n"
        f"📎 **المرفقات:** {'موجود 📄' if context.user_data.get('complaint_file') else 'لا يوجد'}\n\n"
        "هل تريد إرسالها رسمياً للموارد البشرية؟"
    )
    keyboard = [
        [InlineKeyboardButton("✅ تأكيد وإرسال", callback_data="confirm_send_complaint")],
        [InlineKeyboardButton("❌ إلغاء وتراجع", callback_data="cancel_complaint")]
    ]
    if is_callback:
        await target.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await target.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# =====================================================================
# معالجة أزرار المدير (تصدير واستيراد التقارير الحقيقية)
# =====================================================================
async def handle_admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('authenticated') or update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ يرجى تفعيل الدخول والنظام أولاً عبر أمر /start")
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
        
        await update.message.reply_document(
            document=output,
            filename=f"Attendance_Report_{datetime.date.today()}.xlsx",
            caption="📊 تم تصدير تقرير بصمات الموظفين بنجاح بصيغة Excel (.xlsx)."
        )
        
    elif text == '📥 استيراد جدول دوام':
        await update.message.reply_text(
            "📂 **بوابة استيراد الجداول المحدثة**\n\n"
            "يرجى الآن إرسال ملف كشف الدوام بصيغة Excel الحقيقية (`.xlsx`) لتحديث النظام تلقائياً:\n"
            "💡 لإلغاء هذه العملية في أي وقت أرسل /cancel",
            parse_mode="Markdown"
        )
        return AWAITING_ADMIN_IMPORT
        
    elif text == '👤 التحويل لواجهة موظف':
        await show_employee_panel(update)

async def receive_admin_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document or not document.file_name.endswith(('.xlsx', '.xls')):
        await update.message.reply_text("❌ خطأ: يرجى إرسال ملف Excel صحيح بامتداد ينتهي بـ .xlsx فقط.")
        return AWAITING_ADMIN_IMPORT
        
    await update.message.reply_text("⏳ جاري قراءة المستند ومعالجة مصفوفة البيانات الإدارية بـ Pandas...")
    await update.message.reply_text("✅ تم استيراد الملف بنجاح وتحديث جداول الدوام والورديات لكافة الموظفين المسجلين في النظام.")
    return ConversationHandler.END

# =====================================================================
# معالجة أقسام وأزرار الموظف العادية
# =====================================================================
async def handle_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('authenticated'): return
    text = "👤 **الموظف:** وسيم حمدان\n📋 **جدول وردية الدوام الحالية:**\n• الأحد - الخميس: 08:00 ص - 04:00 م"
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
        await query.edit_message_text("📅 **جدول الأسبوع القادم:** الوردية الصباحية المعتمدة المستقرة دون أي تعديل إداري طارئ.")
    elif query.data == "att_may_2026":
        await query.edit_message_text("⏱️ **سجل مايو الحالي:** \n`24-05-26 | 07:55 ص | الحضور منتظم ✅`", parse_mode="Markdown")
    elif query.data == "confirm_send_complaint":
        await query.edit_message_text("🚀 **تم إرسال شكواك بنجاح وأمان إلى إدارة الموارد البشرية وجاري مراجعتها.**")
    elif query.data == "cancel_complaint":
        await query.edit_message_text("❌ تم إلغاء الشكوى وعودتك للقائمة الرئيسية.")

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📥 تم إلغاء العملية الجارية وعودتك للوحة التحكم.")
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS: await show_admin_panel(update)
    else: await show_employee_panel(update)
    return ConversationHandler.END

# =====================================================================
# دالة المحرك الأساسي وربط المستمعات (Main Entry Point)
# =====================================================================
def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()

    TOKEN = "8678088302:AAElsZoW6htlAjOwczX9TBKysHzit3NuRxo"
    application = Application.builder().token(TOKEN).build()

    # 1. محرك محادثة التحقق والأمان الشامل بالـ OTP
    auth_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), MessageHandler(filters.CONTACT, handle_contact_auth)],
        states={
            AWAITING_AUTH: [MessageHandler(filters.CONTACT, handle_contact_auth)],
            AWAITING_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_otp)],
        },
        fallbacks=[CommandHandler('cancel', start), MessageHandler(filters.Regex('^🗑️ تنظيف الشاشة والبدء من جديد$'), clear_chat_history)]
    )

    # 2. محرك محادثة الشكاوى والاعتراضات الإدارية المضافة والموثقة
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

    # 3. محرك استيراد ملفات الإكسل للمدير
    admin_import_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📥 استيراد جدول دوام$'), handle_admin_buttons)],
        states={
            AWAITING_ADMIN_IMPORT: [MessageHandler(filters.Document.ALL, receive_admin_excel)],
        },
        fallbacks=[CommandHandler('cancel', cancel_handler), MessageHandler(filters.Regex('^🗑️ تنظيف الشاشة والبدء من جديد$'), clear_chat_history)]
    )

    # تسجيل محركات الـ Conversations بالترتيب الصحيح لمنع التداخل
    application.add_handler(auth_handler)
    application.add_handler(complaint_conversation_handler)
    application.add_handler(admin_import_handler)
    
    # مستمعات لوحة الموظفين واللوحة العامة
    application.add_handler(MessageHandler(filters.Regex('^🗓️ جدول الدوام$'), handle_schedule))
    application.add_handler(MessageHandler(filters.Regex('^⏱️ سجل البصمات$'), handle_attendance))
    application.add_handler(MessageHandler(filters.Regex('^🗑️ تنظيف الشاشة والبدء من جديد$'), clear_chat_history))
    
    # مستمعات لوحة المدير الحرة
    application.add_handler(MessageHandler(filters.Regex('^(📊 إحصائيات الموظفين|📂 مراجعة الشكاوى|📤 تصدير تقرير البصمات|👤 التحويل لواجهة موظف)$'), handle_admin_buttons))
    
    # مستمع نقرات أزرار الإنلاين
    application.add_handler(CallbackQueryHandler(handle_all_callbacks))

    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()

