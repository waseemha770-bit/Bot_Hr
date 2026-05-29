# =====================================================================
# 1. الجزء الذكي لتحديث المكتبات إجبارياً وتجاوز كاش السيرفر
# =====================================================================
import sys
import os
import subprocess
import threading  # لإنشاء سيرفر ويب وهمي بالخلفية لمنع الـ Timeout على Render

try:
    import openpyxl
    if openpyxl.__version__ < '3.1.5':
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl>=3.1.5"])
        os.execv(sys.executable, ['python'] + sys.argv)
except Exception as e:
    print(f"تنبيه تحديث المكتبات: {e}")

# =====================================================================
# 2. الإعدادات الأساسية للهوية (قائمة المدراء)
# =====================================================================
# 👑 تم دمج معرف التلجرام الخاص بك لتفعيل لوحة المدير تلقائياً لحسابك
ADMIN_IDS = [892385625] 

# تعريف مراحل محادثة الشكاوى (Conversation States)
AWAITING_COMPLAINT_TEXT, AWAITING_COMPLAINT_FILE = range(2)

# =====================================================================
# 3. خادم الويب الوهمي لحل مشكلة الـ Port Binding والـ HEAD Requests
# =====================================================================
from http.server import BaseHTTPRequestHandler, HTTPServer

class DummyWebhookServer(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is Running Successfully!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyWebhookServer)
    print(f"📡 Dummy Server started on port {port} to bypass Render checks...")
    server.serve_forever()

# =====================================================================
# 4. استدعاء مكتبات البوت والبيانات
# =====================================================================
import datetime
import pandas as pd
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
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
# 5. دالة بدء التشغيل وعرض القائمة بحسب الصلاحية (مواظف / مدير)
# =====================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # إذا كان المستخدم مديراً (حسابك الشخصي)
    if user_id in ADMIN_IDS:
        keyboard = [
            ['📊 إحصائيات الموظفين', '📂 مراجعة الشكاوى'],
            ['⚙️ إعدادات النظام', '👤 التحويل لواجهة موظف']
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "👑 **مرحباً بك يا وسيم في لوحة تحكم المدير الإدارية**\n"
            "يمكنك إدارة طلبات الموظفين والاطلاع على التقارير الحية من هنا:",
            reply_markup=reply_markup, parse_mode="Markdown"
        )
    # إذا كان المستخدم موظفاً عادياً
    else:
        keyboard = [
            ['🗓️ جدول الدوام', '⏱️ سجل البصمات'],
            ['✍️ تقديم شكوى', '👤 ملفي الشخصي']
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "👋 أهلاً بك في لوحة تحكم الموظف الذكية.\n"
            "الرجاء اختيار الخدمة المطلوبة من القائمة أدناه:",
            reply_markup=reply_markup
        )

# =====================================================================
# 6. معالجة أزرار القائمة الرئيسية للمدير
# =====================================================================
async def handle_admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == '📊 إحصائيات الموظفين':
        await update.message.reply_text("📈 **إحصائيات اليوم الحالية:**\n• الموظفين الحاضرين: 18\n• المتأخرين: 2\n• الغائبين: 1", parse_mode="Markdown")
    elif text == '📂 مراجعة الشكاوى':
        await update.message.reply_text("📥 لا توجد شكاوى جديدة غير مقروءة في قاعدة البيانات حالياً.")
    elif text == '⚙️ إعدادات النظام':
        await update.message.reply_text("⚙️ إعدادات النظام مفعّلة وتعمل بشكل مستقر على سيرفرات Render الآمنة.")
    elif text == '👤 التحويل لواجهة موظف':
        keyboard = [['🗓️ جدول الدوام', '⏱️ سجل البصمات'], ['✍️ تقديم شكوى', '👤 ملفي الشخصي']]
        await update.message.reply_text("🔄 تم الانتقال لواجهة العرض التجريبية الخاصة بالموظفين:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# =====================================================================
# 7. معالجة قسم جدول الدوام (الموظف)
# =====================================================================
async def handle_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👤 **الموظف:** وسيم حمدان\n"
        "🆔 **الرقم الوظيفي:** HR-2245\n"
        "📋 **جدول دوامك الحالي الأسبوعي:**\n"
        "• الأحد - الخميس: 08:00 ص - 04:00 م"
    )
    keyboard = [
        [InlineKeyboardButton("📅 الأسبوع القادم", callback_data="sched_next_week")],
        [InlineKeyboardButton("🔍 تصفية بحسب الشهر", callback_data="sched_filter_month")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# =====================================================================
# 8. معالجة قسم سجل البصمات (الموظف)
# =====================================================================
async def handle_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("مايو 2026", callback_data="att_may_2026")],
        [InlineKeyboardButton("أبريل 2026", callback_data="att_apr_2026")]
    ]
    await update.message.reply_text("⏱️ يرجى اختيار الشهر المراد عرض سجل البصمات له:", reply_markup=InlineKeyboardMarkup(keyboard))

# =====================================================================
# 9. دالة محرك الاستجابة الذكية لنقرات الأزرار (Callback Query Handler)
# =====================================================================
async def handle_all_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()  # لإزالة علامة التحميل (الساعة الرملية) فوراً عند النقر

    # أزرار قسم جدول الدوام
    if data == "sched_next_week":
        await query.edit_message_text("📅 **جدول الأسبوع القادم:**\nنفس الوردية المعتمدة دون أي تغييرات طارئة حتى الآن.", parse_mode="Markdown")
    elif data == "sched_filter_month":
        await query.edit_message_text("🔍 خاصية التصفية الشهرية المتقدمة قيد التحديث والربط مع قاعدة البيانات.")
    
    # أزرار اختيار أشهر سجل البصمات
    elif data.startswith("att_"):
        month_name = "مايو 2026" if "may" in data else "أبريل 2026"
        table_text = (
            f"⏱️ **سجل بصمات شهر: {month_name}**\n\n"
            "`التاريخ   | الحضور   | الانصراف | الحالة`\n"
            "`---------------------------------------`\n"
            "`24-05-26 | 07:55 ص  | 04:05 م  | ✅ منتظم`\n"
            "`25-05-26 | 08:15 ص  | 04:00 م  | ⚠️ تأخير`\n"
        )
        keyboard = [
            [InlineKeyboardButton("📥 تحميل السجل كملف Excel (XLSX)", callback_data="export_excel")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="back_to_attendance")]
        ]
        await query.edit_message_text(table_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    # أزرار البصمات الداخلية
    elif data == "export_excel":
        await query.message.reply_text("📥 جاري تجهيز تقرير Excel بصيغة XLSX وإرساله لك خلال لحظات...")
    elif data == "back_to_attendance":
        keyboard = [
            [InlineKeyboardButton("مايو 2026", callback_data="att_may_2026")],
            [InlineKeyboardButton("أبريل 2026", callback_data="att_apr_2026")]
        ]
        await query.edit_message_text("⏱️ يرجى اختيار الشهر المراد عرض سجل البصمات له:", reply_markup=InlineKeyboardMarkup(keyboard))
        
    # أزرار تأكيد وإلغاء محادثة الشكاوى
    elif data == "confirm_send_complaint":
        await query.edit_message_text("🚀 **تم إرسال شكواك بنجاح وأمان إلى إدارة الموارد البشرية.**")
    elif data == "cancel_complaint":
        await query.edit_message_text("❌ تم إلغاء الشكوى وعودتك للقائمة الرئيسية.")

# =====================================================================
# 10. نظام محادثة الشكاوى والاعتراضات الإدارية (Conversation)
# =====================================================================
async def start_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✍️ تفضل بكتابة نص شكواك أو اعتراضك الإداري الآن:")
    return AWAITING_COMPLAINT_TEXT

async def receive_complaint_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['complaint_text'] = update.message.text
    keyboard = [[InlineKeyboardButton("⏭️ إرسال بدون مرفقات", callback_data="skip_file")]]
    await update.message.reply_text("✅ تم الحفظ. أرفق مستند/صورة أو اضغط الزر للتخطي:", reply_markup=InlineKeyboardMarkup(keyboard))
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
    text = f"🔍 **معاينة الشكوى التوضيحية:**\n\n📝 {context.user_data['complaint_text']}\n\nهل تؤكد الإرسال الإداري؟"
    keyboard = [[InlineKeyboardButton("✅ تأكيد وإرسال", callback_data="confirm_send_complaint")], [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_complaint")]]
    if is_callback: await target.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else: await target.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📥 تم إلغاء عملية تقديم الشكوى بنجاح.")
    return ConversationHandler.END

# =====================================================================
# 11. الدالة الأساسية لتشغيل البوت واحتضان المستمعات (Main Entry)
# =====================================================================
def main():
    # 📡 إطلاق السيرفر الوهمي بالتوازي لمنع انهيار الـ Web Service على Render
    threading.Thread(target=run_dummy_server, daemon=True).start()

    # 🔑 التوكن الجديد المحدث بالكامل لمنع أي تضارب
    TOKEN = "8678088302:AAElsZoW6htlAjOwczX9TBKysHzit3NuRxo"
    application = Application.builder().token(TOKEN).build()

    complaint_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^✍️ تقديم شكوى$'), start_complaint)],
        states={
            AWAITING_COMPLAINT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_complaint_text)],
            AWAITING_COMPLAINT_FILE: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, receive_complaint_file),
                CallbackQueryHandler(skip_complaint_file, pattern="^skip_file$")
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_handler)]
    )

    # إضافة الـ Handlers الأساسية للمستخدمين والمدير
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex('^🗓️ جدول الدوام$'), handle_schedule))
    application.add_handler(MessageHandler(filters.Regex('^⏱️ سجل البصمات$'), handle_attendance))
    
    # مستقبل أزرار لوحة تحكم المدير الرئيسية
    application.add_handler(MessageHandler(filters.Regex('^(📊 إحصائيات الموظفين|📂 مراجعة الشكاوى|⚙️ إعدادات النظام|👤 التحويل لواجهة موظف)$'), handle_admin_buttons))
    
    application.add_handler(complaint_handler)
    
    # 🎯 المستمع العام والشامل للتعامل مع كافة ضغطات الأزرار العالقة
    application.add_handler(CallbackQueryHandler(handle_all_callbacks))

    # ⚡ التشغيل النظيف مع إسقاط التحديثات المتراكمة لتفادي الـ Conflict
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
