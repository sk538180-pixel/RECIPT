from flask import Flask, render_template, request, redirect, url_for, render_template_string, session
from supabase import create_client, Client
import qrcode
import base64
from io import BytesIO
import json
from datetime import datetime

app = Flask(__name__)
# Session security ke liye
app.secret_key = 'aakash_super_secret_key'

# Supabase Setup (Tumhara original)
SUPABASE_URL = "https://qtzmgxvjibivdgodcfwz.supabase.co"
SUPABASE_KEY = "sb_publishable_mLPBhmg1wc15tJOzbRd6Qg_nu30nfMC"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= LOGIN LOGIC =================
@app.route('/')
def index():
    # Agar login nahi hai, toh "No internet" wala page dikhao
    if not session.get('logged_in'):
        return render_template('offline.html')
    
    # Login hai toh dashboard dikhao
    response = supabase.table('receipts').select('id, url_path').order('id', desc=True).execute()
    pages = [(row['id'], row['url_path']) for row in response.data]
    return render_template('index.html', pages=pages)

@app.route('/login', methods=['POST'])
def login():
    # Tumhara naya secret password
    if request.form.get('password') == "4035":
        session['logged_in'] = True
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))
# ===============================================

@app.route('/create', methods=['POST'])
def create():
    if not session.get('logged_in'): return redirect(url_for('index'))

    url_path = request.form['custom_url'].strip().replace(" ", "")
    if url_path.startswith('/'):
        url_path = url_path[1:]

    # Date Format ko theek karna
    raw_date = request.form.get('date', '').strip()
    formatted_date = ""
    if raw_date:
        formatted_date = datetime.strptime(raw_date, '%Y-%m-%d').strftime('%d-%m-%Y')

    data = {
        'custom_url': url_path,
        'District': request.form.get('district', '').strip(),
        'Anchal': request.form.get('anchal', '').strip(),
        'Halka': request.form.get('halka', '').strip(),
        'Mauja': request.form.get('mauja', '').strip(),
        'Name': request.form.get('name', '').strip(),
        'Name2': request.form.get('name2', '').strip(),
        'Pata': request.form.get('pata', '').strip(),
        'Thana': request.form.get('thana', '').strip(),
        'Khata': request.form.get('khata', '').strip(),
        'Khesra': request.form.get('khesra', '').strip(),
        'Date': formatted_date,
        'Raw_Date': raw_date
    }

    final_html = render_template('receipt_template.html', **data)

    # QR CODE LOGIC (Dense aur bada)
    full_receipt_link = request.host_url + url_path
    qr_maker = qrcode.QRCode(version=8, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
    qr_maker.add_data(full_receipt_link)
    qr_maker.make(fit=True)
    img = qr_maker.make_image(fill_color="black", back_color="white")
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    qr_base64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
    qr_img_tag = f'<img src="data:image/png;base64,{qr_base64}" width="130" height="130">'
    final_html = final_html.replace('Qr', qr_img_tag)

    # Form ka data json format me store karna (taaki edit ho sake)
    form_data_json = json.dumps(data)

    try:
        supabase.table('receipts').insert({
            'url_path': url_path, 
            'html_content': final_html,
            'form_data': form_data_json
        }).execute()
    except Exception as e:
        return "Ye Link pehle se kisi aur ne bana liya hai, kripya back ja kar dusra link daalein."

    return redirect(url_for('index'))

@app.route('/edit_data/<int:id>')
def edit_data(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    
    response = supabase.table('receipts').select('id, form_data').eq('id', id).execute()
    
    if response.data and response.data[0].get('form_data'):
        form_data = json.loads(response.data[0]['form_data'])
        return render_template('edit_data.html', id=id, data=form_data)
    return "Is raseed ka form data save nahi hai (Nayi raseed banayein).", 404

@app.route('/update_data/<int:id>', methods=['POST'])
def update_data(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    
    url_path = request.form['custom_url'].strip().replace(" ", "")
    if url_path.startswith('/'): url_path = url_path[1:]

    raw_date = request.form.get('date', '').strip()
    formatted_date = datetime.strptime(raw_date, '%Y-%m-%d').strftime('%d-%m-%Y')

    data = {
        'custom_url': url_path,
        'District': request.form.get('district', '').strip(),
        'Anchal': request.form.get('anchal', '').strip(),
        'Halka': request.form.get('halka', '').strip(),
        'Mauja': request.form.get('mauja', '').strip(),
        'Name': request.form.get('name', '').strip(),
        'Name2': request.form.get('name2', '').strip(),
        'Pata': request.form.get('pata', '').strip(),
        'Thana': request.form.get('thana', '').strip(),
        'Khata': request.form.get('khata', '').strip(),
        'Khesra': request.form.get('khesra', '').strip(),
        'Date': formatted_date,
        'Raw_Date': raw_date
    }

    final_html = render_template('receipt_template.html', **data)

    full_receipt_link = request.host_url + url_path
    qr_maker = qrcode.QRCode(version=8, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
    qr_maker.add_data(full_receipt_link)
    qr_maker.make(fit=True)
    img = qr_maker.make_image(fill_color="black", back_color="white")
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    qr_base64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
    qr_img_tag = f'<img src="data:image/png;base64,{qr_base64}" width="130" height="130">'
    final_html = final_html.replace('Qr', qr_img_tag)

    form_data_json = json.dumps(data)

    supabase.table('receipts').update({
        'url_path': url_path, 
        'html_content': final_html,
        'form_data': form_data_json
    }).eq('id', id).execute()
    
    return redirect(url_for('index'))

@app.route('/edit/<int:id>')
def edit(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    
    response = supabase.table('receipts').select('id, url_path, html_content').eq('id', id).execute()

    if response.data:
        row = response.data[0]
        page = (row['id'], row['url_path'], row['html_content'])
        return render_template('edit.html', page=page)
    return "Page nahi mila!", 404

@app.route('/update/<int:id>', methods=['POST'])
def update(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    
    new_html = request.form['html_content']
    supabase.table('receipts').update({'html_content': new_html}).eq('id', id).execute()
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
def delete(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    
    supabase.table('receipts').delete().eq('id', id).execute()
    return redirect(url_for('index'))

# Yahan public view hai, isliye koi password check nahi lagega
@app.route('/<path:url_path>')
def view_page(url_path):
    response = supabase.table('receipts').select('html_content').eq('url_path', url_path).execute()

    if response.data:
        return render_template_string(response.data[0]['html_content'])
    else:
        return "Receipt Not Found!", 404

if __name__ == '__main__':
    app.run()
