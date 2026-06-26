from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, date, timedelta
import secrets
import os
from authlib.integrations.flask_client import OAuth
from flask_mail import Mail, Message # Added for email feature

from dotenv import load_dotenv
load_dotenv()

# 🔴 1. ADD THE IMPORT HERE:
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')
# 🔴 2. ADD THE PROXY FIX HERE:
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# ─────────────────────────────────────────────────────────────────
# DB helper
# ─────────────────────────────────────────────────────────────────
def get_db():
    return mysql.connector.connect(
        host='gateway01.ap-southeast-1.prod.aws.tidbcloud.com',
        port=4000,
        user='5MLJE6RAQwcNfyu.root',
        password=os.environ.get('DB_PASSWORD'), # 🔴 Replace this with your generated TiDB password
        database='healthcare_appointment',
        ssl_ca='isrgrootx1.pem'
    )

# ─────────────────────────────────────────────────────────────────
# Auth decorators
# ─────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'patient_id' not in session:
            # 🔴 TELL IT TO REMEMBER THE QR CODE LINK:
            session['next_url'] = request.url
            flash('Please login or register to continue.', 'info')
            return redirect(url_for('patient_login'))
        return f(*args, **kwargs)
    return decorated

def doctor_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'doctor_id' not in session:
            flash('Please login to access this page.', 'error')
            return redirect(url_for('doctor_login'))
        return f(*args, **kwargs)
    return decorated

def admin_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please login to access this page.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────────────────────────────
# HOME
# ─────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        full_name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()

        if not all([full_name, email, message]):
            flash('Please fill out all required fields.', 'error')
            return redirect(url_for('contact'))

        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO contact_messages (full_name, email, subject, message) VALUES (%s, %s, %s, %s)",
                (full_name, email, subject, message)
            )
            conn.commit()
            flash('Thank you! Your message has been received. We will get back to you soon.', 'success')
        except Exception as e:
            flash(f'An error occurred while sending your message: {e}', 'error')
        finally:
            if 'cursor' in locals(): cursor.close()
            if 'conn' in locals(): conn.close()
            
        return redirect(url_for('contact'))
        
    return render_template('contact.html')

# ─────────────────────────────────────────────────────────────────
# GOOGLE OAUTH
# ─────────────────────────────────────────────────────────────────
@app.route('/login/google/<role>')
def google_login(role):
    if role not in ['patient', 'doctor']:
        flash('Invalid role for Google Login.', 'error')
        return redirect(url_for('home'))
    session['oauth_role'] = role
    return google.authorize_redirect(url_for('google_auth', _external=True))

@app.route('/login/google/auth')
def google_auth():
    from authlib.integrations.base_client.errors import OAuthError
    try:
        token = google.authorize_access_token()
    except OAuthError as e:
        flash(f'Authentication failed: {e.error}', 'error')
        return redirect(url_for('home'))

    user_info = token.get('userinfo')
    if not user_info:
        user_info = google.get('https://openidconnect.googleapis.com/v1/userinfo').json()
    
    email = user_info['email'].lower()
    name = user_info.get('name', 'Google User')
    google_id = user_info['sub']
    role = session.get('oauth_role', 'patient')
    
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    table = 'patients' if role == 'patient' else 'doctors'
    id_col = 'patient_id' if role == 'patient' else 'doctor_id'
    
    cursor.execute(f"SELECT * FROM {table} WHERE email=%s", (email,))
    user = cursor.fetchone()
    cursor.close(); conn.close()
    
    if user:
        session[id_col] = user[id_col]
        session[f'{role}_name'] = user['name']
        flash(f"Logged in successfully via Google as {name}!", "success")
        return redirect(url_for(f"{role}_dashboard"))
    else:
        session['google_pending'] = {
            'email': email,
            'name': name,
            'google_id': google_id,
            'role': role
        }
        return redirect(url_for('complete_google_profile', role=role))

@app.route('/complete-google-profile/<role>', methods=['GET', 'POST'])
def complete_google_profile(role):
    if role not in ['patient', 'doctor'] or 'google_pending' not in session:
        flash('Invalid session. Please try logging in again.', 'error')
        return redirect(url_for('home'))
    
    pending = session.get('google_pending')
    
    if request.method == 'POST':
        email = pending['email']
        name = pending['name']
        google_id = pending['google_id']
        
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        table = 'patients' if role == 'patient' else 'doctors'
        id_col = 'patient_id' if role == 'patient' else 'doctor_id'
        
        try:
            if role == 'patient':
                age = request.form.get('age', '').strip()
                gender = request.form.get('gender', '').strip()
                phone = request.form.get('phone', '').strip()
                
                if not age or int(age) <= 0:
                    flash('Age must be a valid number greater than 0.', 'error')
                    return render_template('complete_google_profile.html', role=role, pending=pending)
                if not gender:
                    flash('Please select a gender.', 'error')
                    return render_template('complete_google_profile.html', role=role, pending=pending)
                if not phone or len(phone) < 10:
                    flash('Phone number must be at least 10 digits.', 'error')
                    return render_template('complete_google_profile.html', role=role, pending=pending)
                
                cursor.execute(
                    f"INSERT INTO {table} (name, age, gender, phone_number, email, password, auth_provider, google_id) VALUES (%s, %s, %s, %s, %s, NULL, 'google', %s)",
                    (name, int(age), gender, phone, email, google_id)
                )
            else:
                specialization = request.form.get('specialization', '').strip()
                phone = request.form.get('phone', '').strip()
                available_slots = request.form.get('available_slots', '').strip()
                
                if not specialization:
                    flash('Specialization is required.', 'error')
                    return render_template('complete_google_profile.html', role=role, pending=pending)
                if not phone or len(phone) < 10:
                    flash('Phone number must be at least 10 digits.', 'error')
                    return render_template('complete_google_profile.html', role=role, pending=pending)
                
                cursor.execute(
                    f"INSERT INTO {table} (name, specialization, phone_number, email, password, auth_provider, google_id, available_slots) VALUES (%s, %s, %s, %s, NULL, 'google', %s, %s)",
                    (name, specialization, phone, email, google_id, available_slots)
                )
            conn.commit()
            
            cursor.execute(f"SELECT * FROM {table} WHERE email=%s", (email,))
            user = cursor.fetchone()
            cursor.close(); conn.close()
            
            session[id_col] = user[id_col]
            session[f'{role}_name'] = user['name']
            session.pop('google_pending', None)
            flash(f"Account created successfully! Welcome, {name}!", "success")
            return redirect(url_for(f"{role}_dashboard"))
        except Exception as e:
            cursor.close(); conn.close()
            flash(f'Error creating account: {e}', 'error')
            return render_template('complete_google_profile.html', role=role, pending=pending)
    
    return render_template('complete_google_profile.html', role=role, pending=pending)

# ─────────────────────────────────────────────────────────────────
# PATIENT — AUTH
# ─────────────────────────────────────────────────────────────────
@app.route('/patient/register', methods=['GET', 'POST'])
def patient_register():
    if request.method == 'POST':
        name     = request.form['name'].strip()
        age      = request.form['age']
        gender   = request.form['gender']
        phone    = request.form['phone'].strip()
        email    = request.form['email'].strip().lower()
        password = request.form['password']
        confirm  = request.form['confirm_password']
        address  = request.form.get('address', '').strip()

        if not all([name, age, gender, phone, email, password]):
            flash('All required fields must be filled.', 'error')
            return redirect(url_for('patient_register'))
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('patient_register'))
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('patient_register'))
        if len(phone) < 10:
            flash('Enter a valid phone number.', 'error')
            return redirect(url_for('patient_register'))

        try:
            conn = get_db(); cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT patient_id FROM patients WHERE email=%s", (email,))
            if cursor.fetchone():
                flash('This email is already registered.', 'error')
                return redirect(url_for('patient_register'))
            cursor.execute(
                "INSERT INTO patients (name,age,gender,phone_number,email,password,address) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (name, age, gender, phone, email, generate_password_hash(password), address)
            )
            conn.commit()
            flash('Account created! Please login.', 'success')
            return redirect(url_for('patient_login'))
        except Exception as e:
            flash(f'Registration failed: {e}', 'error')
        finally:
            cursor.close(); conn.close()
    return render_template('patient_register.html')


@app.route('/patient/login', methods=['GET', 'POST'])
def patient_login():
    if request.method == 'POST':
        email    = request.form['email'].strip().lower()
        password = request.form['password']
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM patients WHERE email=%s", (email,))
        patient = cursor.fetchone()
        cursor.close(); conn.close()
        if patient and patient.get('password') and check_password_hash(patient['password'], password):
            session['patient_id']   = patient['patient_id']
            session['patient_name'] = patient['name']
            flash(f'Welcome back, {patient["name"]}!', 'success')
            return redirect(url_for('patient_dashboard'))
        flash('Invalid email or password.', 'error')
    return render_template('patient_login.html')


@app.route('/patient/logout')
def patient_logout():
    session.pop('patient_id', None)
    session.pop('patient_name', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home'))

# Forgot / Reset password (patient)
@app.route('/patient/forgot-password', methods=['GET', 'POST'])
def patient_forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT patient_id FROM patients WHERE email=%s", (email,))
        user = cursor.fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            expires = datetime.now() + timedelta(hours=1)
            cursor.execute(
                "INSERT INTO password_reset_tokens (email, user_type, token, expires_at) VALUES (%s,'patient',%s,%s)",
                (email, token, expires)
            )
            conn.commit()
            reset_link = url_for('patient_reset_password', token=token, _external=True)
            flash(f'Password reset link (dev only): {reset_link}', 'success')
        else:
            flash('If that email exists, a reset link has been sent.', 'success')
        cursor.close(); conn.close()
        return redirect(url_for('patient_login'))
    return render_template('forgot_password.html', role='patient')


@app.route('/patient/reset-password/<token>', methods=['GET', 'POST'])
def patient_reset_password(token):
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM password_reset_tokens WHERE token=%s AND user_type='patient' AND used=0 AND expires_at > %s",
        (token, datetime.now())
    )
    record = cursor.fetchone()
    if not record:
        flash('Invalid or expired reset link.', 'error')
        cursor.close(); conn.close()
        return redirect(url_for('patient_login'))
    if request.method == 'POST':
        pw = request.form['password']
        if len(pw) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('reset_password.html', token=token, role='patient')
        cursor.execute("UPDATE patients SET password=%s WHERE email=%s",
                       (generate_password_hash(pw), record['email']))
        cursor.execute("UPDATE password_reset_tokens SET used=1 WHERE token=%s", (token,))
        conn.commit()
        flash('Password updated! Please login.', 'success')
        cursor.close(); conn.close()
        return redirect(url_for('patient_login'))
    cursor.close(); conn.close()
    return render_template('reset_password.html', token=token, role='patient')

# ─────────────────────────────────────────────────────────────────
# PATIENT — DASHBOARD & PROFILE
# ─────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────
# PATIENT — DASHBOARD & PROFILE
# ─────────────────────────────────────────────────────────────────
@app.route('/patient/dashboard')
@login_required
def patient_dashboard():
    # 🔴 SMART INTERCEPTOR 🔴
    if 'next_url' in session:
        target_url = session.pop('next_url')
        return redirect(target_url)

    conn = get_db(); cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM patients WHERE patient_id=%s", (session['patient_id'],))
    patient = cursor.fetchone()
    
    cursor.execute("""
        SELECT a.*, d.name AS doctor_name, d.specialization, d.phone_number AS doctor_phone
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.doctor_id
        WHERE a.patient_id = %s
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, (session['patient_id'],))
    appointments = cursor.fetchall()
    
    cursor.close(); conn.close()
    
    return render_template('patient_dashboard.html', patient=patient, appointments=appointments)

@app.route('/patient/profile', methods=['GET', 'POST'])
@login_required
def patient_profile():
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        name    = request.form['name'].strip()
        age     = request.form['age']
        gender  = request.form['gender']
        phone   = request.form['phone'].strip()
        address = request.form.get('address', '').strip()
        cursor.execute(
            "UPDATE patients SET name=%s, age=%s, gender=%s, phone_number=%s, address=%s WHERE patient_id=%s",
            (name, age, gender, phone, address, session['patient_id'])
        )
        conn.commit()
        session['patient_name'] = name
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('patient_profile'))
    cursor.execute("SELECT * FROM patients WHERE patient_id=%s", (session['patient_id'],))
    patient = cursor.fetchone()
    cursor.close(); conn.close()
    return render_template('patient_profile.html', patient=patient)

# ─────────────────────────────────────────────────────────────────
# PATIENT — APPOINTMENTS
# ─────────────────────────────────────────────────────────────────
@app.route('/book_appointment', methods=['GET', 'POST'])
@login_required
def book_appointment():
    conn = get_db(); cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        doctor_id = request.form['doctor_id']
        apt_date  = request.form['appointment_date']
        apt_time  = request.form['appointment_time']

        if datetime.strptime(apt_date, '%Y-%m-%d').date() < date.today():
            flash('Cannot book for a past date.', 'error')
            return redirect(url_for('book_appointment'))

        cursor.execute(
            "SELECT appointment_id FROM appointments WHERE doctor_id=%s AND appointment_date=%s AND appointment_time=%s AND status!='Cancelled'",
            (doctor_id, apt_date, apt_time)
        )
        if cursor.fetchone():
            flash('That slot is already taken. Please choose another time.', 'error')
            return redirect(url_for('book_appointment'))

        cursor.execute(
            "INSERT INTO appointments (patient_id,doctor_id,appointment_date,appointment_time,status) VALUES (%s,%s,%s,%s,'Pending')",
            (session['patient_id'], doctor_id, apt_date, apt_time)
        )
        conn.commit()
        cursor.close(); conn.close()
        flash('Appointment booked successfully! The doctor will confirm shortly.', 'success')
        return redirect(url_for('patient_dashboard'))

    spec_filter  = request.args.get('specialization', '')
    search_query = request.args.get('search', '').strip()

    query  = "SELECT * FROM doctors WHERE 1=1"
    params = []
    if spec_filter:
        query += " AND specialization LIKE %s"; params.append(f'%{spec_filter}%')
    if search_query:
        query += " AND (name LIKE %s OR specialization LIKE %s)"
        params += [f'%{search_query}%', f'%{search_query}%']
    query += " ORDER BY name"
    cursor.execute(query, params)
    doctors = cursor.fetchall()

    cursor.execute("SELECT DISTINCT specialization FROM doctors ORDER BY specialization")
    specializations = [r['specialization'] for r in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*) AS total FROM doctors")
    total_doctors = cursor.fetchone()['total']
    cursor.close(); conn.close()

    return render_template('book_appointment.html',
                           doctors=doctors, specializations=specializations,
                           filter=spec_filter, search_query=search_query,
                           total_doctors=total_doctors)


@app.route('/appointment/<int:apt_id>/cancel', methods=['GET', 'POST'])
@login_required
def cancel_appointment(apt_id):
    reason = request.form.get('reason', '').strip() if request.method == 'POST' else ''
    conn = get_db(); cursor = conn.cursor()
    cursor.execute(
        "UPDATE appointments SET status='Cancelled', cancellation_reason=%s WHERE appointment_id=%s AND patient_id=%s",
        (reason, apt_id, session['patient_id'])
    )
    conn.commit()
    cursor.close(); conn.close()
    flash('Appointment cancelled.', 'success')
    return redirect(url_for('patient_dashboard'))


@app.route('/appointment/<int:apt_id>/update', methods=['POST'])
@login_required
def update_appointment(apt_id):
    apt_date = request.form['appointment_date']
    apt_time = request.form['appointment_time']

    if datetime.strptime(apt_date, '%Y-%m-%d').date() < date.today():
        flash('Cannot reschedule to a past date.', 'error')
        return redirect(url_for('patient_dashboard'))

    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT doctor_id FROM appointments WHERE appointment_id=%s AND patient_id=%s",
        (apt_id, session['patient_id'])
    )
    apt = cursor.fetchone()
    if not apt:
        flash('Appointment not found.', 'error')
        cursor.close(); conn.close()
        return redirect(url_for('patient_dashboard'))

    cursor.execute(
        "SELECT appointment_id FROM appointments WHERE doctor_id=%s AND appointment_date=%s AND appointment_time=%s AND appointment_id!=%s AND status!='Cancelled'",
        (apt['doctor_id'], apt_date, apt_time, apt_id)
    )
    if cursor.fetchone():
        flash('That slot is already taken.', 'error')
        cursor.close(); conn.close()
        return redirect(url_for('patient_dashboard'))

    cursor.execute(
        "UPDATE appointments SET appointment_date=%s, appointment_time=%s, status='Pending' WHERE appointment_id=%s AND patient_id=%s",
        (apt_date, apt_time, apt_id, session['patient_id'])
    )
    conn.commit()
    cursor.close(); conn.close()
    flash('Appointment rescheduled!', 'success')
    return redirect(url_for('patient_dashboard'))


@app.route('/appointment_history')
@login_required
def appointment_history():
    status_filter = request.args.get('status', '')
    date_filter   = request.args.get('date', '')

    conn = get_db(); cursor = conn.cursor(dictionary=True)
    query = """
        SELECT a.*, d.name AS doctor_name, d.specialization
        FROM appointments a JOIN doctors d ON a.doctor_id=d.doctor_id
        WHERE a.patient_id=%s
    """
    params = [session['patient_id']]
    if status_filter: query += " AND a.status=%s"; params.append(status_filter)
    if date_filter:   query += " AND a.appointment_date=%s"; params.append(date_filter)
    query += " ORDER BY a.appointment_date DESC, a.appointment_time DESC"
    cursor.execute(query, params)
    appointments = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('appointment_history.html',
                           appointments=appointments,
                           status_filter=status_filter,
                           date_filter=date_filter)


@app.route('/appointment/<int:apt_id>/prescription')
@login_required
def view_prescription(apt_id):
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.*, d.name AS doctor_name, d.specialization,
               a.appointment_date, a.appointment_time,
               pat.name AS patient_name
        FROM prescriptions p
        JOIN appointments a ON p.appointment_id=a.appointment_id
        JOIN doctors d      ON p.doctor_id=d.doctor_id
        JOIN patients pat    ON p.patient_id=pat.patient_id
        WHERE p.appointment_id=%s AND p.patient_id=%s
    """, (apt_id, session['patient_id']))
    prescription = cursor.fetchone()
    cursor.close(); conn.close()
    if not prescription:
        flash('No prescription found for this appointment.', 'error')
        return redirect(url_for('appointment_history'))
    return render_template('prescription.html', prescription=prescription)

# ─────────────────────────────────────────────────────────────────
# DOCTOR — AUTH
# ─────────────────────────────────────────────────────────────────
@app.route('/doctor/register', methods=['GET', 'POST'])
def doctor_register():
    if request.method == 'POST':
        name           = request.form['name'].strip()
        specialization = request.form['specialization'].strip()
        phone          = request.form['phone'].strip()
        email          = request.form['email'].strip().lower()
        password       = request.form['password']
        confirm        = request.form['confirm_password']
        slots          = request.form.get('available_slots', '').strip()
        experience     = request.form.get('experience', 0)
        bio            = request.form.get('bio', '').strip()

        if not all([name, specialization, phone, email, password]):
            flash('All required fields must be filled.', 'error')
            return redirect(url_for('doctor_register'))
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('doctor_register'))
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('doctor_register'))

        try:
            conn = get_db(); cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT doctor_id FROM doctors WHERE email=%s", (email,))
            if cursor.fetchone():
                flash('This email is already registered.', 'error')
                return redirect(url_for('doctor_register'))
            cursor.execute(
                "INSERT INTO doctors (name,specialization,experience,phone_number,email,password,available_slots,bio) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (name, specialization, experience, phone, email, generate_password_hash(password), slots, bio)
            )
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('doctor_login'))
        except Exception as e:
            flash(f'Registration failed: {e}', 'error')
        finally:
            cursor.close(); conn.close()
    return render_template('doctor_register.html')


@app.route('/doctor/login', methods=['GET', 'POST'])
def doctor_login():
    if request.method == 'POST':
        email    = request.form['email'].strip().lower()
        password = request.form['password']
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM doctors WHERE email=%s", (email,))
        doctor = cursor.fetchone()
        cursor.close(); conn.close()
        if doctor and doctor.get('password') and check_password_hash(doctor['password'], password):
            session['doctor_id']   = doctor['doctor_id']
            session['doctor_name'] = doctor['name']
            flash(f'Welcome, Dr. {doctor["name"]}!', 'success')
            return redirect(url_for('doctor_dashboard'))
        flash('Invalid email or password.', 'error')
    return render_template('doctor_login.html')


@app.route('/doctor/logout')
def doctor_logout():
    session.pop('doctor_id', None)
    session.pop('doctor_name', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home'))


@app.route('/doctor/forgot-password', methods=['GET', 'POST'])
def doctor_forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT doctor_id FROM doctors WHERE email=%s", (email,))
        user = cursor.fetchone()
        if user:
            token   = secrets.token_urlsafe(32)
            expires = datetime.now() + timedelta(hours=1)
            cursor.execute(
                "INSERT INTO password_reset_tokens (email,user_type,token,expires_at) VALUES (%s,'doctor',%s,%s)",
                (email, token, expires)
            )
            conn.commit()
            reset_link = url_for('doctor_reset_password', token=token, _external=True)
            flash(f'Reset link (dev only): {reset_link}', 'success')
        else:
            flash('If that email exists, a reset link has been sent.', 'success')
        cursor.close(); conn.close()
        return redirect(url_for('doctor_login'))
    return render_template('forgot_password.html', role='doctor')


@app.route('/doctor/reset-password/<token>', methods=['GET', 'POST'])
def doctor_reset_password(token):
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM password_reset_tokens WHERE token=%s AND user_type='doctor' AND used=0 AND expires_at > %s",
        (token, datetime.now())
    )
    record = cursor.fetchone()
    if not record:
        flash('Invalid or expired reset link.', 'error')
        cursor.close(); conn.close()
        return redirect(url_for('doctor_login'))
    if request.method == 'POST':
        pw = request.form['password']
        if len(pw) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('reset_password.html', token=token, role='doctor')
        cursor.execute("UPDATE doctors SET password=%s WHERE email=%s",
                       (generate_password_hash(pw), record['email']))
        cursor.execute("UPDATE password_reset_tokens SET used=1 WHERE token=%s", (token,))
        conn.commit()
        flash('Password updated! Please login.', 'success')
        cursor.close(); conn.close()
        return redirect(url_for('doctor_login'))
    cursor.close(); conn.close()
    return render_template('reset_password.html', token=token, role='doctor')

# ─────────────────────────────────────────────────────────────────
# DOCTOR — DASHBOARD
# ─────────────────────────────────────────────────────────────────
@app.route('/doctor/dashboard')
@doctor_login_required
def doctor_dashboard():
    # 🔴 ADDED INTERCEPTOR HERE 🔴
    if 'next_url' in session:
        target_url = session.pop('next_url')
        return redirect(target_url)

    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM doctors WHERE doctor_id=%s", (session['doctor_id'],))
    doctor = cursor.fetchone()
    cursor.execute("""
        SELECT a.*,
               p.name AS patient_name, p.phone_number AS patient_phone,
               p.age AS patient_age, p.gender AS patient_gender,
               p.email AS patient_email,
               pr.prescription_id
        FROM appointments a
        JOIN patients p ON a.patient_id=p.patient_id
        LEFT JOIN prescriptions pr ON pr.appointment_id=a.appointment_id
        WHERE a.doctor_id=%s
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, (session['doctor_id'],))
    appointments = cursor.fetchall()

    # Quick stats
    total     = len(appointments)
    pending   = sum(1 for a in appointments if a['status'] == 'Pending')
    confirmed = sum(1 for a in appointments if a['status'] == 'Confirmed')
    completed = sum(1 for a in appointments if a['status'] == 'Completed')

    cursor.close(); conn.close()
    return render_template('doctor_dashboard.html',
                           doctor=doctor, appointments=appointments,
                           total=total, pending=pending,
                           confirmed=confirmed, completed=completed)


@app.route('/doctor/update_slots', methods=['POST'])
@doctor_login_required
def update_slots():
    slots = request.form['available_slots']
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE doctors SET available_slots=%s WHERE doctor_id=%s",
                   (slots, session['doctor_id']))
    conn.commit()
    cursor.close(); conn.close()
    flash('Available slots updated!', 'success')
    return redirect(url_for('doctor_dashboard'))




@app.route('/doctor/add_prescription/<int:apt_id>', methods=['GET', 'POST'])
@doctor_login_required
def add_prescription(apt_id):
    conn = get_db(); cursor = conn.cursor(dictionary=True)

    # Verify appointment belongs to this doctor
    cursor.execute(
        "SELECT a.*, p.name AS patient_name FROM appointments a JOIN patients p ON a.patient_id=p.patient_id WHERE a.appointment_id=%s AND a.doctor_id=%s",
        (apt_id, session['doctor_id'])
    )
    apt = cursor.fetchone()
    if not apt:
        flash('Appointment not found.', 'error')
        cursor.close(); conn.close()
        return redirect(url_for('doctor_dashboard'))

    if request.method == 'POST':
        medicines = request.form['medicines'].strip()
        notes     = request.form['notes'].strip()
        # Upsert prescription
        cursor.execute("SELECT prescription_id FROM prescriptions WHERE appointment_id=%s", (apt_id,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                "UPDATE prescriptions SET medicines=%s, notes=%s WHERE appointment_id=%s",
                (medicines, notes, apt_id)
            )
        else:
            cursor.execute(
                "INSERT INTO prescriptions (appointment_id,doctor_id,patient_id,medicines,notes) VALUES (%s,%s,%s,%s,%s)",
                (apt_id, session['doctor_id'], apt['patient_id'], medicines, notes)
            )
        conn.commit()
        flash('Prescription saved!', 'success')
        cursor.close(); conn.close()
        return redirect(url_for('doctor_dashboard'))

    # Pre-load existing prescription if any
    cursor.execute("SELECT * FROM prescriptions WHERE appointment_id=%s", (apt_id,))
    existing_rx = cursor.fetchone()
    cursor.close(); conn.close()
    return render_template('add_prescription.html', apt=apt, existing_rx=existing_rx)


@app.route('/doctor/profile', methods=['GET', 'POST'])
@doctor_login_required
def doctor_profile():
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        name           = request.form['name'].strip()
        specialization = request.form['specialization'].strip()
        phone          = request.form['phone'].strip()
        experience     = request.form.get('experience', 0)
        bio            = request.form.get('bio', '').strip()
        slots          = request.form.get('available_slots', '').strip()
        
        # Validation
        if not specialization:
            flash('Specialization is required.', 'error')
            cursor.execute("SELECT * FROM doctors WHERE doctor_id=%s", (session['doctor_id'],))
            doctor = cursor.fetchone()
            cursor.close(); conn.close()
            return render_template('doctor_profile.html', doctor=doctor)
        
        if not phone or len(phone) < 10:
            flash('Phone number must be at least 10 digits.', 'error')
            cursor.execute("SELECT * FROM doctors WHERE doctor_id=%s", (session['doctor_id'],))
            doctor = cursor.fetchone()
            cursor.close(); conn.close()
            return render_template('doctor_profile.html', doctor=doctor)
        
        if not slots:
            flash('Available time slots are required.', 'error')
            cursor.execute("SELECT * FROM doctors WHERE doctor_id=%s", (session['doctor_id'],))
            doctor = cursor.fetchone()
            cursor.close(); conn.close()
            return render_template('doctor_profile.html', doctor=doctor)
        
        cursor.execute(
            "UPDATE doctors SET name=%s,specialization=%s,phone_number=%s,experience=%s,bio=%s,available_slots=%s WHERE doctor_id=%s",
            (name, specialization, phone, experience, bio, slots, session['doctor_id'])
        )
        conn.commit()
        session['doctor_name'] = name
        flash('Profile updated successfully!', 'success')
        cursor.close(); conn.close()
        return redirect(url_for('doctor_profile'))
    cursor.execute("SELECT * FROM doctors WHERE doctor_id=%s", (session['doctor_id'],))
    doctor = cursor.fetchone()
    cursor.close(); conn.close()
    return render_template('doctor_profile.html', doctor=doctor)

# ─────────────────────────────────────────────────────────────────
# ADMIN — AUTH
# ─────────────────────────────────────────────────────────────────
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admin WHERE username=%s", (username,))
        admin = cursor.fetchone()
        cursor.close(); conn.close()
        if admin and check_password_hash(admin['password'], password):
            session['admin_id']       = admin['admin_id']
            session['admin_username'] = admin['username']
            flash('Welcome to the Admin panel!', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials.', 'error')
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    flash('Logged out.', 'success')
    return redirect(url_for('home'))

# ─────────────────────────────────────────────────────────────────
# ADMIN — DASHBOARD
# ─────────────────────────────────────────────────────────────────
@app.route('/admin/dashboard')
@admin_login_required
def admin_dashboard():
    # 🔴 ADDED INTERCEPTOR HERE 🔴
    if 'next_url' in session:
        target_url = session.pop('next_url')
        return redirect(target_url)

    conn = get_db(); cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS c FROM patients")
    patient_count = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) AS c FROM doctors")
    doctor_count  = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) AS c FROM appointments")
    apt_count     = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) AS c FROM appointments WHERE status='Pending'")
    pending_count = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) AS c FROM appointments WHERE status='Confirmed'")
    confirmed_count = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) AS c FROM appointments WHERE status='Completed'")
    completed_count = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) AS c FROM appointments WHERE status='Cancelled'")
    cancelled_count = cursor.fetchone()['c']

    # Recent appointments
    cursor.execute("""
        SELECT a.*, d.name AS doctor_name, d.specialization, p.name AS patient_name
        FROM appointments a
        JOIN doctors d ON a.doctor_id=d.doctor_id
        JOIN patients p ON a.patient_id=p.patient_id
        ORDER BY a.created_at DESC LIMIT 15
    """)
    recent_appointments = cursor.fetchall()

    # Monthly stats for chart (last 6 months)
    cursor.execute("""
        SELECT DATE_FORMAT(appointment_date, '%Y-%m') AS month, COUNT(*) AS count
        FROM appointments
        WHERE appointment_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
        GROUP BY month ORDER BY month
    """)
    monthly_raw = cursor.fetchall()
    chart_months  = [r['month'] for r in monthly_raw]
    chart_counts  = [r['count'] for r in monthly_raw]

    # Status distribution for donut chart
    status_data = {
        'Pending': pending_count, 'Confirmed': confirmed_count,
        'Completed': completed_count, 'Cancelled': cancelled_count
    }

    # Top doctors by appointment count
    cursor.execute("""
        SELECT d.name, d.specialization, COUNT(a.appointment_id) AS total
        FROM doctors d LEFT JOIN appointments a ON d.doctor_id=a.doctor_id
        GROUP BY d.doctor_id ORDER BY total DESC LIMIT 5
    """)
    top_doctors = cursor.fetchall()

    cursor.execute("SELECT * FROM doctors ORDER BY name")
    doctors = cursor.fetchall()
    cursor.execute("SELECT * FROM patients ORDER BY created_at DESC")
    patients = cursor.fetchall()

    # Get contact messages for the admin
    cursor.execute("SELECT * FROM contact_messages ORDER BY created_at DESC")
    contact_messages = cursor.fetchall()

    cursor.close(); conn.close()
    
    return render_template('admin_dashboard.html',
                           patient_count=patient_count, doctor_count=doctor_count,
                           apt_count=apt_count, pending_count=pending_count,
                           confirmed_count=confirmed_count, completed_count=completed_count,
                           cancelled_count=cancelled_count,
                           recent_appointments=recent_appointments,
                           chart_months=chart_months, chart_counts=chart_counts,
                           status_data=status_data, top_doctors=top_doctors,
                           doctors=doctors, patients=patients,
                           contact_messages=contact_messages)

# ─────────────────────────────────────────────────────────────────
# ADMIN — DOCTOR MANAGEMENT
# ─────────────────────────────────────────────────────────────────
@app.route('/admin/add_doctor', methods=['POST'])
@admin_login_required
def add_doctor():
    name           = request.form['name'].strip()
    specialization = request.form['specialization'].strip()
    phone          = request.form['phone'].strip()
    email          = request.form['email'].strip().lower()
    password       = request.form['password']
    slots          = request.form.get('available_slots', '')
    experience     = request.form.get('experience', 0)

    if not all([name, specialization, phone, email, password]):
        flash('All fields are required.', 'error')
        return redirect(url_for('admin_dashboard'))
    try:
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT doctor_id FROM doctors WHERE email=%s", (email,))
        if cursor.fetchone():
            flash('A doctor with that email already exists.', 'error')
            return redirect(url_for('admin_dashboard'))
        cursor.execute(
            "INSERT INTO doctors (name,specialization,experience,phone_number,email,password,available_slots) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (name, specialization, experience, phone, email, generate_password_hash(password), slots)
        )
        conn.commit()
        flash('Doctor added!', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    finally:
        cursor.close(); conn.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/edit_doctor/<int:doctor_id>', methods=['POST'])
@admin_login_required
def edit_doctor(doctor_id):
    name           = request.form['name'].strip()
    specialization = request.form['specialization'].strip()
    phone          = request.form['phone'].strip()
    email          = request.form['email'].strip().lower()
    slots          = request.form.get('available_slots', '')
    experience     = request.form.get('experience', 0)
    conn = get_db(); cursor = conn.cursor()
    cursor.execute(
        "UPDATE doctors SET name=%s,specialization=%s,experience=%s,phone_number=%s,email=%s,available_slots=%s WHERE doctor_id=%s",
        (name, specialization, experience, phone, email, slots, doctor_id)
    )
    conn.commit()
    cursor.close(); conn.close()
    flash('Doctor updated!', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete_doctor/<int:doctor_id>')
@admin_login_required
def delete_doctor(doctor_id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM doctors WHERE doctor_id=%s", (doctor_id,))
    conn.commit()
    cursor.close(); conn.close()
    flash('Doctor deleted.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete_patient/<int:patient_id>')
@admin_login_required
def delete_patient(patient_id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM patients WHERE patient_id=%s", (patient_id,))
    conn.commit()
    cursor.close(); conn.close()
    flash('Patient record deleted.', 'success')
    return redirect(url_for('admin_dashboard'))


# ─────────────────────────────────────────────────────────────────
# ADMIN — ANALYTICS API (JSON for Chart.js)
# ─────────────────────────────────────────────────────────────────
@app.route('/admin/api/appointments_per_day')
@admin_login_required
def api_appointments_per_day():
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT appointment_date AS day, COUNT(*) AS count
        FROM appointments
        WHERE appointment_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        GROUP BY day ORDER BY day
    """)
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return jsonify({'labels': [str(r['day']) for r in rows], 'data': [r['count'] for r in rows]})


@app.route('/admin/api/specialization_stats')
@admin_login_required
def api_specialization_stats():
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT d.specialization, COUNT(a.appointment_id) AS count
        FROM doctors d LEFT JOIN appointments a ON d.doctor_id=a.doctor_id
        GROUP BY d.specialization ORDER BY count DESC LIMIT 8
    """)
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return jsonify({'labels': [r['specialization'] for r in rows], 'data': [r['count'] for r in rows]})

# ─────────────────────────────────────────────────────────────────
# PUBLIC — DOCTOR LISTING
# ─────────────────────────────────────────────────────────────────
@app.route('/doctors')
def doctors_list():
    spec_filter  = request.args.get('specialization', '')
    search_query = request.args.get('search', '').strip()

    conn = get_db(); cursor = conn.cursor(dictionary=True)
    query = "SELECT * FROM doctors WHERE 1=1"
    params = []
    if spec_filter:
        query += " AND specialization LIKE %s"; params.append(f'%{spec_filter}%')
    if search_query:
        query += " AND (name LIKE %s OR specialization LIKE %s)"
        params += [f'%{search_query}%', f'%{search_query}%']
    query += " ORDER BY name"
    cursor.execute(query, params)
    doctors = cursor.fetchall()

    cursor.execute("SELECT DISTINCT specialization FROM doctors ORDER BY specialization")
    specializations = [r['specialization'] for r in cursor.fetchall()]
    cursor.close(); conn.close()
    return render_template('doctors_list.html',
                           doctors=doctors, specializations=specializations,
                           filter=spec_filter, search_query=search_query)
# ─────────────────────────────────────────────────────────────────
# CALENDAR VIEW
# ─────────────────────────────────────────────────────────────────
@app.route('/calendar')
def calendar_view():
    # Allow if ANY of the three roles are logged in
    if not any(k in session for k in ['patient_id', 'doctor_id', 'admin_id']):
        flash('Please login to view the calendar.', 'error')
        return redirect(url_for('home'))
    return render_template('calendar.html')

@app.route('/api/calendar/appointments')
def api_calendar_appointments():
    if not any(k in session for k in ['patient_id', 'doctor_id', 'admin_id']):
        return jsonify([])

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    events = []
    
    try:
        if 'admin_id' in session:
            # ADMIN: Sees ALL appointments globally
            cursor.execute("""
                SELECT a.appointment_id, a.appointment_date, a.appointment_time, 
                       CONCAT(p.name, ' w/ Dr. ', d.name) AS other_party, a.status 
                FROM appointments a 
                JOIN patients p ON a.patient_id = p.patient_id 
                JOIN doctors d ON a.doctor_id = d.doctor_id
                WHERE a.status != 'Cancelled'
            """)
        elif 'doctor_id' in session:
            # DOCTOR: Sees only their patients
            cursor.execute("""
                SELECT a.appointment_id, a.appointment_date, a.appointment_time, p.name AS other_party, a.status 
                FROM appointments a JOIN patients p ON a.patient_id = p.patient_id 
                WHERE a.doctor_id = %s AND a.status != 'Cancelled'
            """, (session['doctor_id'],))
        else:
            # PATIENT: Sees only their doctors
            cursor.execute("""
                SELECT a.appointment_id, a.appointment_date, a.appointment_time, CONCAT('Dr. ', d.name) AS other_party, a.status 
                FROM appointments a JOIN doctors d ON a.doctor_id = d.doctor_id 
                WHERE a.patient_id = %s AND a.status != 'Cancelled'
            """, (session['patient_id'],))
            
        appointments = cursor.fetchall()
        
        # Color coding for the calendar blocks
        colors = {'Pending': '#f59e0b', 'Confirmed': '#10b981', 'Completed': '#06b6d4'}
        
        for apt in appointments:
            date_str = str(apt['appointment_date'])
            time_str = apt['appointment_time']
            
            try:
                # Extract starting time if it's a range (e.g., "09:00 AM - 10:00 AM")
                clean_time = time_str.split(' - ')[0].strip() if ' - ' in time_str else time_str.strip()
                dt = datetime.strptime(f"{date_str} {clean_time}", "%Y-%m-%d %I:%M %p")
                
                # Format for FullCalendar ISO requirement
                start_iso = dt.isoformat()
                end_iso = (dt + timedelta(hours=1)).isoformat() # Assumes 1 hour block
            except Exception as e:
                # Fallback if time parsing fails
                start_iso = date_str
                end_iso = date_str

            events.append({
                'id': apt['appointment_id'],
                'title': f"{apt['status']} - {apt['other_party']}",
                'start': start_iso,
                'end': end_iso,
                'backgroundColor': colors.get(apt['status'], '#7c5ff8'),
                'borderColor': colors.get(apt['status'], '#7c5ff8'),
                'textColor': '#ffffff'
            })
    except Exception as e:
        print(f"Calendar Error: {e}")
    finally:
        cursor.close()
        conn.close()

    return jsonify(events)



# ─────────────────────────────────────────────────────────────────
# 2. THE QR TICKET SCANNER ROUTE
# ─────────────────────────────────────────────────────────────────

@app.route('/verify/<int:apt_id>')
def verify_appointment(apt_id):
    # Interceptor: If no one is logged in, save this URL and send to home
    if not any(k in session for k in ['patient_id', 'doctor_id', 'admin_id']):
        session['next_url'] = url_for('verify_appointment', apt_id=apt_id)
        flash('Please login to view this digital ticket.', 'info')
        return redirect(url_for('home'))

    # Fetch full appointment details
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT a.*, p.name AS patient_name, p.phone_number AS patient_phone, 
               p.age AS patient_age, p.gender AS patient_gender,
               d.name AS doctor_name, d.specialization
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        JOIN doctors d ON a.doctor_id = d.doctor_id
        WHERE a.appointment_id = %s
    """, (apt_id,))
    appointment = cursor.fetchone()
    cursor.close(); conn.close()
    
    if not appointment:
        flash('Invalid or expired appointment ticket.', 'error')
        return redirect(url_for('home'))
        
    # Strict Security Ownership Checks
    if 'patient_id' in session and appointment['patient_id'] != session['patient_id']:
        flash('Access Denied: You can only view your own medical tickets.', 'error')
        return redirect(url_for('patient_dashboard'))
        
    if 'doctor_id' in session and appointment['doctor_id'] != session['doctor_id']:
        flash('Access Denied: You can only verify appointments assigned to you.', 'error')
        return redirect(url_for('doctor_dashboard'))
        
    return render_template('verify_appointment.html', apt=appointment)


# ─────────────────────────────────────────────────────────────────
# 3. THE QR STATUS UPDATE ROUTE
# ─────────────────────────────────────────────────────────────────

# app.py

@app.route('/appointment/<int:apt_id>/update_status/<string:status>', methods=['GET', 'POST'])
def update_appointment_status(apt_id, status):
    # 1. STRICT BACKEND RBAC: Reject Patients immediately
    if 'doctor_id' not in session and 'admin_id' not in session:
        flash('Security Alert: You do not have permission to modify appointments.', 'error')
        return redirect(url_for('home'))

    valid_statuses = ['Confirmed', 'Completed', 'Cancelled']
    if status not in valid_statuses:
        flash('Invalid status update requested.', 'error')
        return redirect(request.referrer or url_for('home'))

    # 2. Handle Cancellation Reason
    cancellation_reason = None
    if status == 'Cancelled' and request.method == 'POST':
        cancellation_reason = request.form.get('cancellation_reason', 'No reason provided')

    conn = get_db()
    cursor = conn.cursor()
    try:
        if status == 'Cancelled':
            cursor.execute("""
                UPDATE appointments 
                SET status = %s, cancellation_reason = %s 
                WHERE appointment_id = %s
            """, (status, cancellation_reason, apt_id))
        else:
            cursor.execute("""
                UPDATE appointments 
                SET status = %s 
                WHERE appointment_id = %s
            """, (status, apt_id))
        
        conn.commit()
        flash(f'Appointment #{apt_id} marked as {status}.', 'success')
    except Exception as e:
        flash('Database error occurred.', 'error')
    finally:
        cursor.close()
        conn.close()

    # Redirect back to whoever made the change
    if 'admin_id' in session:
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('doctor_dashboard'))

# ─────────────────────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)