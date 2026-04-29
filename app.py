import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

# 1. LOAD KONFIGURASI
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'MECHAEL_SUPER_SECRET')

# 2. FUNGSI KONEKSI DATABASE (POSTGRESQL)
def get_db_connection():
    # Mengambil URL dari Neon.tech yang ada di file .env
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    return conn

# 3. INISIALISASI DATABASE
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # SQL PostgreSQL menggunakan SERIAL untuk ID otomatis
    cur.execute('''CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY, 
        name TEXT NOT NULL, 
        category TEXT NOT NULL, 
        price REAL NOT NULL, 
        stock INTEGER NOT NULL)''')
        
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY, 
        username TEXT UNIQUE NOT NULL, 
        password TEXT NOT NULL, 
        role TEXT NOT NULL DEFAULT 'user')''')
        
    cur.execute('''CREATE TABLE IF NOT EXISTS cart (
        id SERIAL PRIMARY KEY, 
        user_id INTEGER NOT NULL, 
        product_id INTEGER NOT NULL, 
        quantity INTEGER NOT NULL)''')
    
    # Buat Admin Default jika belum ada
    cur.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cur.fetchone():
        cur.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)", 
                    ('admin', 'admin123', 'admin'))
    
    conn.commit()
    cur.close()
    conn.close()

# Jalankan init_db satu kali saat app menyala
init_db()

# --- ROUTES FRONTEND ---

@app.route('/')
def index():
    conn = get_db_connection()
    # RealDictCursor digunakan agar hasil query bisa diakses seperti dictionary (p['name'])
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM products WHERE stock > 0')
    products = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('index.html', products=products)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)', (username, password, 'user'))
            conn.commit()
            return redirect(url_for('login'))
        except:
            return render_template('register.html', error="Username sudah dipakai!")
        finally:
            cur.close()
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user:
            session.update({'logged_in': True, 'user_id': user['id'], 'username': user['username'], 'role': user['role']})
            return redirect(url_for('index'))
        return render_template('login.html', error="Username/Password salah!")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- FITUR KERANJANG & CHECKOUT ---

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    user_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute('SELECT * FROM cart WHERE user_id = %s AND product_id = %s', (user_id, product_id))
    item = cur.fetchone()
    
    if item:
        cur.execute('UPDATE cart SET quantity = quantity + 1 WHERE id = %s', (item['id'],))
    else:
        cur.execute('INSERT INTO cart (user_id, product_id, quantity) VALUES (%s, %s, 1)', (user_id, product_id))
    
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('cart'))

@app.route('/cart')
def cart():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('''
        SELECT cart.id as cart_id, products.name, products.price, cart.quantity, products.id as product_id
        FROM cart JOIN products ON cart.product_id = products.id
        WHERE cart.user_id = %s
    ''', (session['user_id'],))
    items = cur.fetchall()
    total = sum([item['price'] * item['quantity'] for item in items])
    cur.close()
    conn.close()
    return render_template('cart.html', items=items, total=total)

@app.route('/checkout', methods=['POST'])
def checkout():
    if not session.get('logged_in'): return redirect(url_for('login'))
    user_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute('SELECT * FROM cart WHERE user_id = %s', (user_id,))
    items = cur.fetchall()
    if not items: return redirect(url_for('cart'))
    
    for item in items:
        cur.execute('UPDATE products SET stock = stock - %s WHERE id = %s', (item['quantity'], item['product_id']))
        
    cur.execute('DELETE FROM cart WHERE user_id = %s', (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    return render_template('cart.html', success=True)

# --- RUTE ADMIN ---

@app.route('/admin')
def admin():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    return render_template('admin.html')

@app.route('/api/products', methods=['GET', 'POST'])
def manage_products():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if request.method == 'GET':
        cur.execute('SELECT * FROM products ORDER BY id DESC')
        products = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(products)
    
    if session.get('role') == 'admin':
        data = request.json
        cur.execute('INSERT INTO products (name, category, price, stock) VALUES (%s, %s, %s, %s)', 
                    (data['name'], data['category'], data['price'], data['stock']))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"msg": "Berhasil"}), 201
    return jsonify({"msg": "Unauthorized"}), 401

@app.route('/api/products/<int:id>', methods=['DELETE'])
def delete_product(id):
    if session.get('role') == 'admin':
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM products WHERE id = %s', (id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"msg": "Dihapus"})
    return jsonify({"msg": "Unauthorized"}), 401

if __name__ == '__main__':
    app.run(debug=True)