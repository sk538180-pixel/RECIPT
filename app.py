from flask import Flask, render_template, request, redirect, url_for, render_template_string, session
from supabase import create_client, Client
import qrcode
import base64
from io import BytesIO
import json
from datetime import datetime
import re

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
    response = supabase.table('receipts').select('id, url_path, html_content').order('id', desc=True).execute()
    
    pages = []
    for row in response.data:
        html = row.get('html_content', '')
        display_name = "Naam Nahi Mila"
        
        # Extract name using Regex
        match = re.search(r'जमाबंदी रेयत का नाम :- <b>(.*?)</b>\s*<br>अभिभावक का नाम', html, re.DOTALL | re.IGNORECASE)
        if match and match.group(1).strip():
            display_name = match.group(1).strip()
            
        pages.append((row['id'], row['url_path'], display_name))
        
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

@app.route('/create_from_html', methods=['POST'])
def create_from_html():
    if not session.get('logged_in'): return redirect(url_for('index'))

    url_path = request.form['custom_url'].strip().replace(" ", "")
    if url_path.startswith('/'):
        url_path = url_path[1:]
        
    html_content = request.form['html_content']
    
    # Extract optional names to override in HTML
    jamabandi_name = request.form.get('jamabandi_name', '').strip()
    guardian_name = request.form.get('guardian_name', '').strip()
    halka_name = request.form.get('halka_name', '').strip()
    mauja_name = request.form.get('mauja_name', '').strip()
    mauja_thana_name = request.form.get('mauja_thana_name', '').strip()
    
    if jamabandi_name:
        pattern1 = re.compile(r'(जमाबंदी रेयत का नाम :- <b>)(.*?)(</b>\s*<br>अभिभावक का नाम :- <b>)', re.DOTALL | re.IGNORECASE)
        html_content = pattern1.sub(rf'\g<1>{jamabandi_name}\g<3>', html_content)
        
    if guardian_name:
        pattern2 = re.compile(r'(अभिभावक का नाम :- <b>)(.*?)(</b>\s*</td>\s*<td width="35%">पता)', re.DOTALL | re.IGNORECASE)
        html_content = pattern2.sub(rf'\g<1>{guardian_name}\g<3>', html_content)

    if halka_name:
        pattern3 = re.compile(r'(<td width="36%">हल्का :- <b>)(.*?)(</b>\s*</td>\s*<td width="35%">मौजा)', re.DOTALL | re.IGNORECASE)
        html_content = pattern3.sub(rf'\g<1>{halka_name}\g<3>', html_content)

    if mauja_name:
        pattern4 = re.compile(r'(<td width="35%">मौजा :- <b>)(.*?)(</b>\s*</td>\s*</tr>\s*<tr align="left">)', re.DOTALL | re.IGNORECASE)
        html_content = pattern4.sub(rf'\g<1>{mauja_name}\g<3>', html_content)

    if mauja_thana_name:
        pattern5 = re.compile(r'(<td width="35%">मौजा/थाना संख्या :- <b>)(.*?)(</b>\s*</td>\s*</tr>\s*<tr align="left">)', re.DOTALL | re.IGNORECASE)
        html_content = pattern5.sub(rf'\g<1>{mauja_thana_name}\g<3>', html_content)

    # User's logo replacement requirement
    html_content = html_content.replace('src="../img/logo2_new1.png"', 'src="/static/download.png"')

    # Generate new QR code for the custom URL
    full_receipt_link = request.host_url + url_path
    qr_maker = qrcode.QRCode(version=8, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
    qr_maker.add_data(full_receipt_link)
    qr_maker.make(fit=True)
    img = qr_maker.make_image(fill_color="black", back_color="white")
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    qr_base64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
    
    # Replace the existing base64 image in the provided HTML with the new one
    # This regex looks for src="data:image/...;base64,..." and replaces it with the new QR code
    new_qr_src = f'src="data:image/png;base64,{qr_base64}"'
    # We replace only the first occurrence assuming there's only one QR code at the end
    final_html = re.sub(r'src="data:image/[^;]+;base64,[^"]+"', new_qr_src, html_content, count=1)

    # empty JSON since there's no form data for HTML input
    form_data_json = json.dumps({}) 

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
