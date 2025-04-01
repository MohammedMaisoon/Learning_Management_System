from flask import Flask, flash, jsonify, render_template, request, redirect, session, url_for
from flask_mysqldb import MySQL
import MySQLdb.cursors
import re
from werkzeug.security import generate_password_hash, check_password_hash
import os
import cv2
from werkzeug.utils import secure_filename
import random
import string
from datetime import datetime, timedelta
from flask_mail import Mail, Message
import zipfile
from flask import send_file

app = Flask(__name__)
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'lms_db'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'  
app.config['MAIL_PASSWORD'] = 'your-password' 
mail = Mail(app)

otps = {}
app.secret_key = os.urandom(24)


mysql = MySQL(app)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'mp4', 'pdf', 'pptx'}
os.chmod(UPLOAD_FOLDER, 0o755)
def generate_thumbnail(video_path, output_path):
    try:
        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        if ret:
            cv2.imwrite(output_path, frame)
        cap.release()
    except Exception as e:
        print(f"Error generating thumbnail: {e}")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    try:
        return render_template('login.html')
    except Exception as e:
        print(f"Error: {e}")
        return "An error occurred", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        msg = ''
        if request.method == 'POST':
            email = request.form['email']
            password = request.form['password']
            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
            user = cursor.fetchone()
            
            if user and check_password_hash(user['password'], password):
                session['loggedin'] = True
                session['id'] = user['id']
                session['email'] = user['email']
                return redirect(url_for('dashboard'))
            else:
                msg = 'Incorrect email/password!'
        return render_template('login.html', msg=msg)
    except Exception as e:
        print(f"Error: {e}")
        return "An error occurred", 500

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    msg = ''
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        account = cursor.fetchone()
        
        if account:
            msg = 'Account already exists!'
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            msg = 'Invalid email address!'
        else:
            hashed_password = generate_password_hash(password)
            cursor.execute('INSERT INTO users VALUES (NULL, %s, %s, %s)', (username, email, hashed_password,))
            mysql.connection.commit()
            msg = 'Registration successful!'
            return redirect(url_for('login'))
    return render_template('signup.html', msg=msg)

@app.route('/dashboard')
def dashboard():
    if 'loggedin' in session:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM courses')
        courses = cursor.fetchall()
        return render_template('dashboard.html', courses=courses)
    return redirect(url_for('login'))

@app.route('/upload_course', methods=['GET', 'POST'])
def upload_course():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        file = request.files['course_file']
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            thumbnails_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnails')
            if not os.path.exists(thumbnails_dir):
                os.makedirs(thumbnails_dir)
            
            if filename.lower().endswith('.mp4'):
                thumbnail_path = os.path.join(thumbnails_dir, filename.replace('.mp4', '.jpg'))
                generate_thumbnail(file_path, thumbnail_path)
            
            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            cursor.execute('INSERT INTO courses (title, description, filename, user_id, created_at) VALUES (%s, %s, %s, %s, NOW())', 
                         (title, description, filename, session['id']))
            mysql.connection.commit()
            return redirect(url_for('dashboard'))
            
    return render_template('upload_course.html')



@app.route('/search', methods=['GET'])
def search():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    query = request.args.get('query', '')
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM courses WHERE title LIKE %s OR description LIKE %s', 
                  (f'%{query}%', f'%{query}%'))
    courses = cursor.fetchall()
    return render_template('dashboard.html', courses=courses)

@app.route('/remove_course/<int:course_id>')
def remove_course(course_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    # Check if user owns the course
    cursor.execute('SELECT filename FROM courses WHERE id = %s AND user_id = %s', (course_id, session['id']))
    course = cursor.fetchone()
    
    if course:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], course['filename'])
        if os.path.exists(file_path):
            os.remove(file_path)
            
        cursor.execute('DELETE FROM courses WHERE id = %s', (course_id,))
        mysql.connection.commit()
    
    return redirect(url_for('my_uploads'))

@app.route('/my_uploads')
def my_uploads():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM courses WHERE user_id = %s', (session['id'],))
    courses = cursor.fetchall()
    return render_template('my_uploads.html', courses=courses)
@app.route('/library')
def library():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM playlists WHERE user_id = %s', (session['id'],))
    playlists = cursor.fetchall()
    
    cursor.execute('''
        SELECT c.* FROM courses c
        JOIN watch_history w ON c.id = w.course_id
        WHERE w.user_id = %s
        ORDER BY w.watched_at DESC
    ''', (session['id'],))
    history = cursor.fetchall()
    
    return render_template('library.html', playlists=playlists, history=history)

@app.route('/create_playlist', methods=['POST'])
def create_playlist():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    playlist_name = request.form['playlist_name']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('INSERT INTO playlists (name, user_id) VALUES (%s, %s)', 
                  (playlist_name, session['id']))
    mysql.connection.commit()
    return redirect(url_for('library'))

@app.route('/add_to_playlist/<int:course_id>', methods=['POST'])
def add_to_playlist(course_id):
    if 'loggedin' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    playlist_id = request.json.get('playlist_id')
    
    if not playlist_id:
        return jsonify({'success': False, 'error': 'No playlist selected'}), 400
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    try:
        cursor.execute('SELECT * FROM playlist_items WHERE playlist_id = %s AND course_id = %s', 
                      (playlist_id, course_id))
        existing = cursor.fetchone()
        
        if not existing:
            cursor.execute('INSERT INTO playlist_items (playlist_id, course_id) VALUES (%s, %s)',
                          (playlist_id, course_id))
            mysql.connection.commit()
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Course already in playlist'})
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500  

@app.route('/playlist/<int:playlist_id>')
def view_playlist(playlist_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    # Get playlist details
    cursor.execute('SELECT * FROM playlists WHERE id = %s AND user_id = %s',
                  (playlist_id, session['id']))
    playlist = cursor.fetchone()
    
    if playlist:
        # Get courses in playlist
        cursor.execute('''
            SELECT c.* FROM courses c
            JOIN playlist_items pi ON c.id = pi.course_id
            WHERE pi.playlist_id = %s
        ''', (playlist_id,))
        courses = cursor.fetchall()
        return render_template('playlist.html', playlist=playlist, courses=courses)
    return redirect(url_for('library'))

@app.route('/watch_course/<int:course_id>')
def watch_course(course_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        SELECT c.*, u.username, u.id as uploader_id 
        FROM courses c 
        JOIN users u ON c.user_id = u.id 
        WHERE c.id = %s
    ''', (course_id,))
    course = cursor.fetchone()
    
    if course:
        cursor.execute('''
            INSERT INTO watch_history (user_id, course_id, watched_at)
            VALUES (%s, %s, NOW())
            ON DUPLICATE KEY UPDATE watched_at = NOW()
        ''', (session['id'], course_id))

        cursor.execute('SELECT * FROM user_links WHERE user_id = %s AND linked_user_id = %s',
                      (session['id'], course['uploader_id']))
        is_linked = cursor.fetchone() is not None
        
        cursor.execute('SELECT * FROM playlists WHERE user_id = %s', (session['id'],))
        playlists = cursor.fetchall()
        
        mysql.connection.commit()
        return render_template('watch_course.html', course=course, playlists=playlists, is_linked=is_linked)
    return redirect(url_for('dashboard'))

@app.route('/link/<int:uploader_id>')
def link_user(uploader_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM user_links WHERE user_id = %s AND linked_user_id = %s', 
                  (session['id'], uploader_id))
    existing_link = cursor.fetchone()
    
    if not existing_link:
        cursor.execute('INSERT INTO user_links (user_id, linked_user_id, linked_at) VALUES (%s, %s, NOW())',
                      (session['id'], uploader_id))
        mysql.connection.commit()
    
    return redirect(request.referrer)

@app.route('/unlink/<int:uploader_id>')
def unlink_user(uploader_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('DELETE FROM user_links WHERE user_id = %s AND linked_user_id = %s',
                  (session['id'], uploader_id))
    mysql.connection.commit()
    
    return redirect(request.referrer)

@app.route('/linkers')
def linkers():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        SELECT 
            u.id,
            u.username,
            u.created_at,
            (SELECT COUNT(*) FROM user_links WHERE linked_user_id = u.id) as total_linkers,
            (SELECT COUNT(*) FROM courses WHERE user_id = u.id) as total_courses
        FROM users u
        JOIN user_links ul ON u.id = ul.linked_user_id
        WHERE ul.user_id = %s
        ORDER BY ul.linked_at DESC
    ''', (session['id'],))
    linked_users = cursor.fetchall()
    
    return render_template('linkers.html', linked_users=linked_users)


@app.route('/user_profile/<int:user_id>')
def user_profile(user_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        SELECT 
            u.*,
            (SELECT COUNT(*) FROM user_links WHERE linked_user_id = u.id) as total_linkers,
            (SELECT COUNT(*) FROM courses WHERE user_id = u.id) as total_courses
        FROM users u
        WHERE u.id = %s
    ''', (user_id,))
    user = cursor.fetchone()
    
    if user:
        cursor.execute('SELECT * FROM courses WHERE user_id = %s', (user_id,))
        courses = cursor.fetchall()
    
        cursor.execute('SELECT * FROM user_links WHERE user_id = %s AND linked_user_id = %s',
                      (session['id'], user_id))
        is_linked = cursor.fetchone() is not None
        
        return render_template('profile.html', profile_user=user, courses=courses, is_linked=is_linked)
    
    return redirect(url_for('dashboard'))


@app.route('/settings')
def settings():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM users WHERE id = %s', (session['id'],))
    user = cursor.fetchone()
    return render_template('settings.html', user=user)

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    username = request.form['username']
    email = request.form['email']
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('UPDATE users SET username = %s, email = %s WHERE id = %s',
                  (username, email, session['id']))
    mysql.connection.commit()
    
    return redirect(url_for('settings'))
@app.route('/change_password', methods=['POST'])
def change_password():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM users WHERE id = %s', (session['id'],))
    user = cursor.fetchone()
    
    if not check_password_hash(user['password'], current_password):
        flash('Current password is incorrect')
        return redirect(url_for('settings'))
    
    if new_password != confirm_password:
        flash('New passwords do not match')
        return redirect(url_for('settings'))
    
    hashed_password = generate_password_hash(new_password)
    cursor.execute('UPDATE users SET password = %s WHERE id = %s',
                  (hashed_password, session['id']))
    mysql.connection.commit()
    
    flash('Password changed successfully')
    return redirect(url_for('settings'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        
        if user:
            otp = ''.join(random.choices(string.digits, k=6))
            otps[email] = {
                'otp': otp,
                'expiry': datetime.now() + timedelta(minutes=10)
            }
        
            msg = Message('Password Reset OTP',
                        sender='your-email@gmail.com',
                        recipients=[email])
            msg.body = f'Your OTP for password reset is: {otp}'
            mail.send(msg)
            
            return render_template('verify_otp.html', email=email)
        
        flash('Email not found')
        return redirect(url_for('forgot_password'))
    
    return render_template('forgot_password.html')

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    email = request.form['email']
    otp = request.form['otp']
    
    stored_otp = otps.get(email)
    if not stored_otp or stored_otp['otp'] != otp:
        flash('Invalid OTP')
        return redirect(url_for('forgot_password'))
    
    if datetime.now() > stored_otp['expiry']:
        flash('OTP has expired')
        return redirect(url_for('forgot_password'))

    return render_template('reset_password.html', email=email)

@app.route('/reset_password', methods=['POST'])
def reset_password():
    email = request.form['email']
    password = request.form['password']
    confirm_password = request.form['confirm_password']
    
    if password != confirm_password:
        flash('Passwords do not match')
        return render_template('reset_password.html', email=email)
    
    hashed_password = generate_password_hash(password)
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('UPDATE users SET password = %s WHERE email = %s',
                  (hashed_password, email))
    mysql.connection.commit()
    
    if email in otps:
        del otps[email]
    
    flash('Password has been reset successfully')
    return redirect(url_for('login'))


@app.route('/downloads')
def downloads():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM downloads WHERE user_id = %s', (session['id'],))
    downloads = cursor.fetchall()
    
    return render_template('downloads.html', downloads=downloads)

@app.route('/download_course/<int:course_id>')
def download_course(course_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM courses WHERE id = %s', (course_id,))
    course = cursor.fetchone()
    
    if course:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], course['filename'])
        
        downloads_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'downloads', str(session['id']))
        os.makedirs(downloads_folder, exist_ok=True)
        
        download_path = os.path.join(downloads_folder, course['filename'])
        import shutil
        shutil.copy(file_path, download_path)
        
        cursor.execute('INSERT INTO downloads (user_id, course_id, filename, downloaded_at) VALUES (%s, %s, %s, NOW())', 
                      (session['id'], course_id, course['filename']))
        mysql.connection.commit()
        
        return send_file(download_path, as_attachment=True)
    
    return redirect(url_for('dashboard'))
@app.route('/get_playlists')
def get_playlists():
    if 'loggedin' not in session:
        return jsonify([])
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM playlists WHERE user_id = %s', (session['id'],))
    playlists = cursor.fetchall()
    
    return jsonify(playlists)

@app.route('/add_to_specific_playlist/<int:course_id>/<int:playlist_id>', methods=['POST'])
def add_to_specific_playlist(course_id, playlist_id):
    if 'loggedin' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    try:
        cursor.execute('SELECT * FROM playlist_items WHERE playlist_id = %s AND course_id = %s', 
                      (playlist_id, course_id))
        existing = cursor.fetchone()
        
        if not existing:
            cursor.execute('INSERT INTO playlist_items (playlist_id, course_id) VALUES (%s, %s)',
                          (playlist_id, course_id))
            mysql.connection.commit()
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Course already in playlist'})
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'success': False, 'error': str(e)})
@app.route('/watch_downloaded_course/<filename>')
def watch_downloaded_course(filename):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    return render_template('watch_downloaded_course.html', filename=filename)    

@app.route('/delete_download/<filename>')
def delete_download(filename):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('DELETE FROM downloads WHERE user_id = %s AND filename = %s', 
                  (session['id'], filename))
    mysql.connection.commit()

    downloads_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'downloads', str(session['id']))
    file_path = os.path.join(downloads_folder, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    
    return redirect(url_for('downloads'))

  
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)