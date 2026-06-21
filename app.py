from flask import Flask, render_template, request, redirect, url_for, render_template_string, session
from supabase import create_client, Client
import qrcode
import base64
from io import BytesIO
import os
from functools import wraps
import re
import requests
import uuid
import json
from datetime import datetime
import random
import string
import urllib.request
import urllib.error
import ssl



app = Flask(__name__)
# Session security ke liye
app.secret_key = 'aakash_super_secret_key'

# Supabase Setup (Tumhara original)
SUPABASE_URL = "https://qtzmgxvjibivdgodcfwz.supabase.co"
SUPABASE_KEY = "sb_publishable_mLPBhmg1wc15tJOzbRd6Qg_nu30nfMC"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= LOGIN LOGIC =================
@app.route('/auth/set_session', methods=['POST'])
def auth_set_session():
    data = request.json
    email = data.get('email', '').strip()
    name = data.get('name', '').strip()
    
    if not email: return {"status": "error", "message": "Email required"}, 400
    
    res = supabase.table('users').select('*').eq('email', email).execute()
    if res.data:
        user = res.data[0]
    else:
        if not name: name = email.split('@')[0]
        insert_res = supabase.table('users').insert({'email': email, 'name': name, 'wallet_balance': 0}).execute()
        user = insert_res.data[0]
        
    session['logged_in'] = True
    session['user_id'] = user['id']
    session['email'] = user['email']
    session['is_admin'] = False
    return {"status": "success"}

@app.route('/add_money', methods=['GET', 'POST'])
def add_money():
    if not session.get('logged_in') or session.get('is_admin'):
        return redirect(url_for('index'))
    
    user_id = session.get('user_id')
    email = session.get('email', 'user@example.com')
    
    if request.method == 'POST':
        try:
            amount = int(request.form.get('amount', 0))
            if amount <= 0:
                return render_template('payment.html', error="Invalid amount.")
            
            client_txn_id = str(uuid.uuid4())
            
            # Save Pending Request
            supabase.table('payment_requests').insert({
                'user_id': user_id,
                'amount': amount,
                'utr_number': client_txn_id, 
                'status': 'Pending'
            }).execute()
            
            # Generate static QR
            upi_url = f"upi://pay?pa=lagaaaan@nyes&pn=Aakash&am={amount}&cu=INR"
            qr = qrcode.QRCode(version=1, box_size=10, border=2)
            qr.add_data(upi_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            qr_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            return render_template('payment.html', amount=amount, qr_base64=qr_base64, txn_id=client_txn_id)
                
        except Exception as e:
            return render_template('payment.html', error="Error: " + str(e))
            
    return render_template('payment.html')

@app.route('/api/check_status/<txn_id>')
def api_check_status(txn_id):
    res = supabase.table('payment_requests').select('status').eq('utr_number', txn_id).execute()
    if res.data:
        if res.data[0]['status'] == 'Approved':
            session['payment_msg'] = "Payment completed! Please check your Wallet Balance."
        return {"status": res.data[0]['status']}
    return {"status": "Not Found"}, 404

@app.route('/api/sms_webhook', methods=['POST'])
def api_sms_webhook():
    data = request.json
    if not data or data.get('secret') != "super_admin_secret_123":
        return {"status": "error", "message": "Unauthorized"}, 401
        
    sms_body = data.get('body', '')
    match = re.search(r'(?i)(?:rs\.?|inr|₹)\s*([\d,\.]+)', sms_body)
    if not match:
        return {"status": "ignored", "message": "No amount found"}
        
    amount_str = match.group(1).replace(',', '')
    try:
        amount = float(amount_str)
    except ValueError:
        return {"status": "ignored", "message": "Invalid amount"}
        
    res = supabase.table('payment_requests').select('*').eq('status', 'Pending').eq('amount', int(amount)).order('created_at', desc=False).limit(1).execute()
    if res.data:
        payment = res.data[0]
        user_id = payment['user_id']
        pay_amount = payment['amount']
        
        user_res = supabase.table('users').select('wallet_balance').eq('id', user_id).execute()
        if user_res.data:
            new_balance = (user_res.data[0]['wallet_balance'] or 0) + int(pay_amount)
            supabase.table('users').update({'wallet_balance': new_balance}).eq('id', user_id).execute()
        
        supabase.table('payment_requests').update({'status': 'Approved'}).eq('id', payment['id']).execute()
        return {"status": "success", "message": f"Approved {pay_amount} for user {user_id}"}
        
    return {"status": "ignored", "message": f"No pending request for amount {amount}"}

@app.route('/api/admin_stats', methods=['GET'])
def api_admin_stats():
    secret = request.args.get('secret')
    if secret != "super_admin_secret_123":
        return {"status": "error", "message": "Unauthorized"}, 401
        
    res = supabase.table('payment_requests').select('status, amount').execute()
    if res.data:
        approved = sum(1 for p in res.data if p['status'] == 'Approved')
        pending = sum(1 for p in res.data if p['status'] == 'Pending')
        failed = sum(1 for p in res.data if p['status'] == 'Rejected')
        total_amount = sum(p['amount'] for p in res.data if p['status'] == 'Approved')
        return {
            "approved": approved,
            "pending": pending,
            "failed": failed,
            "total_amount": total_amount
        }
    return { "approved": 0, "pending": 0, "failed": 0, "total_amount": 0 }

@app.route('/')
def index():
    if not session.get('logged_in'):
        return render_template('offline.html')
    
    is_admin = session.get('is_admin', False)
    user_id = session.get('user_id')
    wallet_balance = 0
    email = session.get('email', 'Admin')
    
    # Handle old session states that don't have is_admin or user_id properly set
    if not is_admin and user_id is None:
        session.clear()
        return redirect(url_for('index'))
    
    pending_payments = []
    payment_msg = session.pop('payment_msg', None)
    
    if is_admin:
        response = supabase.table('receipts').select('id, url_path, html_content').is_('user_id', 'null').order('id', desc=True).execute()
        # Admin pending payments fetch
        pay_res = supabase.table('payment_requests').select('*, users(email)').eq('status', 'Pending').order('created_at', desc=True).execute()
        if pay_res.data:
            pending_payments = pay_res.data
    else:
        response = supabase.table('receipts').select('id, url_path, html_content').eq('user_id', user_id).order('id', desc=True).execute()
        user_res = supabase.table('users').select('wallet_balance').eq('id', user_id).execute()
        if user_res.data:
            wallet_balance = user_res.data[0]['wallet_balance']
    
    pages = []
    for row in response.data:
        html = row.get('html_content', '')
        display_name = "Naam Nahi Mila"
        match = re.search(r'जमाबंदी रेयत का नाम :- <b>(.*?)</b>', html, re.DOTALL | re.IGNORECASE)
        if match and match.group(1).strip():
            display_name = match.group(1).strip()
        pages.append((row['id'], row['url_path'], display_name))
        
    return render_template('index.html', pages=pages, is_admin=is_admin, wallet_balance=wallet_balance, email=email, pending_payments=pending_payments, payment_msg=payment_msg)

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('password') == "4035":
        session.clear()
        session['logged_in'] = True
        session['is_admin'] = True
        session['user_id'] = None
        session['email'] = 'Legacy Admin'
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/admin/approve_payment/<int:req_id>', methods=['POST'])
def approve_payment(req_id):
    if not session.get('logged_in') or not session.get('is_admin'): return redirect(url_for('index'))
    
    # Fetch pending request
    pay_res = supabase.table('payment_requests').select('*').eq('id', req_id).execute()
    if not pay_res.data or pay_res.data[0]['status'] != 'Pending':
        return redirect(url_for('index'))
        
    payment = pay_res.data[0]
    user_id = payment['user_id']
    amount = payment['amount']
    
    # Add balance
    user_res = supabase.table('users').select('wallet_balance').eq('id', user_id).execute()
    if user_res.data:
        new_balance = (user_res.data[0]['wallet_balance'] or 0) + amount
        supabase.table('users').update({'wallet_balance': new_balance}).eq('id', user_id).execute()
        
    # Mark as Approved
    supabase.table('payment_requests').update({'status': 'Approved'}).eq('id', req_id).execute()
    session['payment_msg'] = f"Approved ₹{amount} for user."
    return redirect(url_for('index'))

@app.route('/admin/reject_payment/<int:req_id>', methods=['POST'])
def reject_payment(req_id):
    if not session.get('logged_in') or not session.get('is_admin'): return redirect(url_for('index'))
    
    supabase.table('payment_requests').update({'status': 'Rejected'}).eq('id', req_id).execute()
    session['payment_msg'] = "Payment rejected."
    return redirect(url_for('index'))
# ===============================================

@app.route('/create', methods=['POST'])
def create():
    if not session.get('logged_in'): return redirect(url_for('index'))

    url_path = request.form['custom_url'].strip().replace(" ", "")
    if url_path.startswith('/'):
        url_path = url_path[1:]

    user_id = session.get('user_id')
    is_admin = session.get('is_admin')
    
    if not is_admin:
        user_res = supabase.table('users').select('wallet_balance').eq('id', user_id).execute()
        balance = user_res.data[0]['wallet_balance'] if user_res.data else 0
        if balance < 250:
            return "Insufficient Balance in Wallet (₹250 required). Please go back and add money."
        supabase.table('users').update({'wallet_balance': balance - 250}).eq('id', user_id).execute()

    # Check and make url_path unique
    while True:
        response = supabase.table('receipts').select('id').eq('url_path', url_path).execute()
        if not response.data:
            break
        url_path = url_path + ''.join(random.choices(string.ascii_lowercase, k=7))

    # Date Format ko theek karna
    raw_date = request.form.get('date', '').strip()
    formatted_date = ""
    current_year = "2024"
    next_year = "2025"
    start_current_year = "2017"
    start_next_year = "2018"
    if raw_date:
        parsed_date = datetime.strptime(raw_date, '%Y-%m-%d')
        formatted_date = parsed_date.strftime('%d-%m-%Y')
        c_year_int = parsed_date.year
        current_year = str(c_year_int)
        next_year = str(c_year_int + 1)
        
        if c_year_int % 2 == 0:
            s_year_int = c_year_int - 5
        else:
            s_year_int = c_year_int - 4
            
        start_current_year = str(s_year_int)
        start_next_year = str(s_year_int + 1)

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
        'JamabandiNo': request.form.get('jamabandi_no', '').strip(),
        'BhagVartaman': request.form.get('bhag_vartaman', '').strip(),
        'PrishthSankhya': request.form.get('prishth_sankhya', '').strip(),
        'Date': formatted_date,
        'Raw_Date': raw_date,
        'CurrentYear': current_year,
        'NextYear': next_year,
        'StartCurrentYear': start_current_year,
        'StartNextYear': start_next_year
    }

    final_html = render_template('receipt_template.html', **data)

    # QR CODE LOGIC (Version 7, natural browser blur)
    full_receipt_link = request.host_url + url_path
    qr_maker = qrcode.QRCode(version=7, error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=10, border=1)
    qr_maker.add_data(full_receipt_link)
    qr_maker.make(fit=True)
    img = qr_maker.make_image(fill_color="black", back_color="white")
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    qr_base64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
    qr_img_tag = f'<img src="data:image/png;base64,{qr_base64}" width="125" height="125" style="filter: blur(0.15px);">'
    final_html = final_html.replace('Qr', qr_img_tag)

    # Form ka data json format me store karna (taaki edit ho sake)
    form_data_json = json.dumps(data)

    try:
        supabase.table('receipts').insert({
            'url_path': url_path, 
            'html_content': final_html,
            'form_data': form_data_json,
            'user_id': user_id
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

    user_id = session.get('user_id')
    is_admin = session.get('is_admin')
    
    if not is_admin:
        user_res = supabase.table('users').select('wallet_balance').eq('id', user_id).execute()
        balance = user_res.data[0]['wallet_balance'] if user_res.data else 0
        if balance < 250:
            return "Insufficient Balance in Wallet (₹250 required). Please go back and add money."
        supabase.table('users').update({'wallet_balance': balance - 250}).eq('id', user_id).execute()

    # Check and make url_path unique
    while True:
        response = supabase.table('receipts').select('id').eq('url_path', url_path).execute()
        if not response.data:
            break
        url_path = url_path + ''.join(random.choices(string.ascii_lowercase, k=7))
        
    source_url = request.form['source_url'].strip()
    
    try:
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(source_url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=15, context=ctx)
        html_content = response.read().decode('utf-8')
    except Exception as e:
        return f"Link is invalid (Server error ya link galat hai). Error: {str(e)}", 400
    
    # Extract optional names to override in HTML
    jamabandi_name = request.form.get('jamabandi_name', '').strip()
    guardian_name = request.form.get('guardian_name', '').strip()
    halka_name = request.form.get('halka_name', '').strip()
    mauja_name = request.form.get('mauja_name', '').strip()
    mauja_thana_name = request.form.get('mauja_thana_name', '').strip()
    
    if jamabandi_name:
        pattern1 = re.compile(r'(जमाबंदी रेयत का नाम :- <b>)(.*?)(</b>)', re.DOTALL | re.IGNORECASE)
        html_content = pattern1.sub(rf'\g<1>{jamabandi_name}\g<3>', html_content)
        
    if guardian_name:
        pattern2 = re.compile(r'(अभिभावक का नाम :- <b>)(.*?)(</b>)', re.DOTALL | re.IGNORECASE)
        html_content = pattern2.sub(rf'\g<1>{guardian_name}\g<3>', html_content)

    if halka_name:
        pattern3 = re.compile(r'(हल्का :- <b>)(.*?)(</b>)', re.DOTALL | re.IGNORECASE)
        html_content = pattern3.sub(rf'\g<1>{halka_name}\g<3>', html_content)

    if mauja_name:
        pattern4 = re.compile(r'(मौजा :- <b>)(.*?)(</b>)', re.DOTALL | re.IGNORECASE)
        html_content = pattern4.sub(rf'\g<1>{mauja_name}\g<3>', html_content)

    if mauja_thana_name:
        pattern5 = re.compile(r'(मौजा/थाना संख्या :- <b>)(.*?)(</b>)', re.DOTALL | re.IGNORECASE)
        html_content = pattern5.sub(rf'\g<1>{mauja_thana_name}\g<3>', html_content)

    # User's logo replacement requirement
    html_content = html_content.replace('src="../img/logo2_new1.png"', 'src="/static/download.png"')

    # Generate new QR code for the custom URL
    full_receipt_link = request.host_url + url_path
    qr_maker = qrcode.QRCode(version=7, error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=10, border=1)
    qr_maker.add_data(full_receipt_link)
    qr_maker.make(fit=True)
    img = qr_maker.make_image(fill_color="black", back_color="white")
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    qr_base64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
    
    # Replace the existing img tag with a new one
    new_qr_tag = f'<img src="data:image/png;base64,{qr_base64}" width="125" height="125" style="border: none; filter: blur(0.15px);">'
    qr_pattern = re.compile(r'<img[^>]+(?:src="[^"]*barcode\.php[^"]*"|src="data:image/[^;]+;base64,[^"]+"|width="125")[^>]*>', re.IGNORECASE)
    final_html = qr_pattern.sub(new_qr_tag, html_content, count=1)

    # empty JSON since there's no form data for HTML input
    form_data_json = json.dumps({}) 

    try:
        supabase.table('receipts').insert({
            'url_path': url_path, 
            'html_content': final_html,
            'form_data': form_data_json,
            'user_id': user_id
        }).execute()
    except Exception as e:
        return "Ye Link pehle se kisi aur ne bana liya hai, kripya back ja kar dusra link daalein."

    return redirect(url_for('index'))

@app.route('/edit_data/<int:id>')
def edit_data(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    
    query = supabase.table('receipts').select('id, url_path, html_content, form_data').eq('id', id)
    if session.get('is_admin'): query = query.is_('user_id', 'null')
    else: query = query.eq('user_id', session.get('user_id'))
    response = query.execute()
    
    if response.data and response.data[0].get('form_data'):
        form_data = json.loads(response.data[0]['form_data'])
        if not form_data: 
            # Is raseed ko 'Direct HTML' se banaya gaya tha.
            html = response.data[0]['html_content']
            url = response.data[0]['url_path']
            
            # Extract current values via regex
            jamabandi = ""
            guardian = ""
            halka = ""
            mauja = ""
            mauja_thana = ""
            
            m1 = re.search(r'जमाबंदी रेयत का नाम :- <b>(.*?)</b>', html)
            if m1: jamabandi = m1.group(1).strip()
                
            m2 = re.search(r'अभिभावक का नाम :- <b>(.*?)</b>', html)
            if m2: guardian = m2.group(1).strip()
                
            m3 = re.search(r'हल्का :- <b>(.*?)</b>', html)
            if m3: halka = m3.group(1).strip()
                
            m4 = re.search(r'मौजा :- <b>(.*?)</b>', html)
            if m4: mauja = m4.group(1).strip()
                
            m5 = re.search(r'मौजा/थाना संख्या :- <b>(.*?)</b>', html)
            if m5: mauja_thana = m5.group(1).strip()
            
            extracted_data = {
                'custom_url': url,
                'jamabandi_name': jamabandi,
                'guardian_name': guardian,
                'halka_name': halka,
                'mauja_name': mauja,
                'mauja_thana_name': mauja_thana
            }
            return render_template('edit_html_data.html', id=id, data=extracted_data)
        
        return render_template('edit_data.html', id=id, data=form_data)
    return "Is raseed ka form data save nahi hai (Nayi raseed banayein).", 404

@app.route('/update_data/<int:id>', methods=['POST'])
def update_data(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    
    url_path = request.form['custom_url'].strip().replace(" ", "")
    if url_path.startswith('/'): url_path = url_path[1:]

    # Check and make url_path unique (excluding current id)
    while True:
        response = supabase.table('receipts').select('id').eq('url_path', url_path).neq('id', id).execute()
        if not response.data:
            break
        url_path = url_path + ''.join(random.choices(string.ascii_lowercase, k=7))

    raw_date = request.form.get('date', '').strip()
    formatted_date = ""
    current_year = "2024"
    next_year = "2025"
    start_current_year = "2017"
    start_next_year = "2018"
    if raw_date:
        parsed_date = datetime.strptime(raw_date, '%Y-%m-%d')
        formatted_date = parsed_date.strftime('%d-%m-%Y')
        c_year_int = parsed_date.year
        current_year = str(c_year_int)
        next_year = str(c_year_int + 1)
        
        if c_year_int % 2 == 0:
            s_year_int = c_year_int - 5
        else:
            s_year_int = c_year_int - 4
            
        start_current_year = str(s_year_int)
        start_next_year = str(s_year_int + 1)

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
        'JamabandiNo': request.form.get('jamabandi_no', '').strip(),
        'BhagVartaman': request.form.get('bhag_vartaman', '').strip(),
        'PrishthSankhya': request.form.get('prishth_sankhya', '').strip(),
        'Date': formatted_date,
        'Raw_Date': raw_date,
        'CurrentYear': current_year,
        'NextYear': next_year,
        'StartCurrentYear': start_current_year,
        'StartNextYear': start_next_year
    }

    final_html = render_template('receipt_template.html', **data)

    full_receipt_link = request.host_url + url_path
    qr_maker = qrcode.QRCode(version=7, error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=10, border=1)
    qr_maker.add_data(full_receipt_link)
    qr_maker.make(fit=True)
    img = qr_maker.make_image(fill_color="black", back_color="white")
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    qr_base64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
    qr_img_tag = f'<img src="data:image/png;base64,{qr_base64}" width="125" height="125" style="filter: blur(0.15px);">'
    final_html = final_html.replace('Qr', qr_img_tag)

    form_data_json = json.dumps(data)

    try:
        query = supabase.table('receipts').update({
            'url_path': url_path, 
            'html_content': final_html,
            'form_data': form_data_json
        }).eq('id', id)
        if session.get('is_admin'): query = query.is_('user_id', 'null')
        else: query = query.eq('user_id', session.get('user_id'))
        query.execute()
    except Exception as e:
        return "URL pehle se maujud hai, kripya dusra link daalein."
        
    return redirect(url_for('index'))

@app.route('/update_html_data/<int:id>', methods=['POST'])
def update_html_data(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    
    query = supabase.table('receipts').select('html_content', 'url_path').eq('id', id)
    if session.get('is_admin'): query = query.is_('user_id', 'null')
    else: query = query.eq('user_id', session.get('user_id'))
    response = query.execute()
    if not response.data: return "Receipt not found", 404
    
    html_content = response.data[0]['html_content']
    old_url = response.data[0]['url_path']
    
    url_path = request.form['custom_url'].strip().replace(" ", "")
    if url_path.startswith('/'): url_path = url_path[1:]
    
    # Check uniqueness if URL changed
    if url_path != old_url:
        while True:
            r2 = supabase.table('receipts').select('id').eq('url_path', url_path).neq('id', id).execute()
            if not r2.data: break
            url_path = url_path + ''.join(random.choices(string.ascii_lowercase, k=7))
    
    jamabandi_name = request.form.get('jamabandi_name', '').strip()
    guardian_name = request.form.get('guardian_name', '').strip()
    halka_name = request.form.get('halka_name', '').strip()
    mauja_name = request.form.get('mauja_name', '').strip()
    mauja_thana_name = request.form.get('mauja_thana_name', '').strip()
    
    if jamabandi_name:
        pattern1 = re.compile(r'(जमाबंदी रेयत का नाम :- <b>)(.*?)(</b>)', re.DOTALL | re.IGNORECASE)
        html_content = pattern1.sub(rf'\g<1>{jamabandi_name}\g<3>', html_content)
        
    if guardian_name:
        pattern2 = re.compile(r'(अभिभावक का नाम :- <b>)(.*?)(</b>)', re.DOTALL | re.IGNORECASE)
        html_content = pattern2.sub(rf'\g<1>{guardian_name}\g<3>', html_content)

    if halka_name:
        pattern3 = re.compile(r'(<td width="36%">हल्का :- <b>)(.*?)(</b>)', re.DOTALL | re.IGNORECASE)
        html_content = pattern3.sub(rf'\g<1>{halka_name}\g<3>', html_content)

    if mauja_name:
        pattern4 = re.compile(r'(<td width="35%">मौजा :- <b>)(.*?)(</b>)', re.DOTALL | re.IGNORECASE)
        html_content = pattern4.sub(rf'\g<1>{mauja_name}\g<3>', html_content)

    if mauja_thana_name:
        pattern5 = re.compile(r'(<td width="35%">मौजा/थाना संख्या :- <b>)(.*?)(</b>)', re.DOTALL | re.IGNORECASE)
        html_content = pattern5.sub(rf'\g<1>{mauja_thana_name}\g<3>', html_content)

    if url_path != old_url:
        full_receipt_link = request.host_url + url_path
        qr_maker = qrcode.QRCode(version=7, error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=10, border=1)
        qr_maker.add_data(full_receipt_link)
        qr_maker.make(fit=True)
        img = qr_maker.make_image(fill_color="black", back_color="white")
        img_io = BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        qr_base64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
        new_qr_tag = f'<img src="data:image/png;base64,{qr_base64}" width="125" height="125" style="border: none; filter: blur(0.15px);">'
        html_content = re.sub(r'<img[^>]+src="data:image/[^;]+;base64,[^"]+"[^>]*>', new_qr_tag, html_content, count=1)

    try:
        query = supabase.table('receipts').update({
            'url_path': url_path, 
            'html_content': html_content
        }).eq('id', id)
        if session.get('is_admin'): query = query.is_('user_id', 'null')
        else: query = query.eq('user_id', session.get('user_id'))
        query.execute()
    except Exception as e:
        return "URL pehle se maujud hai, kripya dusra link daalein."

    return redirect(url_for('index'))

@app.route('/edit/<int:id>')
def edit(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    
    query = supabase.table('receipts').select('id, url_path, html_content').eq('id', id)
    if session.get('is_admin'): query = query.is_('user_id', 'null')
    else: query = query.eq('user_id', session.get('user_id'))
    response = query.execute()

    if response.data:
        row = response.data[0]
        page = (row['id'], row['url_path'], row['html_content'])
        return render_template('edit.html', page=page)
    return "Page nahi mila!", 404

@app.route('/update/<int:id>', methods=['POST'])
def update(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    
    new_html = request.form['html_content']
    query = supabase.table('receipts').update({'html_content': new_html}).eq('id', id)
    if session.get('is_admin'): query = query.is_('user_id', 'null')
    else: query = query.eq('user_id', session.get('user_id'))
    query.execute()
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
def delete(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    
    query = supabase.table('receipts').delete().eq('id', id)
    if session.get('is_admin'): query = query.is_('user_id', 'null')
    else: query = query.eq('user_id', session.get('user_id'))
    query.execute()
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
