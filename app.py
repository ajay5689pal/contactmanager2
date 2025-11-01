import os
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize the Flask application
app = Flask(__name__)

# --- Configuration ---
app.config['SECRET_KEY'] = "@VCS72xppdv"

# --- DATABASE CONFIGURATION FOR RENDER FREE TIER ---
# We will use a SQLite database file.
# WARNING: On Render's free tier, this file will be DELETED
# every time the app restarts or goes to sleep. All data will be lost.
db_path = os.path.join('instance', 'database.db')
instance_folder = os.path.dirname(db_path)
if not os.path.exists(instance_folder):
    os.makedirs(instance_folder)

app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Database and Login Manager Initialization ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# --- Database Auto-Creation ---
# This will create the database tables every time the app starts.
# This is necessary for Render's free tier ephemeral filesystem.
with app.app_context():
    db.create_all()
    print("Database tables checked/created.")

# --- Database Models (No changes needed) ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    contacts = db.relationship('Contact', backref='owner', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'email': self.email
        }

# We no longer need the 'init-db' command, so it has been removed.

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- All other routes (login, signup, api, etc.) remain exactly the same ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password. Please try again.', 'danger')
            
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if not username or not password:
            flash('Username and password are required.', 'warning')
            return redirect(url_for('signup'))
            
        existing_user = User.query.filter_by(username=username).first()
        
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'warning')
            return redirect(url_for('signup'))
        
        new_user = User(username=username)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', username=current_user.username)

@app.route('/api/contacts', methods=['GET'])
@login_required
def get_contacts():
    search_term = request.args.get('search', '').lower()
    query = Contact.query.filter_by(user_id=current_user.id)
    
    if search_term:
        query = query.filter(
            db.or_(
                Contact.name.ilike(f'%{search_term}%'),
                Contact.phone.ilike(f'%{search_term}%'),
                Contact.email.ilike(f'%{search_term}%')
            )
        )
    
    contacts = query.order_by(Contact.name).all()
    return jsonify([contact.to_dict() for contact in contacts])

@app.route('/api/contacts/<int:contact_id>', methods=['GET'])
@login_required
def get_contact(contact_id):
    contact = Contact.query.filter_by(id=contact_id, user_id=current_user.id).first()
    if contact:
        return jsonify(contact.to_dict())
    return jsonify({'error': 'Contact not found or access denied'}), 404

@app.route('/api/contacts', methods=['POST'])
@login_required
def add__contact():
    data = request.json
    if not data or not data.get('name'):
        return jsonify({'error': 'Name is a required field.'}), 400
        
    new_contact = Contact(
        name=data.get('name'),
        phone=data.get('phone'),
        email=data.get('email'),
        user_id=current_user.id
    )
    db.session.add(new_contact)
    db.session.commit()
    return jsonify(new_contact.to_dict()), 201

@app.route('/api/contacts/<int:contact_id>', methods=['PUT'])
@login_required
def update_contact(contact_id):
    contact = Contact.query.filter_by(id=contact_id, user_id=current_user.id).first()
    if not contact:
        return jsonify({'error': 'Contact not found or access denied'}), 404
    
    data = request.json
    if not data or not data.get('name'):
        return jsonify({'error': 'Name is a required field.'}), 400
        
    contact.name = data.get('name', contact.name)
    contact.phone = data.get('phone', contact.phone)
    contact.email = data.get('email', contact.email)
    db.session.commit()
    return jsonify(contact.to_dict())

@app.route('/api/contacts/<int:contact_id>', methods=['DELETE'])
@login_required
def delete_contact(contact_id):
    contact = Contact.query.filter_by(id=contact_id, user_id=current_user.id).first()
    if not contact:
        return jsonify({'error': 'Contact not found or access denied'}), 404
        
    db.session.delete(contact)
    db.session.commit()
    return jsonify({'message': 'Contact deleted successfully'})

@app.route('/api/contacts/count', methods=['GET'])
@login_required
def get_contacts_count():
    count = Contact.query.filter_by(user_id=current_user.id).count()
    return jsonify({'count': count})

