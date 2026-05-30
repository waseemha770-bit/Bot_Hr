# استخدام نسخة بايثون مستقرة وخفيفة جداً
FROM python:3.10-slim

# تثبيت الأدوات الأساسية للنظام لتجنب مشاكل بناء الحزم
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# تحديد مجلد العمل داخل الحاوية
WORKDIR /app

# نسخ ملف المكتبات أولاً للاستفادة من الكاش
COPY requirements.txt .

# تثبيت المكتبات مع ترقية pip ومنع استخدام الكاش لتقليل المساحة
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع إلى الحاوية
COPY . .

# الأمر المسؤول عن تشغيل البوت
CMD ["python", "main.py"]

