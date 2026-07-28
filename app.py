import os
import cloudinary
import cloudinary.uploader
from flask import Flask, render_template, request, redirect, url_for, session
from pymongo import MongoClient
import certifi
from bson.objectid import ObjectId
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__, static_folder='assets', static_url_path='/assets')
app.secret_key = 'super_secret_key'

# --- 1. MONGODB CONNECTION ---
MONGO_URI = os.environ.get('MONGO_URI')
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['portfolio_db']

certificates_col = db['certificates']
projects_col = db['projects']
visitors_col = db['visitors']
settings_col = db['settings']  # <--- NEW: Settings Collection

# --- 2. CLOUDINARY CONFIG ---
cloudinary.config(
    cloud_name = os.environ.get('CLOUDY_NAME'), 
    api_key = os.environ.get('CLOUDY_KEY'), 
    api_secret = os.environ.get('CLOUDY_SECRET'),
    secure = True
)

# --- ROUTES ---

@app.route('/')
def index():
    try:
        # Visitor Counter
        visitor_data = visitors_col.find_one_and_update(
            {'_id': 'site_stats'},
            {'$inc': {'count': 1}},
            upsert=True,
            return_document=True
        )
        total_views = visitor_data['count'] if visitor_data else 0

        # Fetch Data
        certificates = list(certificates_col.find().sort('position', 1))
        projects = list(projects_col.find().sort('position', 1))
        
        # Fetch Settings (Resume & Drive Link)
        settings = settings_col.find_one({'_id': 'general'}) or {}
        resume_url = settings.get('resume_url', '#')
        drive_link = settings.get('drive_link', '#')
        github_link = settings.get('github_link', 'https://github.com/Sivaraj-T-hash?tab=repositories')
        
        return render_template('index.html', 
                               certificates=certificates, 
                               projects=projects,
                               visitors=total_views,
                               resume_url=resume_url,
                               drive_link=drive_link,
                               github_link=github_link)
    except Exception as e:
        return f"<h1 style='color:red'>Database Error:</h1><p>{e}</p>"


@app.route('/admin')
def admin():
    if 'logged_in' not in session: return render_template('admin_login.html')
    certificates = list(certificates_col.find().sort('position', 1))
    projects = list(projects_col.find().sort('position', 1))
    
    settings = settings_col.find_one({'_id': 'general'}) or {}
    return render_template('admin.html', certificates=certificates, projects=projects, settings=settings)

@app.route('/login', methods=['POST'])
def login():
    # 1. Get the data from the HTML form
    username = request.form.get('username')
    password = request.form.get('password')
    
    # 2. Fetch the secrets from Render Environment Variables
    admin_user = os.environ.get('ADMIN_USER', 'admin') 
    admin_pass = os.environ.get('ADMIN_PASS')

    # 3. Perform the check
    if username == admin_user and password == admin_pass:
        session['logged_in'] = True
        return redirect(url_for('admin'))
    else:
        return render_template('admin_login.html', error="Invalid Credentials")
        
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

# --- NEW: UPDATE SITE SETTINGS ROUTE ---
@app.route('/update_site_settings', methods=['POST'])
def update_site_settings():
    if 'logged_in' not in session: return redirect(url_for('login'))
    
    try:
        update_data = {}
        
        drive_link = request.form.get('drive_link')
        if drive_link:
            update_data['drive_link'] = drive_link

        github_link = request.form.get('github_link')
        if github_link:
            update_data['github_link'] = github_link

        resume = request.files.get('resume')
        if resume and resume.filename != '':
            exact_filename = secure_filename(resume.filename)
            resume_upload = cloudinary.uploader.upload(
                resume, 
                resource_type="raw",
                public_id=exact_filename
            )
            update_data['resume_url'] = resume_upload['secure_url']

        if update_data:
            settings_col.update_one(
                {'_id': 'general'}, 
                {'$set': update_data}, 
                upsert=True
            )

        return redirect(url_for('admin'))

    except Exception as e:
        return f"<h1>Error updating settings:</h1><p>{str(e)}</p><br><a href='/admin'>Go Back</a>"

@app.route('/add_certificate', methods=['POST'])
def add_certificate():
    if 'logged_in' not in session: return redirect(url_for('login'))
    try:
        title = request.form['title']
        image = request.files['image']
        if image:
            upload_result = cloudinary.uploader.upload(image)
            certificates_col.insert_one({
                'title': title, 
                'image': upload_result['secure_url'], 
                'position': 0 
            })
        return redirect(url_for('admin'))
    except Exception as e:
        return f"<h1>Upload Error:</h1><p>{e}</p><a href='/admin'>Back</a>"

@app.route('/delete_certificate/<string:id>')
def delete_certificate(id):
    if 'logged_in' not in session: return redirect(url_for('admin'))
    certificates_col.delete_one({'_id': ObjectId(id)})
    return redirect(url_for('admin'))

@app.route('/add_project', methods=['POST'])
def add_project():
    if 'logged_in' not in session: return redirect(url_for('login'))

    try:
        title = request.form['title']
        category = request.form['category']
        description = request.form.get('description', '')
        
        image = request.files['image']
        report = request.files.get('report')

        if image:
            image_upload = cloudinary.uploader.upload(image)
            image_url = image_upload['secure_url']

            report_url = ""
            if report and report.filename != '':
                exact_filename = secure_filename(report.filename)
                report_upload = cloudinary.uploader.upload(
                    report, 
                    resource_type="raw",
                    public_id=exact_filename 
                )
                report_url = report_upload['secure_url']
            
            projects_col.insert_one({
                'title': title,
                'category': category,
                'description': description,
                'image': image_url,
                'report': report_url,
                'position': 0
            })
            
        return redirect(url_for('admin'))

    except Exception as e:
        return f"<h1>Error during Upload:</h1><p>{str(e)}</p><br><a href='/admin'>Go Back</a>"

@app.route('/delete_project/<string:id>')
def delete_project(id):
    if 'logged_in' not in session: return redirect(url_for('admin'))
    projects_col.delete_one({'_id': ObjectId(id)})
    return redirect(url_for('admin'))

@app.route('/reorder', methods=['POST'])
def reorder():
    if 'logged_in' not in session: return "Unauthorized", 401
    data = request.get_json()
    collection = certificates_col if data.get('collection') == 'certificates' else projects_col
    for index, item_id in enumerate(data.get('order')):
        collection.update_one({'_id': ObjectId(item_id)}, {'$set': {'position': index}})
    return "OK", 200

@app.route('/project/<int:id>')
def project_details(id):
    projects = list(projects_col.find().sort('position', 1))
    if 0 <= id < len(projects):
        project = projects[id]
        return render_template('project_details.html', project=project)
    return redirect(url_for('index'))

@app.route('/edit_project/<string:id>')
def edit_project_page(id):
    if 'logged_in' not in session: return redirect(url_for('login'))
    project = projects_col.find_one({'_id': ObjectId(id)})
    return render_template('edit_project.html', project=project)

@app.route('/update_project/<string:id>', methods=['POST'])
def update_project(id):
    if 'logged_in' not in session: return redirect(url_for('login'))
    
    try:
        title = request.form['title']
        category = request.form['category']
        description = request.form['description']
        
        image = request.files.get('image')
        report = request.files.get('report')
        
        update_data = {
            'title': title,
            'category': category,
            'description': description
        }

        if image and image.filename != '':
            image_upload = cloudinary.uploader.upload(image)
            update_data['image'] = image_upload['secure_url']

        if report and report.filename != '':
            exact_filename = secure_filename(report.filename)
            report_upload = cloudinary.uploader.upload(
                report, 
                resource_type="raw",
                public_id=exact_filename
            )
            update_data['report'] = report_upload['secure_url']

        projects_col.update_one({'_id': ObjectId(id)}, {'$set': update_data})
        return redirect(url_for('admin'))

    except Exception as e:
        return f"<h1>Update Error:</h1><p>{str(e)}</p><a href='/admin'>Back</a>"

if __name__ == '__main__':
    app.run(debug=True,use_reloader=False)
