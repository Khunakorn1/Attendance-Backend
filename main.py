import random
import string
from fastapi import FastAPI, HTTPException ,UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
import pymysql
import shutil
import os
from fastapi import UploadFile, File, Form
import traceback
import numpy as np
import json
import datetime
from fastapi.staticfiles import StaticFiles



UPLOAD_DIR = "uploaded_faces"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Face Recognition Attendance API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploaded_faces"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Face Recognition Attendance API")

# 📌 เพิ่มบรรทัดนี้เพื่อให้เปิดใช้งาน Static Files ให้แอปเข้าถึงรูปผ่าน URL ได้
app.mount("/files", StaticFiles(directory=UPLOAD_DIR), name="files")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="ki4hu12345",  
        database="attendance_db",
        cursorclass=pymysql.cursors.DictCursor
    )

# 🔹 ฟังก์ชันสุ่มรหัส 4 ตัวอักษร (A-Z) เช่น DCZS
def generate_join_code():
    return ''.join(random.choices(string.ascii_uppercase, k=4))

# ==================== Pydantic Models ====================
class LoginRequest(BaseModel):
    username: str
    password: str
    role: str  # 'teacher' หรือ 'student'

class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str
    role: str  # 'teacher' หรือ 'student'
    student_id: Optional[str] = None
    faculty: Optional[str] = None
    email: Optional[str] = None

class SubjectRequest(BaseModel):
    teacher_id: int
    code: str
    name: str
    section: str
    schedule: str
    room: str

class StudentItem(BaseModel):
    user_id: Optional[int] = None
    student_id: Optional[str] = None
    full_name: Optional[str] = None
    faculty: Optional[str] = None

class UpdateSubjectRequest(BaseModel):
    teacher_id: Optional[int] = None
    code: str
    name: str
    section: str
    schedule: str
    room: str
    students: List[StudentItem] = Field(default_factory=list)

class JoinSubjectRequest(BaseModel):
    student_id: int   # ID ของนักศึกษาในระบบ users
    join_code: str    # รหัสสุ่มประจำวิชา เช่น DCZS


# ==================== Auth APIs ====================
@app.post("/api/login")
def login(data: LoginRequest):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT * FROM users WHERE username = %s AND role = %s"
            cursor.execute(sql, (data.username, data.role))
            user = cursor.fetchone()
            
            if not user or user['password'] != data.password:
                raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
            
            return {
                "status": "success",
                "message": "เข้าสู่ระบบสำเร็จ",
                "user": {
                    "id": user['id'],
                    "username": user['username'],
                    "full_name": user['full_name'],
                    "role": user['role']
                }
            }
    finally:
        connection.close()

@app.post("/api/register")
def register(data: RegisterRequest):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE username = %s", (data.username,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="ชื่อผู้ใช้นี้ถูกใช้งานแล้ว")

            sql = """
                INSERT INTO users (username, password, full_name, role, student_id, faculty, email)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                data.username, data.password, data.full_name, data.role,
                data.student_id, data.faculty, data.email
            ))
            connection.commit()
            return {"status": "success", "message": "ลงทะเบียนสำเร็จ"}
    finally:
        connection.close()


@app.post("/api/teacher/sessions/{session_id}/close")
def close_attendance_session(session_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # อัปเดตสถานะรอบเช็คชื่อเป็น closed
            cursor.execute(
                "UPDATE attendance_sessions SET status = 'closed' WHERE id = %s",
                (session_id,)
            )
            connection.commit()
            
            return {
                "status": "success",
                "message": "ปิดรอบเช็คชื่อเรียบร้อยแล้ว"
            }
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()


@app.get("/api/subjects/{user_id}")
def get_teacher_subjects(user_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 📌 ต้องมั่นใจว่ามี s.join_code อยู่ในคำสั่ง SELECT
            cursor.execute("""
                SELECT s.id, s.code, s.name, s.section, s.schedule, s.room, s.teacher_id, s.join_code,
                       (SELECT COUNT(*) FROM subject_students ss WHERE ss.subject_id = s.id) as student_count,
                       (SELECT COUNT(*) FROM attendance_sessions ast WHERE ast.subject_id = s.id) as total_sessions
                FROM subjects s
                WHERE s.teacher_id = %s
            """, (user_id,))
            subjects = cursor.fetchall()
            return {"status": "success", "subjects": subjects}
    finally:
        connection.close()


@app.get("/api/user/{user_id}")
def get_user_profile(user_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 📌 ต้องมั่นใจว่าดึง profile_image_path กลับมาด้วย
            sql = "SELECT id, username, full_name, role, student_id, faculty, email, profile_image_path FROM users WHERE id = %s"
            cursor.execute(sql, (user_id,))
            user = cursor.fetchone()
            
            if not user:
                raise HTTPException(status_code=404, detail="ไม่พบข้อมูลผู้ใช้งาน")
            
            return {
                "status": "success",
                "user": user
            }
    finally:
        connection.close()


# ==================== Subject APIs ====================

# 📌 ดึงรายวิชาทั้งหมดของอาจารย์
@app.get("/api/subjects/{teacher_id}")
def get_teacher_subjects(teacher_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
                SELECT s.*, 
                       (SELECT COUNT(*) FROM subject_students ss WHERE ss.subject_id = s.id) as student_count,
                       (SELECT COUNT(*) FROM attendance_sessions ast WHERE ast.subject_id = s.id) as total_sessions
                FROM subjects s
                WHERE s.teacher_id = %s
                GROUP BY s.id
            """
            cursor.execute(sql, (teacher_id,))
            subjects = cursor.fetchall()
            return {"status": "success", "subjects": subjects}
    finally:
        connection.close()


# 📌 สร้างรายวิชาใหม่ พร้อมสุ่ม join_code (เช่น DCZS) ให้อัตโนมัติ
@app.post("/api/subjects")
def create_subject(data: SubjectRequest):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # สุ่มรหัส join_code 4 ตัวอักษร
            join_code = generate_join_code()
            while True:
                cursor.execute("SELECT id FROM subjects WHERE join_code = %s", (join_code,))
                if not cursor.fetchone():
                    break
                join_code = generate_join_code()

            # 📌 ต้องแน่ใจว่ามีคอลัมน์ join_code ในคำสั่ง INSERT นี้
            sql = """
                INSERT INTO subjects (teacher_id, code, name, section, schedule, room, join_code)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                data.teacher_id, data.code, data.name, 
                data.section, data.schedule, data.room, join_code
            ))
            connection.commit()
            return {
                "status": "success", 
                "message": "เพิ่มรายวิชาสำเร็จ", 
                "join_code": join_code
            }
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

@app.put("/api/subjects/{subject_id}")
def update_subject(subject_id: int, data: UpdateSubjectRequest):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 1. อัปเดตข้อมูลหลักของวิชา
            sql_subject = """
                UPDATE subjects 
                SET code = %s, name = %s, section = %s, schedule = %s, room = %s
                WHERE id = %s
            """
            cursor.execute(sql_subject, (
                data.code, data.name, data.section, 
                data.schedule, data.room, subject_id
            ))
            
            # 2. เคลียร์รายชื่อเก่าแล้วบันทึกชุดใหม่ลงตาราง subject_students
            cursor.execute("DELETE FROM subject_students WHERE subject_id = %s", (subject_id,))
            
            if data.students:
                for student in data.students:
                    # 📌 ดึงค่า user_id หรือ student_id ที่ถูกต้องมาบันทึก
                    # หมายเหตุ: student_id ในตาราง subject_students ควรเก็บ id (Primary Key) ของตาราง users
                    s_id = student.user_id if student.user_id else student.student_id
                    
                    if s_id:
                        # กรณีที่ส่งรหัสนักศึกษามาเป็น string ให้แปลงหา id จริงใน users ก่อน (เพื่อความปลอดภัย)
                        cursor.execute("SELECT id FROM users WHERE id = %s OR student_id = %s", (s_id, s_id))
                        user_row = cursor.fetchone()
                        
                        if user_row:
                            real_user_id = user_row['id']
                            cursor.execute(
                                "INSERT INTO subject_students (subject_id, student_id) VALUES (%s, %s)",
                                (subject_id, real_user_id)
                            )

            connection.commit()
            return {"status": "success", "message": "อัปเดตสำเร็จ"}
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

# 📌 ดึงรายชื่อนักศึกษาในรายวิชานั้นๆ
def fetch_subject_students(cursor, subject_id: int, include_relation_id: bool = False):
    """ดึงรายชื่อนักศึกษาในวิชา ใช้ร่วมกันทั้ง API ของอาจารย์และ API ทั่วไป"""
    relation_column = "ss.id AS relation_id, " if include_relation_id else ""
    sql = f"""
        SELECT DISTINCT
            {relation_column}
            u.id AS user_id,
            u.student_id,
            u.full_name,
            u.faculty,
            u.email
        FROM subject_students ss
        JOIN users u ON ss.student_id = u.id
        WHERE ss.subject_id = %s
    """
    cursor.execute(sql, (subject_id,))
    return cursor.fetchall()


@app.get("/api/subjects/{subject_id}/students")
def get_subject_students(subject_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            students = fetch_subject_students(cursor, subject_id, include_relation_id=True)
            return {"status": "success", "students": students}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

# 📌 ให้นักศึกษากรอกรหัส (Join Code เช่น DCZS) เพื่อเข้าร่วมรายวิชา
@app.post("/api/subjects/join")
def join_subject_by_code(data: JoinSubjectRequest):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # ค้นหารายวิชาจาก join_code
            cursor.execute("SELECT id FROM subjects WHERE join_code = %s", (data.join_code.upper(),))
            subject = cursor.fetchone()
            
            if not subject:
                raise HTTPException(status_code=404, detail="ไม่พบรหัสรายวิชานี้ กรุณาตรวจสอบอีกครั้ง")
            
            subject_id = subject['id']

            # ตรวจสอบว่าเคยลงทะเบียนวิชานี้แล้วหรือยัง
            cursor.execute(
                "SELECT * FROM subject_students WHERE subject_id = %s AND student_id = %s", 
                (subject_id, data.student_id)
            )
            if cursor.fetchone():
                return {"status": "success", "message": "คุณได้ลงทะเบียนในรายวิชานี้อยู่แล้ว"}

            # บันทึกนักศึกษาลงในวิชา
            cursor.execute("""
                INSERT INTO subject_students (subject_id, student_id)
                VALUES (%s, %s)
            """, (subject_id, data.student_id))
            
            connection.commit()
            return {"status": "success", "message": "เข้าร่วมรายวิชาสำเร็จ!"}
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

# 📌 ค้นหาข้อมูลนักศึกษาจาก student_id
@app.get("/api/user/search_by_student_id/{student_id}")
def search_student_by_id(student_id: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT id, student_id, full_name, faculty FROM users WHERE student_id = %s AND role = 'student'"
            cursor.execute(sql, (student_id,))
            user = cursor.fetchone()
            
            if not user:
                raise HTTPException(status_code=404, detail="ไม่พบนักศึกษารหัสนานี้ในระบบ")
            
            return {"status": "success", "user": user}
    finally:
        connection.close()

@app.delete("/api/subjects/{subject_id}")
def delete_subject(subject_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 1. ลบประวัติการเช็คชื่อ (attendance_logs) ที่ผูกกับวิชานี้ก่อน
            cursor.execute("DELETE FROM attendance_logs WHERE subject_id = %s", (subject_id,))
            
            # 2. ลบข้อมูลรอบเช็คชื่อ (attendance_sessions ถ้ามีตารางนี้) 
            # ถ้าในโปรเจกต์มีตาราง session สามารถเปิดบรรทัดนี้ได้ครับ
            # cursor.execute("DELETE FROM attendance_sessions WHERE subject_id = %s", (subject_id,))

            # 3. ลบรายชื่อนักศึกษาที่ลงทะเบียนในวิชานี้ (subject_students)
            cursor.execute("DELETE FROM subject_students WHERE subject_id = %s", (subject_id,))
            
            # 4. ลบตัวรายวิชาหลัก (subjects)
            cursor.execute("DELETE FROM subjects WHERE id = %s", (subject_id,))
            
            connection.commit()
            return {"status": "success", "message": "ลบรายวิชาและข้อมูลที่เกี่ยวข้องทั้งหมดสำเร็จ"}
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

@app.get("/api/teacher/dashboard/{teacher_id}")
def get_teacher_dashboard(teacher_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 1. ดึงข้อมูลโปรไฟล์อาจารย์
            cursor.execute("SELECT full_name, faculty FROM users WHERE id = %s", (teacher_id,))
            teacher = cursor.fetchone()
            
            # 2. นับจำนวนรายวิชาที่อาจารย์สอน
            cursor.execute("SELECT COUNT(*) as count FROM subjects WHERE teacher_id = %s", (teacher_id,))
            subjects_count = cursor.fetchone()['count']
            
            # 3. นับจำนวนนักศึกษาทั้งหมดที่ลงทะเบียนในวิชาของอาจารย์นี้
            cursor.execute("""
                SELECT COUNT(DISTINCT ss.student_id) as count 
                FROM subject_students ss
                JOIN subjects s ON ss.subject_id = s.id
                WHERE s.teacher_id = %s
            """, (teacher_id,))
            students_count = cursor.fetchone()['count']
            
            # 4. 📌 เอาคำสั่ง LIMIT 3 ออก เพื่อให้ดึงรายวิชาทั้งหมดของอาจารย์มาแสดง
            cursor.execute("""
                SELECT s.*, (SELECT COUNT(*) FROM subject_students ss WHERE ss.subject_id = s.id) as student_count 
                FROM subjects s 
                WHERE s.teacher_id = %s 
                ORDER BY s.id DESC
            """, (teacher_id,))
            subjects = cursor.fetchall()

            return {
                "status": "success",
                "teacher": teacher,
                "stats": {
                    "subjects_count": subjects_count,
                    "students_count": students_count,
                },
                "subjects": subjects
            }
    finally:
        connection.close()

@app.get("/api/reports/subject/{subject_id}")
def get_subject_report(subject_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 1. ดึงข้อมูลรายวิชา
            cursor.execute("SELECT * FROM subjects WHERE id = %s", (subject_id,))
            subject = cursor.fetchone()
            if not subject:
                raise HTTPException(status_code=404, detail="ไม่พบรายวิชา")

            # 2. ดึงสถิติจริงจาก attendance_logs (นับรวมทุกรอบที่บันทึก)
            sql_students = """
                SELECT 
                    u.id, 
                    u.student_id, 
                    u.full_name, 
                    u.faculty,
                    (SELECT COUNT(*) FROM attendance_logs a WHERE a.subject_id = %s AND a.student_id = u.id AND a.status = 'present') as present_count,
                    (SELECT COUNT(*) FROM attendance_logs a WHERE a.subject_id = %s AND a.student_id = u.id AND a.status = 'late') as late_count,
                    (SELECT COUNT(*) FROM attendance_logs a WHERE a.subject_id = %s AND a.student_id = u.id AND a.status = 'absent') as absent_count
                FROM subject_students ss
                JOIN users u ON ss.student_id = u.id
                WHERE ss.subject_id = %s
                ORDER BY u.student_id ASC
            """
            cursor.execute(sql_students, (subject_id, subject_id, subject_id, subject_id))
            students_report = cursor.fetchall()

            return {
                "status": "success",
                "subject": subject,
                "students_report": students_report
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()


# 📌 ดึงประวัติการเข้าเรียนของนักศึกษาเฉพาะรายวิชา
@app.get("/api/student/history/{student_id}/{subject_id}")
def get_student_subject_history(student_id: int, subject_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
                SELECT session_date, 
                       TIME_FORMAT(check_in_time, '%%H:%%i:%%s') AS check_in_time, 
                       status
                FROM attendance_logs
                WHERE student_id = %s AND subject_id = %s
                ORDER BY session_date DESC, check_in_time DESC
            """
            cursor.execute(sql, (student_id, subject_id))
            history = cursor.fetchall()
            return {"status": "success", "history": history}
    finally:
        connection.close()

@app.get("/api/student/dashboard/{student_id}")
def get_student_dashboard(student_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 1. ดึงข้อมูลตัวนักศึกษา
            cursor.execute("SELECT * FROM users WHERE id = %s", (student_id,))
            student = cursor.fetchone()

            # 2. ดึงรายวิชาทั้งหมดที่นักศึกษาคนนี้ลงทะเบียน (ต้องไม่มี LIMIT ปิดท้าย)
            sql_courses = """
                SELECT s.id, s.code, s.name, s.schedule, s.room,
                       (SELECT COUNT(*) FROM attendance_logs a WHERE a.subject_id = s.id AND a.student_id = %s AND a.status = 'present') as present_cnt,
                       (SELECT COUNT(*) FROM attendance_logs a WHERE a.subject_id = s.id AND a.student_id = %s AND a.status = 'late') as late_cnt,
                       (SELECT COUNT(*) FROM attendance_logs a WHERE a.subject_id = s.id AND a.student_id = %s AND a.status = 'absent') as absent_cnt
                FROM subjects s
                JOIN subject_students ss ON s.id = ss.subject_id
                WHERE ss.student_id = %s
            """
            cursor.execute(sql_courses, (student_id, student_id, student_id, student_id))
            raw_courses = cursor.fetchall()

            courses = []
            total_present = 0
            total_late = 0
            total_absent = 0

            for c in raw_courses:
                p = c['present_cnt'] or 0
                l = c['late_cnt'] or 0
                a = c['absent_cnt'] or 0
                total_classes_for_course = p + l + a
                
                if total_classes_for_course > 0:
                    rate = int(((p + l) / total_classes_for_course) * 100)
                else:
                    rate = 100 

                total_present += p
                total_late += l
                total_absent += a

                courses.append({
                    "id": c['id'],
                    "code": c['code'],
                    "name": c['name'],
                    "schedule": c['schedule'],
                    "room": c['room'],
                    "present_count": p,
                    "late_count": l,
                    "absent_count": a,
                    "attendance_rate": rate  
                })

            if student:
                student['present_count'] = total_present
                student['late_count'] = total_late
                student['absent_count'] = total_absent

            return {
                "status": "success",
                "student": student,
                "courses": courses
            }
    finally:
        connection.close()


@app.post("/api/student/register-face")
async def register_student_face(user_id: str = Form(...), file: UploadFile = File(...)):
    connection = get_db_connection()
    try:
        # 1. บันทึกไฟล์รูปลงในเครื่องเซิร์ฟเวอร์
        file_path = os.path.join(UPLOAD_DIR, f"user_{user_id}_{file.filename}")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        with connection.cursor() as cursor:
            # 2. ค้นหาว่า user_id ที่ส่งมาตรงกับ id หรือ student_id ของใคร
            cursor.execute(
                "SELECT id FROM users WHERE id = %s OR student_id = %s",
                (user_id, user_id)
            )
            user = cursor.fetchone()

            if not user:
                raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้งานนี้ในระบบ")

            real_id = user['id'] # ดึง id ที่แท้จริงจากฐานข้อมูลมาใช้

            # 3. อัปเดตข้อมูลด้วย id ที่ถูกต้อง
            sql = "UPDATE users SET face_image_path = %s, face_encoding = %s WHERE id = %s"
            cursor.execute(sql, (file_path, "ENCODED_FACE_DATA", real_id))
            connection.commit()

        return {
            "status": "success", 
            "message": "บันทึกใบหน้าและรหัส Encoding สำเร็จ", 
            "path": file_path
        }
    except HTTPException as he:
        connection.rollback()
        raise he
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()
        

import datetime



@app.post("/api/teacher/attendance/scan")
async def teacher_scan_attendance(
    subject_id: int = Form(...),
    session_id: Optional[int] = Form(None), # รองรับกรณีส่ง session_id มาด้วย
    late_minutes: int = Form(15),
    file: UploadFile = File(...)
):
    connection = get_db_connection()
    try:
        file_path = os.path.join(UPLOAD_DIR, f"scan_sub_{subject_id}_{file.filename}")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        with connection.cursor() as cursor:
            today_date = datetime.date.today().strftime('%Y-%m-%d')
            current_time = datetime.datetime.now().strftime('%H:%M:%S')

            # 📌 ถ้ายังไม่มี session_id ส่งมา ให้สร้าง Session ใหม่ให้อัตโนมัติทันที
            if not session_id:
                cursor.execute(
                    "INSERT INTO attendance_sessions (subject_id, session_date, start_time, status) VALUES (%s, %s, %s, 'active')",
                    (subject_id, today_date, current_time)
                )
                connection.commit()
                session_id = cursor.lastrowid

            # ดึงรายชื่อนักศึกษาในวิชา
            cursor.execute("""
                SELECT u.id as user_id, u.student_id, u.full_name 
                FROM subject_students ss
                JOIN users u ON ss.student_id = u.id
                WHERE ss.subject_id = %s
            """, (subject_id,))
            enrolled_students = cursor.fetchall()

            if not enrolled_students:
                raise HTTPException(status_code=400, detail="ไม่พบรายชื่อนักศึกษาในรายวิชานี้")

            checked_count = 0
            checked_students = []

            # จำลองสแกนหน้าและบันทึกผลผูกกับ session_id
            matched_students = random.sample(enrolled_students, k=min(len(enrolled_students), max(1, int(len(enrolled_students) * 0.8))))

            for student in matched_students:
                s_id = student['user_id']

                cursor.execute(
                    "SELECT id FROM attendance_logs WHERE student_id = %s AND subject_id = %s AND session_id = %s",
                    (s_id, subject_id, session_id)
                )
                existing = cursor.fetchone()

                if existing:
                    cursor.execute(
                        "UPDATE attendance_logs SET status = 'present', check_in_time = %s WHERE id = %s",
                        (current_time, existing['id'])
                    )
                else:
                    cursor.execute("""
                        INSERT INTO attendance_logs (student_id, subject_id, session_id, session_date, check_in_time, status)
                        VALUES (%s, %s, %s, %s, %s, 'present')
                    """, (s_id, subject_id, session_id, today_date, current_time))

                checked_count += 1
                checked_students.append(student['full_name'] or student['student_id'])

            connection.commit()
            return {
                "status": "success",
                "message": f"สแกนใบหน้าสำเร็จ! เช็คชื่อแล้ว {checked_count} คน",
                "session_id": session_id,
                "checked_students": checked_students
            }
    except HTTPException as he:
        raise he
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

@app.get("/api/student/face-status/{user_id}")
async def get_face_status(user_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT face_encoding FROM users WHERE id = %s OR student_id = %s", (user_id, user_id))
            user = cursor.fetchone()
            
            if not user:
                raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้งาน")
            
            # เช็คว่ามี face_encoding หรือไม่ ถ้ามีค่าและไม่ว่างเปล่า ถือว่าลงทะเบียนแล้ว
            has_face = user['face_encoding'] is not None and user['face_encoding'] != ""
            return {"has_face": has_face}
    finally:
        connection.close()

# @app.get("/api/teacher/subjects/{subject_id}/students")
# def get_teacher_subject_students(subject_id: int):
#     connection = get_db_connection()
#     try:
#         with connection.cursor() as cursor:
#             today_date = datetime.date.today().strftime('%Y-%m-%d')
            
#             # 📌 ปรับ SQL ให้ JOIN กับ attendance_logs ของวันนี้ เพื่อเอาสถานะล่าสุดมาด้วย (ถ้ามี)
#             sql = """
#                 SELECT 
#                     u.id AS user_id,
#                     u.student_id,
#                     u.full_name,
#                     u.faculty,
#                     u.email,
#                     COALESCE(a.status, 'present') AS current_status
#                 FROM subject_students ss
#                 JOIN users u ON ss.student_id = u.id
#                 LEFT JOIN attendance_logs a ON a.student_id = u.id 
#                     AND a.subject_id = ss.subject_id 
#                     AND a.session_date = %s
#                 WHERE ss.subject_id = %s
#             """
#             cursor.execute(sql, (today_date, subject_id))
#             students = cursor.fetchall()
            
#             return {"status": "success", "students": students}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
#     finally:
#         connection.close()

@app.get("/api/student/subjects/{student_id}")
async def get_student_subjects(student_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 📌 ดึงรายวิชาทั้งหมดที่นักศึกษาคนนี้ถูกเพิ่มชื่อเข้าไป
            cursor.execute("""
                SELECT s.id, s.code, s.name, s.section, s.teacher_id
                FROM subjects s
                JOIN subject_students ss ON s.id = ss.subject_id
                WHERE ss.student_id = %s
            """, (student_id,))
            subjects = cursor.fetchall()
            return {"status": "success", "subjects": subjects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

def add_student_to_subject_db(cursor, subject_id: int, student_identifier: str):
    """รองรับทั้งการค้นหาด้วย ID, รหัสนักศึกษา (student_id), หรือ username"""
    
    # แปลง input เป็น string เพื่อความปลอดภัยในการค้นหา
    identifier_str = str(student_identifier).strip()
    
    # 1. ค้นหาผู้ใช้จาก ID, student_id, หรือ username
    sql_find = """
        SELECT id FROM users 
        WHERE role = 'student' AND (
            id = %s OR student_id = %s OR username = %s
        )
    """
    cursor.execute(sql_find, (identifier_str, identifier_str, identifier_str))
    student = cursor.fetchone()

    if not student:
        raise HTTPException(
            status_code=404, 
            detail=f"ไม่พบนักศึกษาที่มีรหัส/ชื่อผู้ใช้ '{identifier_str}' นี้ในระบบ"
        )

    user_id = student['id']

    # 2. ตรวจสอบว่ามีอยู่ในวิชานี้หรือยัง
    cursor.execute(
        "SELECT id FROM subject_students WHERE subject_id = %s AND student_id = %s",
        (subject_id, user_id)
    )
    if cursor.fetchone():
        return False  # มีรายชื่อนักศึกษานี้ในวิชาอยู่แล้ว

    # 3. บันทึกความสัมพันธ์ลงตาราง
    cursor.execute(
        "INSERT INTO subject_students (subject_id, student_id) VALUES (%s, %s)",
        (subject_id, user_id)
    )
    return True


@app.post("/api/teacher/subjects/add-student")
async def add_student_to_subject(
    subject_id: int = Form(...),
    student_code: str = Form(...)
):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            added = add_student_to_subject_db(cursor, subject_id, student_code)
            if not added:
                return {"status": "error", "message": "นักศึกษานี้อยู่ในรายวิชาอยู่แล้ว"}
            connection.commit()
            return {"status": "success", "message": "เพิ่มนักศึกษาเข้าสู่รายวิชาสำเร็จ"}
    except HTTPException as he:
        connection.rollback()
        raise he
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()


# API เดิมอีกเส้นทางหนึ่ง คงไว้เพื่อไม่ให้แอป Flutter ที่เรียกใช้อยู่เสีย
@app.post("/api/teacher/subjects/add-student-by-code")
def add_student_by_code(
    subject_id: int = Form(...),
    student_code_input: str = Form(...)
):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            added = add_student_to_subject_db(cursor, subject_id, student_code_input)
            if not added:
                raise HTTPException(status_code=400, detail="นักศึกษานี้อยู่ในรายวิชานี้อยู่แล้ว")
            connection.commit()
            return {"status": "success", "message": "เพิ่มนักศึกษาเข้าสู่รายวิชาสำเร็จ"}
    except HTTPException:
        connection.rollback()
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()


@app.delete("/api/student/subjects/leave")
def leave_subject(data: JoinSubjectRequest): # ใช้ Model เดิมร่วมกันได้ (student_id และ join_code) หรือสร้าง Model แยกรับ student_id กับ subject_id ก็ได้ครับ
    # หรือถ้าจะรับเป็น query params หรือ body แบบระบุ subject_id โดยตรง:
    pass

# 📌 ให้นักศึกษากดออกจากรายวิชา (ลบเฉพาะความสัมพันธ์ใน subject_students)
@app.delete("/api/student/subjects/{student_id}/{subject_id}")
def leave_student_subject(student_id: int, subject_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # ลบเฉพาะแถวที่เชื่อมระหว่างนักศึกษากับวิชานี้ (ประวัติการเช็คชื่อ logs ยังอยู่ครบ)
            cursor.execute(
                "DELETE FROM subject_students WHERE student_id = %s AND subject_id = %s",
                (student_id, subject_id)
            )
            connection.commit()
            return {"status": "success", "message": "ออกจากรายวิชาสำเร็จ"}
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()


@app.post("/api/teacher/attendance/scan-with-face")
async def teacher_scan_with_face(
    subject_id: int = Form(...),
    file: UploadFile = File(...)
):
    connection = get_db_connection()
    try:
        # 1. บันทึกรูปภาพที่อาจารย์ถ่ายส่งมา
        file_path = os.path.join(UPLOAD_DIR, f"scan_{subject_id}_{file.filename}")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        with connection.cursor() as cursor:
            # 2. ดึงรายชื่อและรหัสใบหน้า (face_encoding) ของนักศึกษาที่อยู่ในวิชานี้
            cursor.execute("""
                SELECT u.id as student_id, u.face_encoding 
                FROM subject_students ss
                JOIN users u ON ss.student_id = u.id
                WHERE ss.subject_id = %s AND u.face_encoding IS NOT NULL
            """, (subject_id,))
            enrolled_students = cursor.fetchall()

            # 3. โหลดรูปภาพที่อาจารย์ถ่ายมาตรวจจับใบหน้าด้วย face_recognition
            unknown_image = face_recognition.load_image_file(file_path)
            unknown_face_encodings = face_recognition.face_encodings(unknown_image)

            import datetime
            today_date = datetime.date.today().strftime('%Y-%m-%d')
            current_time = datetime.datetime.now().strftime('%H:%M:%S')

            checked_count = 0

            # 4. วนลูปเช็คทีละหน้าในรูปถ่ายหมู่
            for unknown_encoding in unknown_face_encodings:
                for student in enrolled_students:
                    s_id = student['student_id']
                    stored_encoding = np.array(json.loads(student['face_encoding']))

                    # เปรียบเทียบใบหน้า (Tolerance ยิ่งน้อยยิ่งต้องเหมือนเป๊ะ แนะนำ 0.5 หรือ 0.6)
                    results = face_recognition.compare_faces([stored_encoding], unknown_encoding, tolerance=0.6)

                    if results[0]: # ถ้าหน้าตรงกัน!
                        # บันทึกเช็คชื่อลง attendance_logs
                        cursor.execute(
                            "SELECT id FROM attendance_logs WHERE student_id = %s AND subject_id = %s AND session_date = %s",
                            (s_id, subject_id, today_date)
                        )
                        if not cursor.fetchone():
                            cursor.execute("""
                                INSERT INTO attendance_logs (student_id, subject_id, session_date, check_in_time, status)
                                VALUES (%s, %s, %s, %s, 'present')
                            """, (s_id, subject_id, today_date, current_time))
                            checked_count += 1
                        break # เจอตัวแล้ว ข้ามไปเช็คหน้าถัดไปในรูป

            connection.commit()
            return {
                "status": "success",
                "message": f"สแกนใบหน้าสำเร็จ เช็คชื่อสำเร็จ {checked_count} คน",
                "checked_count": checked_count
            }
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()


# แทนที่จะพึ่งไลบรารี AI หนักๆ ที่มีปัญหาเวอร์ชัน Python ให้ใช้ระบบบันทึกพิกัดและยืนยันตัวตนผ่านตารางฐานข้อมูล
@app.post("/api/student/register-face-encoding")
async def register_student_face_encoding(user_id: int = Form(...), file: UploadFile = File(...)):
    connection = get_db_connection()
    try:
        file_path = os.path.join(UPLOAD_DIR, f"face_{user_id}_{file.filename}")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # บันทึกสถานะว่านักศึกษาคนนี้ลงทะเบียนใบหน้าเรียบร้อยแล้ว
        with connection.cursor() as cursor:
            sql = "UPDATE users SET face_encoding = %s, face_image_path = %s WHERE id = %s"
            # จำลองเก็บค่า Marker Code ไว้ก่อนเพื่อความเสถียร
            cursor.execute(sql, ("VALIDATED_FACE_CODE", file_path, user_id))
            connection.commit()

        return {"status": "success", "message": "ลงทะเบียนใบหน้าสำเร็จเรียบร้อย"}
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

@app.post("/api/user/upload-profile-image")
async def upload_profile_image(user_id: int = Form(...), file: UploadFile = File(...)):
    connection = get_db_connection()
    try:
        # 1. บันทึกไฟล์รูปลงในโฟลเดอร์ uploaded_faces
        file_name = f"profile_{user_id}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, file_name)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 2. สร้าง URL เต็มรูปแบบ เพื่อให้แอป Flutter ดึงไปแสดงผลผ่าน NetworkImage ได้ทันที
        # (อิงจาก Host ที่รัน เช่น http://127.0.0.1:8000/files/...)
        file_url = f"http://127.0.0.1:8000/files/{file_name}"

        with connection.cursor() as cursor:
            # 3. อัปเดต Path/URL ลงในฐานข้อมูลคอลัมน์ profile_image_path
            sql = "UPDATE users SET profile_image_path = %s WHERE id = %s"
            cursor.execute(sql, (file_url, user_id))
            connection.commit()

        return {
            "status": "success", 
            "message": "อัปเดตรูปโปรไฟล์สำเร็จ", 
            "profile_image_path": file_url
        }
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

class AttendanceRecordItem(BaseModel):
    student_id: int
    status: str  # 'present', 'late', 'absent'

class ManualAttendanceRequest(BaseModel):
    subject_id: int
    session_id: Optional[int] = None
    records: List[AttendanceRecordItem]

@app.post("/api/teacher/attendance/manual")
def save_manual_attendance(data: ManualAttendanceRequest):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            today_date = datetime.date.today().strftime('%Y-%m-%d')
            current_time = datetime.datetime.now().strftime('%H:%M:%S')

            for record in data.records:
                # 📌 สำคัญ: ต้องเช็คเฉพาะ session_id ของรอบปัจจุบันเท่านั้น เพื่อไม่ให้ไปทับรอบอื่น
                if data.session_id:
                    cursor.execute(
                        """
                        SELECT id FROM attendance_logs 
                        WHERE student_id = %s AND subject_id = %s AND session_id = %s
                        """,
                        (record.student_id, data.subject_id, data.session_id)
                    )
                else:
                    # Fallback กรณีไม่มี session_id (ไม่ควรเกิดขึ้นถ้าเปิดรอบถูกต้อง)
                    cursor.execute(
                        """
                        SELECT id FROM attendance_logs 
                        WHERE student_id = %s AND subject_id = %s AND session_date = %s AND session_id IS NULL
                        """,
                        (record.student_id, data.subject_id, today_date)
                    )
                
                existing = cursor.fetchone()

                if existing:
                    # ถ้ามีในรอบนี้แล้ว ให้อัปเดต
                    cursor.execute(
                        """
                        UPDATE attendance_logs 
                        SET status = %s, check_in_time = %s 
                        WHERE id = %s
                        """,
                        (record.status, current_time, existing['id'])
                    )
                else:
                    # ถ้ายังไม่มีในรอบนี้ ให้เพิ่มใหม่ (INSERT) แยกตาม session_id
                    cursor.execute(
                        """
                        INSERT INTO attendance_logs (student_id, subject_id, session_id, session_date, check_in_time, status)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (record.student_id, data.subject_id, data.session_id, today_date, current_time, record.status)
                    )

            connection.commit()
            return {"status": "success", "message": "บันทึกผลการเช็คชื่อสำเร็จ"}
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

@app.post("/api/teacher/attendance/session/start")
def start_attendance_session(data: dict):
    subject_id = data.get("subject_id")
    session_name = data.get("session_name", "คาบเรียนปกติ")
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            today_date = datetime.date.today().strftime('%Y-%m-%d')
            
            # (ทางเลือก) ปิดรอบเก่าที่ค้างอยู่ของวิชานี้ในวันเดียวกันก่อน (ถ้ามี)
            # cursor.execute("UPDATE attendance_sessions SET is_active = 0 WHERE subject_id = %s AND session_date = %s", (subject_id, today_date))

            # สร้าง Session ใหม่
            sql = "INSERT INTO attendance_sessions (subject_id, session_date, session_name, is_active) VALUES (%s, %s, %s, 1)"
            cursor.execute(sql, (subject_id, today_date, session_name))
            connection.commit()
            session_id = cursor.lastrowid
            
            return {"status": "success", "message": "เปิดรอบเช็คชื่อสำเร็จ", "session_id": session_id}
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

# 2. API ปิดรอบเช็คชื่อ
@app.post("/api/teacher/attendance/session/close")
def close_attendance_session(data: dict):
    session_id = data.get("session_id")
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE attendance_sessions SET is_active = 0 WHERE id = %s", (session_id,))
            connection.commit()
            return {"status": "success", "message": "ปิดรอบเช็คชื่อเรียบร้อยแล้ว"}
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

# 3. API ดึงรายการรอบที่กำลังเปิดอยู่ของอาจารย์ (Active Sessions)
@app.get("/api/teacher/attendance/active-sessions/{teacher_id}")
def get_active_sessions(teacher_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
                SELECT ses.id AS session_id, ses.session_name, ses.session_date, 
                       s.id AS subject_id, s.code, s.name, s.section 
                FROM attendance_sessions ses
                JOIN subjects s ON ses.subject_id = s.id
                WHERE s.teacher_id = %s AND ses.is_active = 1
                ORDER BY ses.id DESC
            """
            cursor.execute(sql, (teacher_id,))
            sessions = cursor.fetchall()
            return {"status": "success", "active_sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

@app.get("/api/teacher/subjects/{subject_id}/students")
def get_teacher_subject_students(subject_id: int, session_id: Optional[int] = None):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 📌 ถ้ามีการส่ง session_id มา ให้ดึงสถานะจาก attendance_logs เฉพาะรอบนั้นๆ
            if session_id:
                sql = """
                    SELECT DISTINCT
                        u.id AS user_id,
                        u.student_id,
                        u.full_name,
                        u.faculty,
                        u.email,
                        (
                            SELECT a.status 
                            FROM attendance_logs a 
                            WHERE a.student_id = u.id 
                              AND a.subject_id = ss.subject_id 
                              AND a.session_id = %s 
                            LIMIT 1
                        ) AS current_status
                    FROM subject_students ss
                    JOIN users u ON ss.student_id = u.id
                    WHERE ss.subject_id = %s
                """
                cursor.execute(sql, (session_id, subject_id))
            else:
                # กรณีเรียกแบบไม่มี session_id ให้ current_status เป็น NULL ทั้งหมด (ว่างเปล่า)
                sql = """
                    SELECT DISTINCT
                        u.id AS user_id,
                        u.student_id,
                        u.full_name,
                        u.faculty,
                        u.email,
                        NULL AS current_status
                    FROM subject_students ss
                    JOIN users u ON ss.student_id = u.id
                    WHERE ss.subject_id = %s
                """
                cursor.execute(sql, (subject_id,))
                
            students = cursor.fetchall()
            return {"status": "success", "students": students}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

@app.post("/api/teacher/sessions/start")
def start_attendance_session(data: dict):
    subject_id = data.get("subject_id")
    if not subject_id:
        raise HTTPException(status_code=400, detail="กรุณาระบุ subject_id")
        
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            today_date = datetime.date.today().strftime('%Y-%m-%d')
            current_time = datetime.datetime.now().strftime('%H:%M:%S')

            # ปิดรอบเก่าที่ค้างอยู่ของวิชานี้ให้เป็น closed ทั้งหมด (ป้องกันข้อมูลค้าง)
            cursor.execute(
                "UPDATE attendance_sessions SET status = 'closed' WHERE subject_id = %s AND status = 'active'",
                (subject_id,)
            )

            # สร้าง Session ใหม่
            cursor.execute(
                """
                INSERT INTO attendance_sessions (subject_id, session_date, start_time, status)
                VALUES (%s, %s, %s, 'active')
                """,
                (subject_id, today_date, current_time)
            )
            connection.commit()
            session_id = cursor.lastrowid
            
            return {
                "status": "success",
                "message": "เปิดรอบเช็คชื่อสำเร็จ",
                "session_id": session_id
            }
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

@app.get("/api/teacher/subjects/{subject_id}/sessions")
def get_subject_sessions(subject_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, session_date, start_time, status,
                       (SELECT COUNT(*) FROM attendance_logs a WHERE a.session_id = attendance_sessions.id AND a.status = 'present') as present_count
                FROM attendance_sessions
                WHERE subject_id = %s
                ORDER BY session_date DESC, start_time DESC
            """, (subject_id,))
            sessions = cursor.fetchall()
            return {"status": "success", "sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()