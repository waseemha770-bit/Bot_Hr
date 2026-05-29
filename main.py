# =====================================================================
# 1. الجزء الذكي لتحديث المكتبات إجبارياً وتجاوز كاش السيرفر
# =====================================================================
import sys
import os
import subprocess

try:
    import openpyxl
    if openpyxl.__version__ < '3.1.5':
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl>=3.1.5"])
        os.execv(sys.executable, ['python'] + sys.argv)
except Exception as e:
    print(f"تنبيه تحديث المكتبات: {e}")

# =====================================================================
# 2. استدعاء المكتبات المطلوبة للواجهات الجديدة
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

# تعريف مراحل محادثة الشكاوى (Conversation States)
AWAITING_COMPLAINT_TEXT, AWAITING_COMPLAINT_FILE = range(2)

# =====================================================================
# 3. دالة بدء التشغيل وعرض القائمة الرئيسية (Main Menu)
# =====================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض القائمة الرئيسية للموظف المعتمد"""
    keyboard = [
        ['🗓️ جدول الدوام', '⏱️ سجل البصمات'],
        ['✍️ تقديم شكوى', '👤 ملفي الشخصي']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    await update.message.reply_text(
        "👋 أهلاً بك في لوحة تحكم الموظف الذكية.\n"
        "الرجاء اختيار الخدمة المطلوبة من القائمة أدناه:",
        reply_markup=reply_markup
    )

# =====================================================================
# 4. قسم جدول الدوام (Shift Schedule)
# =====================================================================
async def handle_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض واجهة جدول الدوام مع فلاتر التصفية"""
    text = (
        "👤 **الموظف:** وسيم حمدان\n"
        "🆔 **الرقم الوظيفي:** HR-2245\n"
        "📅 **الفترة الحالية:** الأسبوع الحالي\n\n"
        "📋 **جدول دوامك المعتمد:**\n"
        "• الأحد - الثلاثاء: 08:00 ص - 04:00 م (صباحي)\n"
        "• الأربعاء: 04:00 م - 12:00 م (مسائي)\n"
        "• الخميس: 08:00 ص - 04:00 م (صباحي)\n"
        "• الجمعة - السبت: إجازة أسبوعية."
    )
    
    keyboard = [
        [InlineKeyboardButton("📅 الأسبوع القادم", callback_data="sched_next_week")],
        [InlineKeyboardButton("🔍 تصفية بحسب الشهر", callback_data="sched_filter_month")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# =====================================================================
# 5. قسم سجل البصمات (Attendance Logs)
# =====================================================================
async def handle_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب اختيار الشهر لعرض البصمات"""
    keyboard = [
        [InlineKeyboardButton("مايو 2026", callback_data="att_may_2026")],
        [InlineKeyboardButton("أبريل 2026", callback_data="att_apr_2026")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⏱️ يرجى اختيار الشهر المراد عرض سجل البصمات له:", reply_markup=reply_markup)

async def process_attendance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جدول البصمات بنظام منسق مونو-سبيس"""
    query = update.callback_query
    await query.answer()
    
    table_text = (
        "⏱️ **سجل بصمات شهر: مايو 2026**\n\n"
        "`التاريخ   | الحضور   | الانصراف | الحالة`\n"
        "`---------------------------------------`\n"
        "`24-05-26 | 07:55 ص  | 04:05 م  | ✅ منتظم`\n"
        "`25-05-26 | 08:15 ص  | 04:00 م  | ⚠️ تأخير`\n"
        "`26-05-26 | 03:50 م  | 12:02 م  | ✅ منتظم`\n"
        "`27-05-26 | --:--    | --:--    | ❌ غياب`\n\n"
        "💡 *إجمالي ساعات الدوام الفعلية: 168 ساعت.*"
    )
    
    keyboard = [
        [InlineKeyboardButton("📥 تحميل السجل كملف Excel (XLSX)", callback_data="export_excel")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back_to_attendance")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(table_text, reply_markup=reply_markup, parse_mode="Markdown")

# =====================================================================
# 6. قسم الشكاوى والاعتراضات (Complaints System)
# =====================================================================
async def start_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التحقق من التاريخ التلقائي وقبول الشكوى"""
    current_date = datetime.datetime.now()
    deadline_day = 26  # آخر موعد لاستقبال الشكاوى قبل الرواتب بـ 5 أيام
    
    if current_date.day > deadline_day:
        await update.message.reply_text(
            f"❌ **عذراً، استقبال الشكاوى مغلق حالياً.**\n"
            f"لقد انتهت المدة المحددة لاستقبال اعتراضات الرواتب لهذا الشهر (انتهت يوم {deadline_day} في الشهر).\n"
            f"يرجى مراجعة إدارة الموارد البشرية مباشرة.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "✍️ **قسم الشكاوى والاعتراضات الإدارية**\n\n"
        "الموعد متاح حالياً. يرجى اتباع الآتي:\n"
        "1. اكتب نص الشكوى أو الاعتراض بالتفصيل في الرسالة القادمة.\n"
        "2. لإلغاء العملية في أي وقت اكتب /cancel.\n\n"
        "👇 تفضل بكتابة شكواك الآن:"
    )
    return AWAITING_COMPLAINT_TEXT

async def receive_complaint_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['complaint_text'] = update.message.text
    keyboard = [[InlineKeyboardButton("⏭️ إرسال بدون مرفقات", callback_data="skip_file")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "✅ تم استلام النص.\n"
        "قم بإرفاق ملف توضيحي الآن (صورة أو مستند PDF)، أو اضغط على الزر أدناه للمتابعة بدون مرفقات:",
        reply_markup=reply_markup
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
    query = update.callback_query
    await query.answer()
    context.user_data['complaint_file'] = None
    await send_complaint_preview(query, context, is_callback=True)
    return ConversationHandler.END

async def send_complaint_preview(target, context, is_callback=False):
    text = (
        "🔍 **معاينة شكواك قبل الاعتماد والإرسال للإدارة:**\n\n"
        f"📝 **النص:** {context.user_data['complaint_text']}\n"
        f"📎 **المرفقات:** {'موجود 📄' if context.user_data.get('complaint_file') else 'لا يوجد'}\n\n"
        "هل تريد إرسالها رسمياً؟"
    )
    keyboard = [
        [InlineKeyboardButton("✅ تأكيد وإرسال", callback_data="confirm_send_complaint")],
        [InlineKeyboardButton("❌ إلغاء وتراجع", callback_data="cancel_complaint")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if is_callback:
        await target.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await target.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📥 تم إلغاء تقديم الشكوى وعودتك للقائمة الرئيسية.")
    return ConversationHandler.END

# =====================================================================
# 7. معالجة عمليات التأكيد النهائية (Callbacks)
# =====================================================================
async def handle_global_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_send_complaint":
        await query.edit_message_text("🚀 **تم إرسال شكواك بنجاح وأمان إلى إدارة الموارد البشرية وجاري مراجعتها.**")
    elif query.data == "cancel_complaint":
        await query.edit_message_text("❌ تم إلغاء الشكوى ولم يتم إرسال أي بيانات.")

# =====================================================================
# 8. الدالة الأساسية لتشغيل البوت (Main Entry)
# =====================================================================
def main():
    # التوكن الجديد المحدث
    TOKEN = "8678088302:AAEGCNo6XTRuhf5ybIdbGJw8u4XMzJMOnFI"
    
    application = Application.builder().token(TOKEN).build()

    # إعداد نظام محادثة الشكاوى المتسلسل
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

    # تسجيل الموزعين والأزرار الأساسية
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex('^🗓️ جدول الدوام$'), handle_schedule))
    application.add_handler(MessageHandler(filters.Regex('^⏱️ سجل البصمات$'), handle_attendance))
    application.add_handler(complaint_handler)
    
    # تسجيل أزرار الأحداث الشفافة
    application.add_handler(CallbackQueryHandler(process_attendance_callback, pattern="^att_"))
    application.add_handler(CallbackQueryHandler(handle_global_callbacks, pattern="^(confirm_send|cancel_complaint)"))

    # تشغيل سحب البيانات (Polling)
    application.run_polling()

if __name__ == '__main__':
    main()

