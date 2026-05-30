import os
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Float, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from cryptography.fernet import Fernet

DATABASE_URL = "sqlite:///hr_enterprise_database.db"

# 🔒 مفتاح تشفير ثابت لبيانات الرواتب لحماية الخصوصية
STATIC_KEY = b'uF8gK3m_Xz9-v1WpQLr4TY7N2sEb6GcHvA1jD4xO5k8='
cipher_suite = Fernet(STATIC_KEY)

Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def encrypt_data(data: str) -> str:
    """تشفير البيانات الحساسة مثل الرواتب قبل حفظها"""
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(data: str) -> str:
    """فك تشفير البيانات عند العرض"""
    try:
        if not data: return "0.0"
        return cipher_suite.decrypt(data.encode()).decode()
    except Exception:
        return "0.0"

class Employee(Base):
    __tablename__ = "employees"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False, unique=True)
    telegram_id = Column(String, nullable=True)
    role = Column(String, default="Employee") # Owner, Admin, Employee
    department = Column(String, default="العلاقات العامة")
    title = Column(String, default="موظف")
    encrypted_salary = Column(String) # حقل مشفر بالكامل
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
    status = Column(String, default="قيد المراجعة")
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)

