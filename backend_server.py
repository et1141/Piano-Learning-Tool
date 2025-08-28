from flask import Flask, request, jsonify, send_from_directory, send_file, render_template
from flask_cors import CORS
import os
import subprocess
from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH
from synthviz import create_video
import json
import re
import yt_dlp
import time
import os, shutil


from music21 import converter, stream, interval, key, midi

import threading



# download thumbnail
import requests
from PIL import Image
from io import BytesIO

import sqlite3





app = Flask(__name__)
CORS(app) # Let any domain to access the API


DB_PATH = 'songs.db'
UPLOAD_FOLDER = 'uploads'
MIDI_FOLDER = 'midi'
VIDEO_FOLDER = 'videos'
XML_FOLDER ='xml'
PDF_FOLDER = 'pdf'
THUMBNAILS_FOLDER = 'thumbnails'
SONGS_JSON = 'songs.json'



os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MIDI_FOLDER, exist_ok=True)
os.makedirs(VIDEO_FOLDER, exist_ok=True)
os.makedirs(XML_FOLDER, exist_ok=True)
os.makedirs(PDF_FOLDER, exist_ok=True)
os.makedirs(THUMBNAILS_FOLDER, exist_ok=True)


allowedFieldsSongs = {'song_id','user_id','title','audio_path', 'source','duration','picture_path', 
                       'original_key_root','original_key_mode','uploaded_date',}
                
allowedFieldsSongVersions= {'version_id', 'song_id', 'model_name','title_version','key_root', 'key_mode','instrument' , 
                              'filename' ,'midi_path' ,'pdf_path', 'musicxml_path', 'video_path','picture_version_path',
                              'description', 'created_at','is_public'}
allowedFields = allowedFieldsSongs | allowedFieldsSongVersions
fieldsToDeleteOnMidiChange = ['pdf_path', 'musicxml_path', 'video_path']
filesToDelete = ['pdf_path', 'musicxml_path', 'video_path', 'audio_path','midi_path']
fieldsModal = ["version_id", "title", "key_root", "key_mode", "picture_path", "description", "is_public"]



# Sync objects
videoGenerationJobs = set()
videoGenerationJobsLock = threading.Lock()  #Protects videoGenerationJobs set

songUploadLock = threading.Lock()  # Ensures only one song upload is processed at a time
uploadLockStartTime = None
uploadLockTimeout = 60 * 5  

######################################## Database functions  ########################################

def get_db_connection(): 
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  
    return conn

### CREATE

def add_new_song(**kwargs):
    if not kwargs.get('audio_path'):
        raise ValueError("Missing required field: audio_path")
    for f in kwargs.keys():
        if f not in allowedFieldsSongs and f != "uploaded_date": 
            raise ValueError(f"Unrecognized field: {f}")

    fields = ', '.join(kwargs.keys())
    placeholders = ', '.join(['?'] * len(kwargs))
    values = list(kwargs.values())

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f'''
        INSERT INTO songs ({fields})
        VALUES ({placeholders})
    ''', values)

    song_id = cur.lastrowid
    conn.commit()
    conn.close()
    return song_id


def add_new_song_version(song_id,model_name,key_root,key_mode,instrument,filename,midi_path):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO song_versions (song_id,model_name,key_root,key_mode,instrument,filename,midi_path) VALUES (?,?,?,?,?,?,?)',
                (song_id,model_name,key_root,key_mode,instrument,filename,midi_path))
    song_version_id = cur.lastrowid
    conn.commit()
    conn.close()
    return song_version_id


### READ

def get_song(song_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM songs where song_id = ?',(song_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return row
    else:
        return None #TODO
    
def get_song_version(song_version_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM song_versions WHERE version_id = ?',(song_version_id,))
    row = cur.fetchone() 
    conn.close()
    if row:
        return row
    else:
        return None #TODO 
    

def get_song_versions(fields=None, version_id=None):
    conn = get_db_connection()
    cur = conn.cursor()

    if fields:
        # if field is a single element convert it to list
        if isinstance(fields, str):
            fields = [fields]
        selected_fields = []
        for f in fields:
            if f not in allowedFields:
                raise ValueError(f"Unrecognized field: {f}")
            if f == 'title':
                selected_fields.append("COALESCE(title_version, title) AS title")
            elif f == 'picture_path':
                selected_fields.append("COALESCE(picture_version_path, picture_path) AS picture_path")
            else:
                selected_fields.append(f)

        field_str = ', '.join(selected_fields)
    else:
        field_str = '*'  

    query = f'SELECT {field_str} FROM song_versions LEFT JOIN songs ON song_versions.song_id = songs.song_id'

    if version_id is not None:
        query += ' WHERE song_versions.version_id = ?'
        cur.execute(query, (version_id,))
    else:
        cur.execute(query)

    rows = cur.fetchall() 
    conn.close()
    if not rows:
        return None
    if version_id is not None:
        return dict(rows[0])
    return [dict(row) for row in rows]


@app.route('/api/get-song-version/<int:songVersionId>')
def get_song_version_api(songVersionId):
    song_version = get_song_versions(fields=fieldsModal, version_id=songVersionId)

    if song_version:
        return song_version, 200

    return {'error': 'Not found'}, 404

@app.route('/api/get-song-version-title/<int:songVersionId>')


def get_song_version_title_api(songVersionId):
    song_version = get_song_versions(fields=fieldsModal, version_id=songVersionId)

    if song_version:
        return {'success': True, 'title': song_version}, 200

    return {'error': 'Not found'}, 404

    

def get_table(table):
    if not table.isidentifier():
        raise ValueError("Invalid table name")  # SQL injection protection
    conn = get_db_connection()
    cur = conn.cursor()
    query = f'SELECT * FROM {table}'
    cur.execute(query)
    rows = cur.fetchall()
    conn.close()
    if rows:
        return rows    
    else: 
        return None #TODO




### UPDATE
def map_song_versions_field_name(field): #this function is only used by update_song_version 
    if field=='picture_path':
        return 'picture_version_path'
    if field=='title':
        return 'title_version'
    return field

def update_song(songId, **kwargs):
    if not kwargs:
        return  # nothing to update
    for f in kwargs:
        if f not in allowedFieldsSongs:
            raise ValueError(f"Unrecognized field for update: {f}")
        
    fields = ', '.join(f"{f} = ?" for f in kwargs)
    values = list(kwargs.values())
    values.append(songId)  

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f'''
        UPDATE songs
        SET {fields}

        WHERE song_id = ?
    ''', values)

    conn.commit()
    conn.close()


def update_song_version(songVersionId, **kwargs):
    if not kwargs:
        return  

    for f in kwargs:
        if f not in allowedFieldsSongVersions:
            raise ValueError(f"Unrecognized field for update: {f}")
        
    fields = ', '.join(f"{map_song_versions_field_name(f)} = ?" for f in kwargs)
    values = list(kwargs.values())
    values.append(songVersionId)  
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f'''
        UPDATE song_versions
        SET {fields}

        WHERE version_id = ?
    ''', values)

    conn.commit()
    conn.close()



### DELETE
def delete_song_version(songVersionId):
    conn = get_db_connection()
    cur = conn.cursor()

    row = get_song_versions(fields=filesToDelete, version_id=songVersionId)
    if row:
        for col in filesToDelete:
            file_path = row.get(col) 
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"[delete_song_version] Error while deleting {file_path}: {e}")

    cur.execute('DELETE FROM song_versions WHERE version_id = ?',(songVersionId,))
    deleted_count = cur.rowcount
    conn.commit()
    conn.close()

    return deleted_count
 
    


########################################################    Other      ###############################################

def safe_filename_song(title):
    title = title.replace(' ', '_')  
    title = re.sub(r'[^a-zA-Z0-9_\-\.]', '', title)  
    return title

def safe_filename_version(title,model_name,key_root,key_mode):
    title = title.replace(' ', '_')  
    title = re.sub(r'[^a-zA-Z0-9_\-\.]', '', title)  
    return f"{title}_{model_name}_{key_root}_{key_mode}"


def transkun_predict(audio_path,midi_path):
    try:
        subprocess.run(['transkun', audio_path, midi_path], check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Transkun failed: {e}")

    return midi_path


################################################## Music functions  ##################################################

def get_duration_ffmpeg(path):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True, text=True
    )
    meta = json.loads(result.stdout)
    return float(meta["format"]["duration"])

def get_instrument(score):
    instruments = list(score.recurse().getElementsByClass('Instrument'))

    instrument_name = None
    for inst in instruments:
        name = inst.instrumentName or inst.bestName()
        if name:
            instrument_name = name
            break

    if instrument_name:
        print(f"[get_instrument]: Instrument {instrument_name}")
    else:
        instrument_name = "Unknown"
        print("[get_instrument]: No instrument found — (saved as Unknown")
    return instrument_name

def transpose_key_root(midi_path, new_key, curr_key=None):
    score = converter.parse(midi_path)
    if not curr_key:
       curr_key = score.analyze('key')
    else:
        curr_key=key.Key(curr_key)
   # curr_key = score.analyze('key')

    target_key = key.Key(new_key)
    i = interval.Interval(curr_key.tonic, target_key.tonic)
    print("[transpose_key_root]: key_root interval is: " + str(i))

    transposed_score = score.transpose(i)

    mf = midi.translate.music21ObjectToMidiFile(transposed_score)
    mf.open(midi_path, 'wb')
    mf.write()
    mf.close()


#############################################################      API    ###################################################

@app.route("/")
def serve_index():
    return send_from_directory(".", "index.html")

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory("static", path)

@app.route('/api/get-songs-list-dropdown', methods=['GET'])
def get_midi_files_dropdown():
    songs = get_song_versions(('version_id','title'))

    return jsonify(songs)

@app.route('/api/get-songs-list-gallery', methods=['GET'])
def get_midi_files_gallery():
    songs = get_song_versions(('version_id','title', 'source',
                               'picture_path','uploaded_date','key_root', 'key_mode',  'duration', 'description'))
    return jsonify(songs)



def update_save_version_song_api(songVersionId, songVersionDataMap):
    songVersion = get_song_versions(version_id=songVersionId)
    print("[update_save_version_song_api]: songversion = ", str(songVersion))
    if not songVersion:
        return jsonify({'error': 'Song version not found'}), 404

    # create new record from the old one 
    newSongVersionId = add_new_song_version(
        songVersion.get('song_id'),
        songVersion.get('model_name'),
        songVersion.get('key_root'),
        songVersion.get('key_mode'),
        songVersion.get('instrument'),
        songVersion.get('filename'),
        songVersion.get('midi_path'),
    )

    #copy midi, change filename/midi_path to be independent
    try:
        orig_midi = songVersion.get('midi_path')
        if orig_midi:
            base, ext = os.path.splitext(orig_midi)
            new_midi = f"{base}-{newSongVersionId}{ext or ''}"
            os.makedirs(os.path.dirname(new_midi), exist_ok=True)
            try:
                shutil.copy2(orig_midi, new_midi)
            except FileNotFoundError:
                new_midi = orig_midi  
            songVersionDataMap['midi_path'] = new_midi

        orig_filename = songVersion.get('filename')
        if orig_filename:
            fbase, fext = os.path.splitext(orig_filename)
            songVersionDataMap['filename'] = f"{fbase}-{newSongVersionId}{fext or ''}"
    except Exception as e:
        print(f"[update_save_version_song_api] copy-midi-error: {e}")

    currKey = songVersion.get('key_root')
    newKey = songVersionDataMap.get('key_root')

    if newKey and currKey != newKey:
        midi_path = songVersionDataMap.get('midi_path') or get_song_versions(fields=['midi_path'], version_id=newSongVersionId).get('midi_path')
        if midi_path:
            transpose_key_root(midi_path, newKey, curr_key=currKey)
        for f in fieldsToDeleteOnMidiChange:
            songVersionDataMap[f] = ''

    update_song_version(newSongVersionId, **songVersionDataMap)
    return '', 204


@app.route('/api/update-song', methods=['POST'])
def update_version_song_api():
    data = request.get_json()
    saveAsNew = data.pop('save_as_new',None)

    songVersionDataMap={}
    songVersionId = data.pop('version_id')
    for f in data:
        mapped_field = map_song_versions_field_name(f)
        if mapped_field in allowedFieldsSongVersions: 
            songVersionDataMap[mapped_field] = data[f]
    
    if(saveAsNew):
        return update_save_version_song_api(songVersionId, songVersionDataMap)

    songVersionKeyRoot = get_song_versions(fields=['key_root'], version_id=songVersionId)
    currKey = songVersionKeyRoot.get('key_root')
    newKey = data.get('key_root')

    if newKey and currKey != newKey:
        songVersion = get_song_versions(fields=fieldsToDeleteOnMidiChange + ['midi_path'], version_id=songVersionId)
        midi_path = songVersion.get('midi_path')

        transpose_key_root(midi_path, newKey, curr_key=currKey)

        for f in fieldsToDeleteOnMidiChange:
            if songVersion.get(f):
                try:
                    os.remove(songVersion[f])
                except FileNotFoundError:
                    pass  
                except Exception as e:
                    print(f"[update_version_song_api]: Error deleting file {songVersion[f]}: {e}")
            songVersionDataMap[f] = '' 

    update_song_version(songVersionId, **songVersionDataMap)
    return '', 204


def release_upload_lock():
    global uploadLockStartTime
    if songUploadLock.locked():
        songUploadLock.release()
    uploadLockStartTime = None

@app.route('/api/tupload', methods=['POST'])
def unlock_upload():
    global uploadLockStartTime
    if songUploadLock.locked():
        release_upload_lock()
        return jsonify({'status': 'Lock released'}), 200
    return jsonify({'status': 'Lock was not active'}), 200


def force_unlock_upload_if_stuck():
    global uploadLockStartTime
    if songUploadLock.locked() and uploadLockStartTime:
        if time.time() - uploadLockStartTime > uploadLockTimeout:
            print("[force_unlock_upload_if_stuck]: Upload lock timeout reached — forcing release.")
            release_upload_lock()



@app.route('/api/upload-audio', methods=['POST'])
def upload_audio():
    force_unlock_upload_if_stuck() # Unlock if the previous job is processing for over 5 minutes

    if not songUploadLock.acquire(blocking=False):  # try to acquire the lock without waiting (blocking=True would wait until the lock is released), if another upload is in progress return 429
        return jsonify({"error": "Another upload job in progress"}), 429
    
    global uploadLockStartTime
    uploadLockStartTime = time.time()

    try:
        if 'audio_file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        audio_file = request.files['audio_file']
        if audio_file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        user_id = 1 
        title = audio_file.filename 
        filename = safe_filename_song(title) + '.mp3'
        audio_path = os.path.join(UPLOAD_FOLDER, filename)
        audio_file.save(audio_path)
        duration_seconds = get_duration_ffmpeg(audio_path)
         
        song_id = add_new_song(user_id=user_id, title=title,audio_path=audio_path,duration=duration_seconds)
        return jsonify({'song_id': song_id}), 200 
    except Exception as e:
        print("[upload_audio]: Upload audio  error:", e)
        release_upload_lock()
        return jsonify({'error': str(e)}), 500 # Server-side error


@app.route('/api/download-upload-audio', methods=['POST'])
def download_audio_yt_dlp():
    force_unlock_upload_if_stuck() #unlock if the previous job is processing for over 5 minutes

    if not songUploadLock.acquire(blocking=False):  # try to acquire the lock without waiting (blocking=True would wait until the lock is released), if another upload is in progress return 429
        return jsonify({"error": "Another upload job in progress"}), 429

    global uploadLockStartTime
    uploadLockStartTime = time.time()

    data = request.get_json()
    user_id = 1 
    youtube_url = data.get('youtube_url')

    if not youtube_url:
        return jsonify({'error': 'Missing YouTube URL'}), 400

    try:
        # Download data (without audio - just to get the title)
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl_info:
            info = ydl_info.extract_info(youtube_url, download=False)
        video_title = info.get('title', 'unknown_title')
        duration_seconds = info.get('duration',None)

        title = video_title 
        safe_filename = safe_filename_song(video_title) 
        audio_path = os.path.join(UPLOAD_FOLDER, safe_filename) # without '.mp3' at the end because yt-dlp appends it 
        thumbnail_url = info.get('thumbnail')  
        image_path = None

        if thumbnail_url:
            try:
                res = requests.get(thumbnail_url)
                if res.status_code == 200:
                    image_path = os.path.join(THUMBNAILS_FOLDER, safe_filename + '.jpg')
                    with open(image_path, 'wb') as f:
                        f.write(res.content)
            except Exception as e:
                print("[download_audio_yt_dlp]: Warning: Couldn't download thumbnail:", e)

        # Download and convert to mp3 with yt-dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': audio_path + '.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'noplaylist': True,
            'quiet': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
        song_id = add_new_song(user_id=user_id, title=title,audio_path=audio_path+'.mp3',source=youtube_url,picture_path=image_path,duration=duration_seconds)
        return jsonify({'song_id': song_id, 'title':title}), 200
     
    except Exception as e:
        print("[download_audio_yt_dlp]: YouTube download error:", e)
        release_upload_lock()
        return jsonify({'error': str(e)}), 500 # Server-side error
    


@app.route('/api/convert-audio', methods=['POST'])
def convert_audio():
    try: 
        # Prepare metadata
        data = request.get_json()
        model_name = data.get('model_name', 'transkun') # transkun is the default model
        song_id = data.get('song_id')
        song = get_song(song_id)
        if not song:
            raise ValueError("Song not found")
        title = song['title']
        audio_path = song['audio_path']
        temp_midi_filename = f"temp_{song_id}_{model_name}.mid"
        temp_midi_path = os.path.join(MIDI_FOLDER, temp_midi_filename)

        # Audio to midi conversion     
        if model_name == 'transkun':
            #midi_path = transkun_predict(song_id,midi_path) # transkun saves midi_data!
            transkun_predict(audio_path,temp_midi_path) 
        else: 
            model_output, midi_data, note_events = predict(audio_path, model_or_model_path=ICASSP_2022_MODEL_PATH)
            midi_data.write(temp_midi_path)

        # Song metadata analysis
        score = converter.parse(temp_midi_path)
        key_signature_data = score.analyze('key')
        print(f"[convert_audio]: Key = {key_signature_data.tonic.name} {key_signature_data.mode}")
        key_root = key_signature_data.tonic.name
        key_mode = key_signature_data.mode
        instrument = get_instrument(score)

        # Rename midi file and save to database 
        filename=safe_filename_version(title,model_name,key_root,key_mode) 
        midi_path = os.path.join(MIDI_FOLDER, f"{filename}.mid")
        song_version_id = add_new_song_version(song_id,model_name,key_root,key_mode,instrument,filename,midi_path)
        os.rename(temp_midi_path, midi_path)
        update_song(song_id,original_key_root=key_root,original_key_mode=key_mode)
    
        return jsonify({'title': title, 'song_version_id': song_version_id}), 200
    
    except Exception as e:
        print("[convert_audio]: Audio to midi converion failed:", e)
        return jsonify({'error': str(e)}), 500 # Server-side error
    finally:
        release_upload_lock()

########################################################################################################################


def generate_video(songVersionId):
    with videoGenerationJobsLock:
        if songVersionId in videoGenerationJobs:
            raise RuntimeError("Video already generating")
        videoGenerationJobs.add(songVersionId)

    try:
        print(f"[generate_video]: Starting generation for version_id={songVersionId}")
        song_version = get_song_version(songVersionId)
        midi_path = song_version['midi_path']

        if not os.path.exists(midi_path):
            raise FileNotFoundError("MIDI file not found")

        video_filename = song_version['filename'] + '.mp4'
        new_video_path = os.path.join(VIDEO_FOLDER, video_filename)

        print(f"[generate_video] Generating video at: {new_video_path}")
        create_video(input_midi=midi_path, video_filename=new_video_path)
        update_song_version(songVersionId, video_path=new_video_path)

    finally:
        with videoGenerationJobsLock:
            videoGenerationJobs.pop(songVersionId)
        print(f"[generate_video]: Finished generation for version_id={songVersionId}")


@app.route('/api/get-video', methods=['GET', 'HEAD'])
def get_video():
    def error_response(status, message):
        if request.method == 'HEAD':
            return '', status
        return jsonify({'error': message}), status
    
    video_was_generated = False
    songVersionId = request.args.get('song_version_id')
    if not songVersionId:
        return error_response(404, 'Song version not found')

    row = get_song_versions(fields=['video_path'], version_id=songVersionId)
    video_path = row.get('video_path') if row else None

    if not video_path or not os.path.exists(video_path):
        try:
            generate_video(songVersionId)
            video_was_generated = True

        except RuntimeError as e:
            return error_response(429, str(e))  # Conflict: another job is running
        except Exception as e:
            return error_response(500, f'Failed to generate video: {str(e)}') # Server-side error
 
 
        row = get_song_versions(fields=['video_path'], version_id=songVersionId)
        video_path = row.get('video_path') if row else None

    if not video_path or not os.path.exists(video_path): 
        return error_response(404, 'Video file not found')

    if request.method == 'HEAD':
        statusCode =  201 if video_was_generated else 200
        return '', statusCode

    return send_file(video_path)


@app.route('/api/get-audio', methods=['GET'])
def get_audio():
    songVersionId = request.args.get('song_version_id')
    if not songVersionId:
        return jsonify({'error': 'Song version not found'}), 404
    row = get_song_versions(fields=['audio_path','filename'], version_id=songVersionId)
    audio_path = row.get('audio_path') if row else None
    filename = row.get('filename') + '.mp3'
    return send_file(audio_path, download_name = filename)

@app.route('/api/get-midi', methods=['GET'])
def get_midi():
    songVersionId = request.args.get('song_version_id')
    if not songVersionId:
        return jsonify({'error': 'Song version not found'}), 404
    row = get_song_versions(fields=['midi_path','filename'], version_id=songVersionId)
    midi_path = row.get('midi_path') if row else None
    filename = row.get('filename') + '.mid'
    return send_file(midi_path, download_name = filename)

@app.route('/api/get-musicxml', methods=['GET'])
def get_musicxml():
    songVersionId = request.args.get('song_version_id')
    if not songVersionId:
        return jsonify({'error': 'Song version not found'}), 404

    row = get_song_versions(fields=['musicxml_path','midi_path','filename'], version_id=songVersionId)
    musicxml_path = row.get('musicxml_path') if row else None
    filename = row.get('filename') + '.musicxml'

    if not musicxml_path or not os.path.exists(musicxml_path):
        midi_path = row.get('midi_path') 
        musicxml_path = os.path.join(XML_FOLDER, filename)
        try:
            s = converter.parse(midi_path)
            s.write('musicxml', musicxml_path)
            print(f"[get_musicxml]: Successfully converted {midi_path} to {musicxml_path}")
            update_song_version(songVersionId, musicxml_path=musicxml_path)
        except Exception as e:
            print(f"[get_musicxml]: Error during conversion: {e}")
            return jsonify({'error': 'Failed to convert MIDI to MusicXML', 'details': str(e)}), 500 # Server-side error
        
    return send_file(musicxml_path, download_name = filename)


@app.route('/api/get-pdf', methods=['GET'])
def get_pdf():
    songVersionId = request.args.get('song_version_id')
    if not songVersionId:
        return jsonify({'error': 'Song version not found'}), 404

    row = get_song_versions(fields=['pdf_path','midi_path','filename'], version_id=songVersionId)
    pdf_path = row.get('pdf_path') if row else None
    filename_base = row.get('filename') 
    filename = filename_base + '.pdf'
    
    if not pdf_path or not os.path.exists(pdf_path):
        midi_path = row.get('midi_path') 

        output_path = os.path.join(PDF_FOLDER, filename_base) 
        
        try:
            s = converter.parse(midi_path)
            pdf_path = s.write('lily.pdf', output_path)
            if os.path.exists(output_path): #music21 creates 2 files: 'pdf_path' and 'pdf_path'+'.pdf'
                os.remove(output_path) 

            print(f"[get_pdf]: Successfully converted {midi_path} to {pdf_path}")
            update_song_version(songVersionId, pdf_path=str(pdf_path))
        except Exception as e:
            print(f"[get_pdf]: Error during conversion: {e}")
            return jsonify({'error': 'Failed to convert MIDI to PDF', 'details': str(e)}), 500 # Server-side error

    return send_file(pdf_path, as_attachment=True, download_name = filename)


@app.route('/midi/<filename>', methods=['GET'])
def get_midi_file(filename):
    return send_from_directory(MIDI_FOLDER, filename)

@app.route('/api/delete-song-version/<int:songVersionId>', methods=['DELETE'])
def delete_song_version_api(songVersionId):
    deleted_count = delete_song_version(songVersionId)
    if deleted_count == 0:
        return {'error': 'Not found'}, 404
    return {'success': True, 'deleted_id': songVersionId}, 200
    




@app.route('/api/get-song-picture/<int:songVersionId>')
def get_song_picture(songVersionId):
    row = get_song_versions(fields=['picture_path'], version_id=songVersionId)

    if row and row["picture_path"]:
        picture_path = row["picture_path"]
        if picture_path.startswith("http://") or picture_path.startswith("https://"):
            try: 
                response = requests.get(picture_path)
                if response.status_code == 200:
                    return send_file(
                        BytesIO(response.content),
                        mimetype='image/png'
                    )
            except requests.exceptions.RequestException as e:
                print(f"[get_song_picture]: Error while fetching image from the URL: {e}")
        return send_file(row["picture_path"], mimetype='image/png')
    
    
    return send_file("static/music2.png", mimetype='image/png')




@app.route('/game')
def game():
    return render_template('game.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)