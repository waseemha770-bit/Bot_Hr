import os
import io
import re
import pandas as pd
import numpy as np
import pdfkit
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import logging
import threading
import http.server
import socketserver

# إعدادات الـ Logging لمراقبة الأخطاء
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- إعداد مسار wkhtmltopdf المتوافق مع سيرفر Render وجهازك الشخصي ---
if os.path.exists('./bin/wkhtmltopdf'):
    # هذا المسار الذي سيتم استخدامه على سيرفر Render بعد تفعيل أمر البناء الجديد
    path_wkhtmltopdf = './bin/wkhtmltopdf'
else:
    # هذا هو المسار الافتراضي على نظام ويندوز (إذا كنت تجرّب البوت محلياً على جهازك)
    path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'

# إعداد الإعدادات الخاصة بـ pdfkit
config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)

# خيارات تنسيق الـ PDF ليدعم اللغة العربية والترميز الصحيح
pdf_options = {
    'encoding': "UTF-8",
    'custom-header': [
        ('Accept-Encoding', 'gzip')
    ],
    'no-outline': None,
    'quiet': ''
}

# حالات المحادثة للبوت (Conversation States)
CHOOSING, TYPING_REPLY, TYPING_ID = range(3)

# الكيبورد الرئيسي للبوت
reply_keyboard = [
    ['إدخال البصمة', 'تقرير الموظف'],
    ['تقرير اليوم', 'تقرير الموظفين'],
    ['حذف سجلات الموظف']
]
markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=False, resize_keyboard=True)

# دالة لتنظيف وتجهيز نصوص الخلايا
def clean_cell(val):
    if pd.isna(val):
        return ""
    s = str(val).strip()
    s = re.sub(r'\.0$', '', s)
    return s

# دالة لقراءة البيانات من ملف الإكسل
def load_data():
    file_path = "Attendance_data.xlsx"
    if not os.path.exists(file_path):
        df = pd.DataFrame(columns=["ID", "Name", "Date", "Time In", "Time Out", "Status"])
        df.to_excel(file_path, index=False)
        return df
    try:
        df = pd.read_excel(file_path)
        for col in df.columns:
            df[col] = df[col].astype(object)
        return df
    except Exception as e:
        logger.error(f"Error loading excel file: {e}")
        return pd.DataFrame()

# دالة لحفظ البيانات إلى ملف الإكسل
def save_data(df):
    file_path = "Attendance_data.xlsx"
    try:
        df.to_excel(file_path, index=False)
    except Exception as e:
        logger.error(f"Error saving excel file: {e}")

# دالة لبدء البوت واستقبال المستخدم /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "مرحباً بك في نظام إدارة الحضور والانصراف.\nالرجاء اختيار أحد الخيارات التالية:",
        reply_markup=markup,
    )
    return CHOOSING

# دالة التعامل مع كيبورد الخيارات
async def regular_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    context.user_data['choice'] = text
    
    if text == 'إدخال البصمة':
        await update.message.reply_text(
            "الرجاء إدخال البيانات بصيغة:\nالرقم، الاسم، التاريخ، وقت الدخول، وقت الخروج، الحالة\n\nمثال:\n1, وسيم, 2026-05-30, 08:00, 16:00, حضور",
            reply_markup=ReplyKeyboardRemove()
        )
        return TYPING_REPLY
    elif text == 'تقرير الموظف':
        await update.message.reply_text("الرجاء إدخال الرقم الوظيفي للموظف لرؤية تقريره:", reply_markup=ReplyKeyboardRemove())
        return TYPING_ID
    elif text == 'تقرير اليوم':
        await generate_today_report(update, context)
        return CHOOSING
    elif text == 'تقرير الموظفين':
        await generate_all_employees_report(update, context)
        return CHOOSING
    elif text == 'حذف سجلات الموظف':
        await update.message.reply_text("الرجاء إدخال الرقم الوظيفي للموظف لحذف جميع سجلاته:", reply_markup=ReplyKeyboardRemove())
        return TYPING_ID
    else:
        await update.message.reply_text("خيار غير صحيح، رجاءً اختر من القائمة مجدداً.", reply_markup=markup)
        return CHOOSING

# دالة استقبال وحفظ بيانات البصمة المدخلة يدوياً
async def received_information(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    parts = [p.strip() for p in text.split(',')]
    if len(parts) < 6:
        await update.message.reply_text("صيغة غير صحيحة، تأكد من وجود 6 قيم مفصولة بفاصلة.", reply_markup=markup)
        return CHOOSING

    emp_id, name, date_str, time_in, time_out, status = parts[:6]
    df = load_data()
    new_row = pd.DataFrame([{
        "ID": emp_id, "Name": name, "Date": date_str, 
        "Time In": time_in, "Time Out": time_out, "Status": status
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    save_data(df)
    
    await update.message.reply_text("تم حفظ بيانات البصمة بنجاح!", reply_markup=markup)
    return CHOOSING

# دالة معالجة الإجراءات التي تطلب الرقم الوظيفي (ID) مثل تقرير موظف أو حذفه
async def received_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    emp_id = update.message.text.strip()
    choice = context.user_data.get('choice')
    
    if choice == 'تقرير الموظف':
        await generate_employee_report(update, context, emp_id)
    elif choice == 'حذف سجلات الموظف':
        df = load_data()
        df['ID_str'] = df['ID'].apply(clean_cell)
        if emp_id not in df['ID_str'].values:
            await update.message.reply_text(f"لم يتم العثور على موظف بالرقم {emp_id}", reply_markup=markup)
        else:
            df = df[df['ID_str'] != emp_id]
            df = df.drop(columns=['ID_str'], errors='ignore')
            save_data(df)
            await update.message.reply_text(f"تم حذف جميع سجلات الموظف ذو الرقم {emp_id} بنجاح.", reply_markup=markup)
            
    return CHOOSING

# دالة إنشاء تقرير لموظف محدد وإرساله بصيغة PDF
async def generate_employee_report(update: Update, context: ContextTypes.DEFAULT_TYPE, emp_id: str):
    df = load_data()
    df['ID_str'] = df['ID'].apply(clean_cell)
    emp_df = df[df['ID_str'] == emp_id]
    
    if emp_df.empty:
        await update.message.reply_text(f"لا توجد بيانات مسجلة للموظف بالرقم: {emp_id}", reply_markup=markup)
        return

    emp_name = emp_df.iloc[0]['Name']
    
    html_content = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Arial', sans-serif; margin: 30px; text-align: center; }}
            h2 {{ color: #2c3e50; border-bottom: 2px solid #34495e; padding-bottom: 10px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; direction: rtl; }}
            th, td {{ border: 1px solid #bdc3c7; padding: 12px; text-align: center; }}
            th {{ background-color: #34495e; color: white; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
        </style>
    </head>
    <body>
        <h2>تقرير الحضور والانصراف للموظف: {emp_name} ({emp_id})</h2>
        <table>
            <tr>
                <th>التاريخ</th>
                <th>وقت الدخول</th>
                <th>وقت الخروج</th>
                <th>الحالة</th>
            </tr>
    """
    for _, row in emp_df.iterrows():
        html_content += f"""
            <tr>
                <td>{clean_cell(row['Date'])}</td>
                <td>{clean_cell(row['Time In'])}</td>
                <td>{clean_cell(row['Time Out'])}</td>
                <td>{clean_cell(row['Status'])}</td>
            </tr>
        """
    html_content += "</table></body></html>"

    try:
        pdf_data = pdfkit.from_string(html_content, False, configuration=config, options=pdf_options)
        pdf_file = io.BytesIO(pdf_data)
        pdf_file.name = f"Report_{emp_id}.pdf"
        
        await update.message.reply_document(document=pdf_file, caption=f"تقرير الموظف: {emp_name}", reply_markup=markup)
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        await update.message.reply_text(f"حدث خطأ أثناء إنشاء ملف الـ PDF. تفاصيل الخطأ: {e}", reply_markup=markup)

# دالة إنشاء تقرير اليوم لجميع الموظفين وإرساله PDF
async def generate_today_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df = load_data()
    today_str = pd.Timestamp.now().strftime('%Y-%m-%d')
    df['Date_str'] = df['Date'].apply(clean_cell)
    today_df = df[df['Date_str'] == today_str]
    
    if today_df.empty:
        await update.message.reply_text(f"لا توجد أي سجلات بصمة مسجلة لتاريخ اليوم: {today_str}", reply_markup=markup)
        return

    html_content = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Arial', sans-serif; margin: 30px; text-align: center; }}
            h2 {{ color: #27ae60; border-bottom: 2px solid #2ecc71; padding-bottom: 10px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; direction: rtl; }}
            th, td {{ border: 1px solid #bdc3c7; padding: 12px; text-align: center; }}
            th {{ background-color: #27ae60; color: white; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
        </style>
    </head>
    <body>
        <h2>تقرير الحضور والانصراف لليوم: {today_str}</h2>
        <table>
            <tr>
                <th>الرقم الوظيفي</th>
                <th>الاسم</th>
                <th>وقت الدخول</th>
                <th>وقت الخروج</th>
                <th>الحالة</th>
            </tr>
    """
    for _, row in today_df.iterrows():
        html_content += f"""
            <tr>
                <td>{clean_cell(row['ID'])}</td>
                <td>{clean_cell(row['Name'])}</td>
                <td>{clean_cell(row['Time In'])}</td>
                <td>{clean_cell(row['Time Out'])}</td>
                <td>{clean_cell(row['Status'])}</td>
            </tr>
        """
    html_content += "</table></body></html>"

    try:
        pdf_data = pdfkit.from_string(html_content, False, configuration=config, options=pdf_options)
        pdf_file = io.BytesIO(pdf_data)
        pdf_file.name = f"Today_Report_{today_str}.pdf"
        await update.message.reply_document(document=pdf_file, caption=f"تقرير يوم: {today_str}", reply_markup=markup)
    except Exception as e:
        logger.error(f"Error generating today PDF: {e}")
        await update.message.reply_text(f"حدث خطأ أثناء تصدير تقرير اليوم: {e}", reply_markup=markup)

# دالة إنشاء كشف عام لجميع الموظفين بكل التواريخ
async def generate_all_employees_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df = load_data()
    if df.empty:
        await update.message.reply_text("قاعدة البيانات فارغة تماماً ولا توجد سجلات.", reply_markup=markup)
        return

    html_content = """
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <style>
            body { font-family: 'Arial', sans-serif; margin: 30px; text-align: center; }
            h2 { color: #2980b9; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; direction: rtl; }
            th, td { border: 1px solid #bdc3c7; padding: 10px; text-align: center; }
            th { background-color: #2980b9; color: white; }
            tr:nth-child(even) { background-color: #f2f2f2; }
        </style>
    </head>
    <body>
        <h2>التقرير العام لجميع الموظفين المسجلين</h2>
        <table>
            <tr>
                <th>الرقم الوظيفي</th>
                <th>الاسم</th>
                <th>التاريخ</th>
                <th>وقت الدخول</th>
                <th>وقت الخروج</th>
                <th>الحالة</th>
            </tr>
    """
    for _, row in df.iterrows():
        html_content += f"""
            <tr>
                <td>{clean_cell(row['ID'])}</td>
                <td>{clean_cell(row['Name'])}</td>
                <td>{clean_cell(row['Date'])}</td>
                <td>{clean_cell(row['Time In'])}</td>
                <td>{clean_cell(row['Time Out'])}</td>
                <td>{clean_cell(row['Status'])}</td>
            </tr>
        """
    html_content += "</table></body></html>"

    try:
        pdf_data = pdfkit.from_string(html_content, False, configuration=config, options=pdf_options)
        pdf_file = io.BytesIO(pdf_data)
        pdf_file.name = "All_Employees_Report.pdf"
        await update.message.reply_document(document=pdf_file, caption="التقرير العام لحضور الموظفين", reply_markup=markup)
    except Exception as e:
        logger.error(f"Error generating all report PDF: {e}")
        await update.message.reply_text(f"حدث خطأ أثناء تصدير التقرير الشامل: {e}", reply_markup=markup)

# إلغاء العملية الحالية والعودة للقائمة الرئيسية
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("تم إلغاء العملية.", reply_markup=markup)
    return CHOOSING

# دالة لتشغيل سيرفر وهمي لإرضاء سيرفر Render ومنعه من إغلاق البوت تلقائياً
def run_dummy_server():
    PORT = int(os.environ.get("PORT", 10000))
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        logger.info(f"Dummy web server running on port {PORT}")
        httpd.serve_forever()

# الدالة الأساسية لتشغيل البوت
def main() -> None:
    # تشغيل السيرفر الوهمي في خلفية البرنامج إذا كان البوت يشتغل كـ Web Service على Render
    if os.environ.get("PORT"):
        threading.Thread(target=run_dummy_server, daemon=True).start()

    # جلب التوكن الخاص بالبوت
    TOKEN = os.environ.get("TELEGRAM_TOKEN", "7787353133:AAFlb9gLqGsc0-jNnpxmY97PZOf_Lg-kR4I")
    
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING: [
                MessageHandler(filters.TEXT & ~(filters.COMMAND), regular_choice)
            ],
            TYPING_REPLY: [
                MessageHandler(filters.TEXT & ~(filters.COMMAND), received_information)
            ],
            TYPING_ID: [
                MessageHandler(filters.TEXT & ~(filters.COMMAND), received_id)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    
    # بدء تشغيل البوت بنظام الـ Polling
    application.run_polling()

if __name__ == '__main__':
    main()

