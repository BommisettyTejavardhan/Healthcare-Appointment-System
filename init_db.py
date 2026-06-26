import mysql.connector
from werkzeug.security import generate_password_hash

def init_db():
    conn = mysql.connector.connect(
        host='localhost',
        user='root',
        password='teja@266'
    )
    cursor = conn.cursor()

    cursor.execute("CREATE DATABASE IF NOT EXISTS healthcare_appointment")
    cursor.execute("USE healthcare_appointment")


    # ── patients ──────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            patient_id   INT AUTO_INCREMENT PRIMARY KEY,
            name         VARCHAR(100) NOT NULL,
            age          INT NOT NULL,
            gender       VARCHAR(10)  NOT NULL,
            phone_number VARCHAR(15)  NOT NULL,
            email        VARCHAR(100) NOT NULL UNIQUE,
            password     VARCHAR(255),
            address      TEXT,
            profile_pic  VARCHAR(255) DEFAULT NULL,
            auth_provider VARCHAR(20) DEFAULT 'local',
            google_id    VARCHAR(100) DEFAULT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── doctors ───────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            doctor_id       INT AUTO_INCREMENT PRIMARY KEY,
            name            VARCHAR(100) NOT NULL,
            specialization  VARCHAR(100) NOT NULL,
            experience      INT DEFAULT 0,
            phone_number    VARCHAR(15)  NOT NULL,
            email           VARCHAR(100) NOT NULL UNIQUE,
            password        VARCHAR(255),
            available_slots TEXT DEFAULT NULL,
            bio             TEXT,
            profile_pic     VARCHAR(255) DEFAULT NULL,
            auth_provider   VARCHAR(20)  DEFAULT 'local',
            google_id       VARCHAR(100) DEFAULT NULL,
            rating          DECIMAL(3,1) DEFAULT 4.5,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── appointments ──────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            appointment_id       INT AUTO_INCREMENT PRIMARY KEY,
            patient_id           INT NOT NULL,
            doctor_id            INT NOT NULL,
            appointment_date     DATE NOT NULL,
            appointment_time     VARCHAR(20) NOT NULL,
            status               VARCHAR(20) DEFAULT 'Pending',
            cancellation_reason  TEXT,
            notes                TEXT,
            created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE,
            FOREIGN KEY (doctor_id)  REFERENCES doctors(doctor_id)   ON DELETE CASCADE
        )
    """)

    # ── prescriptions ─────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prescriptions (
            prescription_id INT AUTO_INCREMENT PRIMARY KEY,
            appointment_id  INT NOT NULL,
            doctor_id       INT NOT NULL,
            patient_id      INT NOT NULL,
            medicines       TEXT,
            notes           TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id) ON DELETE CASCADE,
            FOREIGN KEY (doctor_id)      REFERENCES doctors(doctor_id)           ON DELETE CASCADE,
            FOREIGN KEY (patient_id)     REFERENCES patients(patient_id)         ON DELETE CASCADE
        )
    """)

    # ── admin ─────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            admin_id   INT AUTO_INCREMENT PRIMARY KEY,
            username   VARCHAR(50)  NOT NULL UNIQUE,
            password   VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── password_reset_tokens ─────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            email      VARCHAR(100) NOT NULL,
            user_type  VARCHAR(20)  NOT NULL,
            token      VARCHAR(255) NOT NULL UNIQUE,
            expires_at DATETIME NOT NULL,
            used       TINYINT(1) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── contact_messages ─────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contact_messages (
            message_id INT AUTO_INCREMENT PRIMARY KEY,
            full_name VARCHAR(100) NOT NULL,
            email VARCHAR(100) NOT NULL,
            subject VARCHAR(200),
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── default admin ─────────────────────────────────────
    cursor.execute("SELECT * FROM admin WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO admin (username, password) VALUES (%s, %s)",
            ('admin', generate_password_hash('admin123'))
        )

    # ── sample doctors ────────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM doctors")
    if cursor.fetchone()[0] == 0:
        dp = generate_password_hash('doctor123')
        sample = [
            ('Rajesh Kumar',  'Cardiology',      12, '9876543210', 'rajesh.kumar@hospital.com',  '09:00 AM - 01:00 PM, 02:00 PM - 05:00 PM', 4.8),
            ('Priya Sharma',  'Dermatology',      8, '9876543211', 'priya.sharma@hospital.com',  '10:00 AM - 02:00 PM, 03:00 PM - 06:00 PM', 4.7),
            ('Amit Patel',    'Orthopedics',     15, '9876543212', 'amit.patel@hospital.com',    '08:00 AM - 12:00 PM, 01:00 PM - 04:00 PM', 4.6),
            ('Sunita Reddy',  'Neurology',       10, '9876543213', 'sunita.reddy@hospital.com',  '09:00 AM - 01:00 PM, 03:00 PM - 06:00 PM', 4.9),
            ('Vikram Singh',  'Pediatrics',       7, '9876543214', 'vikram.singh@hospital.com',  '08:00 AM - 12:00 PM, 02:00 PM - 05:00 PM', 4.5),
            ('Meera Iyer',    'Gynecology',       9, '9876543215', 'meera.iyer@hospital.com',    '10:00 AM - 01:00 PM, 02:00 PM - 05:00 PM', 4.8),
            ('Anil Deshmukh', 'ENT',              6, '9876543216', 'anil.deshmukh@hospital.com', '09:00 AM - 12:00 PM, 01:00 PM - 04:00 PM', 4.4),
            ('Kavita Nair',   'Ophthalmology',   11, '9876543217', 'kavita.nair@hospital.com',   '10:00 AM - 02:00 PM, 03:00 PM - 06:00 PM', 4.7),
            ('Suresh Gupta',  'General Medicine', 14, '9876543218', 'suresh.gupta@hospital.com', '08:00 AM - 01:00 PM, 02:00 PM - 06:00 PM', 4.6),
            ('Deepa Joshi',   'Psychiatry',       5, '9876543219', 'deepa.joshi@hospital.com',   '11:00 AM - 03:00 PM, 04:00 PM - 07:00 PM', 4.9),
            ('Rahul Verma',   'Dentistry',        8, '9876543220', 'rahul.verma@hospital.com',   '09:00 AM - 01:00 PM, 02:00 PM - 06:00 PM', 4.5),
            ('Anjali Mehta',  'Cardiology',      13, '9876543221', 'anjali.mehta@hospital.com',  '10:00 AM - 02:00 PM, 03:00 PM - 05:00 PM', 4.8),
        ]
        for d in sample:
            cursor.execute(
                "INSERT INTO doctors (name,specialization,experience,phone_number,email,password,available_slots,rating) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (d[0], d[1], d[2], d[3], d[4], dp, d[5], d[6])
            )

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Database initialized successfully!")
    print("   Admin login  → username: admin   | password: admin123")
    print("   Doctor login → any sample email  | password: doctor123")

if __name__ == '__main__':
    init_db()