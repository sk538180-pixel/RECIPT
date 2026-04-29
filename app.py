from flask import Flask, render_template, request, redirect, url_for, render_template_string
from supabase import create_client, Client

app = Flask(__name__)

# Supabase Setup
SUPABASE_URL = "https://qtzmgxvjibivdgodcfwz.supabase.co"
SUPABASE_KEY = "sb_publishable_mLPBhmg1wc15tJOzbRd6Qg_nu30nfMC"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def index():
    response = supabase.table('receipts').select('id, url_path').order('id', desc=True).execute()
    pages = [(row['id'], row['url_path']) for row in response.data]
    return render_template('index.html', pages=pages)

@app.route('/create', methods=['POST'])
def create():
    url_path = request.form['custom_url'].strip().replace(" ", "")
    
    if url_path.startswith('/'):
        url_path = url_path[1:]

    data = {
        'District': request.form.get('district', '').strip(),
        'Anchal': request.form.get('anchal', '').strip(),
        'Halka': request.form.get('halka', '').strip(),
        'Mauja': request.form.get('mauja', '').strip(),
        'Name': request.form.get('name', '').strip(),
        'Name2': request.form.get('name2', '').strip(),
        'Pata': request.form.get('pata', '').strip(),
        'Thana': request.form.get('thana', '').strip(),
        'Khata': request.form.get('khata', '').strip(),
        'Khesra': request.form.get('khesra', '').strip()
    }

    final_html = render_template('receipt_template.html', **data)

    try:
        supabase.table('receipts').insert({'url_path': url_path, 'html_content': final_html}).execute()
    except Exception as e:
        return "Ye Link pehle se kisi aur ne bana liya hai, kripya back ja kar dusra link daalein."

    return redirect(url_for('index'))

@app.route('/edit/<int:id>')
def edit(id):
    response = supabase.table('receipts').select('id, url_path, html_content').eq('id', id).execute()
    
    if response.data:
        row = response.data[0]
        page = (row['id'], row['url_path'], row['html_content'])
        return render_template('edit.html', page=page)
    return "Page nahi mila!", 404

@app.route('/update/<int:id>', methods=['POST'])
def update(id):
    new_html = request.form['html_content']
    supabase.table('receipts').update({'html_content': new_html}).eq('id', id).execute()
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
def delete(id):
    supabase.table('receipts').delete().eq('id', id).execute()
    return redirect(url_for('index'))

@app.route('/<path:url_path>')
def view_page(url_path):
    response = supabase.table('receipts').select('html_content').eq('url_path', url_path).execute()
    
    if response.data:
        return render_template_string(response.data[0]['html_content'])
    else:
        return "Receipt Not Found!", 404

if __name__ == '__main__':
    app.run()
