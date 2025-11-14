from flask import Flask, render_template, request, redirect, url_for, session, g
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'dev_secret_key_change_me'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'doxa.db')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur.lastrowid

# --- Routes ---
@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = query_db('SELECT * FROM users WHERE username = ? AND password = ?', (username, password), one=True)
        if user:
            session['user_id'] = user['id']
            session['nombre'] = user['name']
            session['user_rol'] = user['role']
            return redirect(url_for('dashboard'))
        else:
            error = 'Credenciales inválidas'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    casos = query_db('SELECT c.*, p.name as perito_nombre FROM casos c LEFT JOIN peritos p ON c.perito_id = p.id')
    return render_template('dashboard.html', casos=casos)

@app.route('/add_siniestro', methods=['GET', 'POST'])
def add_siniestro():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    peritos = query_db('SELECT * FROM peritos')
    error = None
    if request.method == 'POST':
        compania = request.form['compania']
        codigo_unico = request.form['codigo_unico']
        descripcion = request.form['descripcion']
        perito_id = request.form['perito_id']
        perito = query_db('SELECT * FROM peritos WHERE id = ?', (perito_id,), one=True)
        execute_db('INSERT INTO casos (codigo_unico, compania_aseguradora, descripcion, perito_id, estado) VALUES (?, ?, ?, ?, ?)',
                   (codigo_unico, compania, descripcion, perito_id, 'Pendiente'))
        return redirect(url_for('dashboard'))
    return render_template('add_siniestro.html', peritos=peritos, error=error)

@app.route('/detalle_siniestro/<int:id>', methods=['GET', 'POST'])
def detalle_siniestro(id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    siniestro = query_db('SELECT c.*, p.name as perito_nombre, p.username as perito_username, p.id as perito_id FROM casos c LEFT JOIN peritos p ON c.perito_id = p.id WHERE c.id = ?', (id,), one=True)
    gastos = query_db('SELECT * FROM gastos WHERE caso_id = ?', (id,))
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_gasto' and session.get('user_rol') == 'Perito':
            desc = request.form['descripcion_gasto']
            monto = float(request.form['monto_guaranies'])
            ticket = request.form.get('ticket_ruta', '')
            execute_db('INSERT INTO gastos (caso_id, descripcion_gasto, monto_guaranies, ticket_ruta) VALUES (?, ?, ?, ?)',
                       (id, desc, monto, ticket))
            return redirect(url_for('detalle_siniestro', id=id))
        if action == 'update_pago' and session.get('user_rol') == 'Creador':
            gasto_id = request.form['gasto_id']
            fecha_pago = request.form.get('fecha_pago') or None
            execute_db('UPDATE gastos SET fecha_pago_reembolso = ? WHERE id = ?', (fecha_pago, gasto_id))
            return redirect(url_for('detalle_siniestro', id=id))
    moneda = 'Gs'
    return render_template('detalle_siniestro.html', siniestro=siniestro, gastos=gastos, moneda=moneda)

@app.route('/sumatorias_reporte')
def sumatorias_reporte():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    compania = request.args.get('compania')
    perito_id = request.args.get('perito_id')
    moneda = 'Gs'
    deuda_compania = 0
    deuda_perito = 0
    peritos_list = query_db('SELECT * FROM peritos')
    if compania:
        # Sum gastos pendientes for company
        deuda_compania = query_db(
            "SELECT SUM(g.monto_guaranies) as total FROM gastos g JOIN casos c ON g.caso_id = c.id WHERE c.compania_aseguradora = ? AND (g.fecha_pago_reembolso IS NULL OR g.fecha_pago_reembolso = '')",
            (compania,), one=True)['total'] or 0
    if perito_id:
        deuda_perito = query_db(
            "SELECT SUM(g.monto_guaranies) as total FROM gastos g JOIN casos c ON g.caso_id = c.id WHERE c.perito_id = ? AND (g.fecha_pago_reembolso IS NULL OR g.fecha_pago_reembolso = '')",
            (perito_id,), one=True)['total'] or 0
    return render_template('reporte_sumatorias.html', compania=compania, deuda_compania=deuda_compania,
                           perito_id=perito_id, deuda_perito=deuda_perito, peritos_list=peritos_list, moneda=moneda)

@app.route('/iniciar_investigacion/<int:id>', methods=['POST'])
def iniciar_investigacion(id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    execute_db('UPDATE casos SET estado = ? WHERE id = ?', ('Investigación', id))
    return redirect(url_for('dashboard'))

@app.route('/terminar_investigacion/<int:id>', methods=['POST'])
def terminar_investigacion(id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    execute_db('UPDATE casos SET estado = ? WHERE id = ?', ('Revisión', id))
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)