import flask
from flask import request
import os
from io import StringIO
import csv
from . import worker
from .db import JobDB, ARCHIVE_NAME
from datetime import datetime
import re

# Our Flask application.
app = flask.Flask(__name__, instance_relative_config=True)

# Configuration. We include some defaults and allow overrides.
app.config.update(
    UPLOAD_EXTENSIONS=['zip'],
    SEASHELL_COMPILER='seac',
)
app.config.from_pyfile('buildbot.cfg', silent=True)

# Connect to our database.
db = JobDB(app.instance_path)


def _unpad(s):
    """Remove padding zeroes from a formatted date string."""
    return re.sub(r'(^|\s)0+', r'\1', s)


@app.template_filter('dt')
def _datetime_filter(value, withtime=True):
    """Format a timestamp (given as a float) as a human-readable string.
    `withtime` indicates whether this should be just a day or a day with
    a time.
    """
    if not value:
        return ''
    dt = datetime.fromtimestamp(value)

    fmt = '%B %d, %Y'
    if withtime:
        fmt += ', %I:%M %p'
    return _unpad(dt.strftime(fmt))


@app.before_first_request
def start_work_threads():
    """Create and start our worker threads.
    """
    work_threads = worker.work_threads(db, app.config)
    for thread in work_threads:
        if not thread.is_alive():
            thread.start()


@app.route('/jobs', methods=['POST'])
def add_job():
    if 'file' not in request.files:
        return 'missing file', 400
    file = request.files['file']

    # Check that the file has an allowed extension.
    _, ext = os.path.splitext(file.filename)
    if ext[1:] not in app.config['UPLOAD_EXTENSIONS']:
        return 'invalid extension {}'.format(ext), 400

    # Create a job record.
    job = db.add('uploading')

    # Create the job's directory and save the code there.
    path = db.job_dir(job['name'])
    os.mkdir(path)
    archive_path = os.path.join(path, ARCHIVE_NAME + ext)
    file.save(archive_path)

    # Mark it as uploaded.
    db.set_state(job, 'uploaded')

    # In the browser, redirect to the detail page. Otherwise, just
    # return the job name.
    if request.values.get('browser'):
        return flask.redirect(flask.url_for('show_job', name=job['name']))
    else:
        return job['name']


@app.route('/jobs.csv')
def jobs_csv():
    output = StringIO()
    writer = csv.DictWriter(
        output,
        ['name', 'started', 'state'],
    )
    writer.writeheader()

    for job in db.jobs:
        writer.writerow({
            'name': job['name'],
            'started': job['started'],
            'state': job['state'],
        })

    csv_data = output.getvalue()
    return csv_data, 200, {'Content-Type': 'text/csv'}


@app.route('/')
def jobs_list():
    return flask.render_template('joblist.html', jobs=db.jobs)


@app.route('/jobs/<name>.html')
def show_job(name):
    job = db.get(name)

    # Find all the job's files.
    job_dir = db.job_dir(name)
    paths = []
    for dirpath, dirnames, filenames in os.walk(job_dir):
        dp = os.path.relpath(dirpath, job_dir)
        for fn in filenames:
            if not fn.startswith('.'):
                paths.append(os.path.join(dp, fn))

    return flask.render_template('job.html', job=job, files=paths)


@app.route('/jobs/<name>')
def get_job(name):
    job = db.get(name)
    return flask.jsonify(job)


@app.route('/jobs/<name>/files/<path:filename>')
def job_file(name, filename):
    # Make sure this job actually exists.
    db.get(name)

    # Send the file.
    return flask.send_from_directory(db.job_dir(name), filename)
