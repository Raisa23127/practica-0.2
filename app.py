import os
import uuid
import json
from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd

from models import db, User, Upload
from excel_parser import parse_addresses
from word_generator import generate_word

app = Flask(__name__)
app.secret_key = 'super_secret_key_change_in_production'

# База данных
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему'

# Папки
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['EXPORT_FOLDER'] = 'exports'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Неверный логин или пароль')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not username or not password:
            flash('Заполните все поля')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Пароли не совпадают')
            return redirect(url_for('register'))
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Пользователь с таким именем уже существует')
            return redirect(url_for('register'))
        
        new_user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='operator'  # По умолчанию обычный пользователь
        )
        db.session.add(new_user)
        db.session.commit()
        
        flash('Регистрация прошла успешно! Теперь вы можете войти.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/uploads', methods=['GET', 'POST'])
@login_required
def uploads_page():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Файл не выбран')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('Имя файла пустое')
            return redirect(request.url)
        
        if file:
            filename = str(uuid.uuid4()) + '_' + file.filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            addresses = parse_addresses(filepath)
            
            new_upload = Upload(filename=filename, filepath=filepath, user_id=current_user.id)
            db.session.add(new_upload)
            db.session.commit()
            
            flash(f'Файл загружен! Найдено адресов: {len(addresses)}')
            return redirect(url_for('view_addresses', upload_id=new_upload.id))
        else:
            flash('Ошибка при загрузке файла')
            return redirect(request.url)
    
    # --- ВАЖНОЕ ИЗМЕНЕНИЕ: ФИЛЬТРАЦИЯ ЗАГРУЗОК ---
    if current_user.role == 'admin':
        # Админ видит ВСЕ загрузки
        all_uploads = Upload.query.order_by(Upload.uploaded_at.desc()).all()
    else:
        # Обычный пользователь видит ТОЛЬКО СВОИ загрузки
        all_uploads = Upload.query.filter_by(user_id=current_user.id).order_by(Upload.uploaded_at.desc()).all()
    
    return render_template('uploads.html', uploads=all_uploads)

@app.route('/uploads/<int:upload_id>')
@login_required
def view_addresses(upload_id):
    upload = Upload.query.get(upload_id)
    if not upload:
        flash('Загрузка не найдена')
        return redirect(url_for('uploads_page'))
    
    # --- ПРОВЕРКА ПРАВ НА ПРОСМОТР ---
    if current_user.role != 'admin' and upload.user_id != current_user.id:
        flash('У вас нет прав на просмотр этого файла')
        return redirect(url_for('uploads_page'))
    
    addresses = parse_addresses(upload.filepath)
    return render_template('addresses.html', addresses=addresses, upload=upload)

@app.route('/uploads/delete/<int:upload_id>')
@login_required
def delete_upload_route(upload_id):
    upload = Upload.query.get(upload_id)
    if not upload:
        flash('Загрузка не найдена')
        return redirect(url_for('uploads_page'))
    
    # --- ПРОВЕРКА ПРАВ НА УДАЛЕНИЕ ---
    if current_user.role != 'admin' and upload.user_id != current_user.id:
        flash('У вас нет прав на удаление этого файла')
        return redirect(url_for('uploads_page'))
    
    if os.path.exists(upload.filepath):
        os.remove(upload.filepath)
    db.session.delete(upload)
    db.session.commit()
    flash('Загрузка удалена')
    return redirect(url_for('uploads_page'))

@app.route('/download/<int:upload_id>')
@login_required
def download_word(upload_id):
    upload = Upload.query.get(upload_id)
    if not upload:
        flash('Загрузка не найдена')
        return redirect(url_for('uploads_page'))
    
    # --- ПРОВЕРКА ПРАВ НА СКАЧИВАНИЕ ---
    if current_user.role != 'admin' and upload.user_id != current_user.id:
        flash('У вас нет прав на скачивание этого файла')
        return redirect(url_for('uploads_page'))
    
    addresses = parse_addresses(upload.filepath)
    filename = f'addresses_{upload_id}.docx'
    filepath = generate_word(addresses, filename)
    return send_file(filepath, as_attachment=True)

@app.route('/export/<int:upload_id>')
@login_required
def export_excel(upload_id):
    upload = Upload.query.get(upload_id)
    if not upload:
        flash('Загрузка не найдена')
        return redirect(url_for('uploads_page'))
    
    # --- ПРОВЕРКА ПРАВ НА ЭКСПОРТ ---
    if current_user.role != 'admin' and upload.user_id != current_user.id:
        flash('У вас нет прав на экспорт этого файла')
        return redirect(url_for('uploads_page'))
    
    addresses = parse_addresses(upload.filepath)
    df = pd.DataFrame(addresses, columns=['Адрес'])
    export_path = os.path.join(app.config['EXPORT_FOLDER'], f'export_{upload_id}.xlsx')
    df.to_excel(export_path, index=False)
    return send_file(export_path, as_attachment=True)

@app.route('/stats')
@login_required
def stats_page():
    # --- АДМИН ВИДИТ ОБЩУЮ СТАТИСТИКУ ---
    if current_user.role == 'admin':
        total_uploads = Upload.query.count()
        all_uploads = Upload.query.all()
    else:
        # Обычный пользователь видит только свою статистику
        total_uploads = Upload.query.filter_by(user_id=current_user.id).count()
        all_uploads = Upload.query.filter_by(user_id=current_user.id).all()
    
    total_addresses = 0
    user_stats = {}
    file_names = []
    file_address_counts = []
    
    for upload in all_uploads:
        addresses = parse_addresses(upload.filepath)
        count = len(addresses)
        total_addresses += count
        short_name = upload.filename[:15] + ('...' if len(upload.filename) > 15 else '')
        file_names.append(short_name)
        file_address_counts.append(count)
        
        username = upload.user.username
        user_stats[username] = user_stats.get(username, 0) + 1

    file_names_json = json.dumps(file_names)
    file_counts_json = json.dumps(file_address_counts)

    return render_template('stats.html', 
                           total_uploads=total_uploads,
                           total_addresses=total_addresses,
                           user_stats=user_stats,
                           file_names_json=file_names_json,
                           file_counts_json=file_counts_json)

if __name__ == '__main__':
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    if not os.path.exists('exports'):
        os.makedirs('exports')
    
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            db.session.add(User(
                username='admin', 
                password_hash=generate_password_hash('admin123'), 
                role='admin'
            ))
            db.session.add(User(
                username='operator', 
                password_hash=generate_password_hash('op123'), 
                role='operator'
            ))
            db.session.commit()
    
    app.run(debug=True)
