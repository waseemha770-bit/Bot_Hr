# استخدام نسخة بايثون الرسمية والمستقرة
FROM python:3.12-slim

# تثبيت حزم النظام المطلوبة وتثبيت wkhtmltopdf
RUN apt-get update && apt-get install -y --no-install-recommends \
    wkhtmltopdf \
    && rm -rf /var/lib/apt/lists/*

# تحديد مجلد العمل داخل الحاوية
WORKDIR /app

# نسخ ملف الاعتماديات وتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ بقية ملفات المشروع إلى الحاوية
COPY . .

# أمر تشغيل البوت عند بدء الحاوية
CMD ["python", "main.py"]
