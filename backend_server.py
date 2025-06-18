from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import os
import subprocess
import numpy as np
from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH
from mido import MidiFile
from synthviz import create_video
import json
import re
import yt_dlp
from music21 import converter, key

import sqlite3





app = Flask(__name__)
CORS(app) # Let any domain to access API


DB_PATH = 'songs.db'
UPLOAD_FOLDER = 'uploads'
MIDI_FOLDER = 'midi'
VIDEO_FOLDER = 'videos'
SONGS_JSON = 'songs.json'


os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MIDI_FOLDER, exist_ok=True)
os.makedirs(VIDEO_FOLDER, exist_ok=True)

######################################## Database functions  ########################################

def get_db_connection(): 
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # by móc używać dict-like results
    return conn

######################################## CREATE

def add_new_song(user_id,title,audio_path,youtube_url=''):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''INSERT INTO songs (user_id,title,audio_path,source) VALUES (?, ?, ?,?)
                ''',(user_id,title,audio_path,youtube_url))
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


######################################## READ

def get_song(song_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM songs where id = ?',(song_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return row
    else:
        return None #TODO

def get_song_version(song_version_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM song_versions WHERE id = ?',(song_version_id,))
    row = cur.fetchone() 
    conn.close()
    if row:
        return row
    else:
        return None #TODO 

def get_table(table):
    if not table.isidentifier():
        raise ValueError("Invalid table name")  # zabezpieczenie przed SQL injection
    conn = get_db_connection()
    cur = conn.cursor()
    query = f'SELECT * FROM {table}'
    cur.execute(query)
    rows = cur.fetchall()
    conn.close()
    return rows    


######################################## UPDATE
def update_song_version(song_version_id, **kwargs):
    if not kwargs:
        return  # nic do aktualizacji

    fields = ', '.join(f"{key} = ?" for key in kwargs)
    values = list(kwargs.values())
    values.append(song_version_id)  # dodaj ID na końcu do WHERE

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f'''
        UPDATE song_versions
        SET {fields}
        WHERE id = ?
    ''', values)
    conn.commit()
    conn.close()



######################################## DELETE



########################################################################################################################

def safe_filename_song(title):
    title = title.replace(' ', '_')  
    title = re.sub(r'[^a-zA-Z0-9_\-\.]', '', title)  
    return title

def safe_filename_version(title,model_name,key_root,key_mode):
    title = title.replace(' ', '_')  
    title = re.sub(r'[^a-zA-Z0-9_\-\.]', '', title)  
    return f"{title}_{model_name}_{key_root}_{key_mode}"

def load_song_data():
    if not os.path.exists(SONGS_JSON):
        return {"songs": []}
    with open(SONGS_JSON, 'r') as f:
        return json.load(f)

def save_song_data(data):
    with open(SONGS_JSON, 'w') as f:
        json.dump(data, f, indent=2)


def transkun_predict(audio_path,midi_path):

    try:
        subprocess.run(['transkun', audio_path, midi_path], check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Transkun failed: {e}")

    return midi_path

def get_instrument(score):
    instruments = list(score.recurse().getElementsByClass('Instrument'))
    # Wybierz pierwszy niepusty instrument
    instrument_name = None
    for inst in instruments:
        name = inst.instrumentName or inst.bestName()
        if name:
            instrument_name = name
            break

    if instrument_name:
        print(f"Instrument {instrument_name}")
    else:
        instrument_name = "Unknown"
        print("No instrument found — (saved as Unknown")
    return instrument_name



@app.route('/api/get-midi-files', methods=['GET'])
def get_midi_files():
    files = [f for f in os.listdir(MIDI_FOLDER) if f.endswith('.mid')]
    return jsonify(files)



@app.route('/api/upload-audio', methods=['POST'])
def upload_audio():
    if 'audio_file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    audio_file = request.files['audio_file']
    if audio_file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    user_id = 1 # TODO po zalogowaniu dynamicznie dodawany user
    title = audio_file.filename #TODO dodaj funkcjonalnosc dawania tytulu - wtedy po prostu przekazuj tytul w request
    filename = safe_filename_song(title) + '.mp3'
    audio_path = os.path.join(UPLOAD_FOLDER, filename)
    audio_file.save(audio_path)


    song_id = add_new_song(user_id, title,audio_path) #TODO 1: dodaj picture path, po logowaniu: 
    return jsonify({'song_id': song_id}), 200 


@app.route('/api/download-upload-audio', methods=['POST'])
def download_audio_yt_dlp():
    data = request.get_json()
    user_id = 1 # TODO po zalogowaniu dynamicznie dodawany user
    youtube_url = data.get('youtube_url')

    if not youtube_url:
        return jsonify({'error': 'Missing YouTube URL'}), 400

    try:
        # download data (without audio - just to get the title)
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl_info:
            info = ydl_info.extract_info(youtube_url, download=False)
        
        video_title = info.get('title', 'unknown_title')
        title = safe_filename_song(video_title) 
        audio_path = os.path.join(UPLOAD_FOLDER, title) # without '.mp3' at the end because yt-dlp adds it 

        # Ściągnij i przekonwertuj na MP3
        ydl_opts = {
            'format': 'bestaudio',
            'outtmpl': audio_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
            }],
            'quiet': True,
            'noplaylist': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
        

        song_id = add_new_song(user_id, title,audio_path+'.mp3',youtube_url) #TODO 1: dodaj picture path, po logowaniu: 

        return jsonify({'song_id': song_id}), 200

    except Exception as e:
        print("YouTube download error:", e)
        return jsonify({'error': str(e)}), 500
    


@app.route('/api/convert-audio', methods=['POST'])
def convert_audio():
    # Prepare data
    model_name = request.form.get('model_name', 'transkun') # transkun is the default model
    song_id = request.form.get('song_id')
    song = get_song(song_id)
    if not song:
        return jsonify({'error: Song not found'})
    
    title = song['title']
    audio_path = song['audio_path']

    temp_midi_filename = f"temp_{song_id}_{model_name}.mid"
    temp_midi_path = os.path.join(MIDI_FOLDER, temp_midi_filename)

    # Audio to MIDI conversion     
    if model_name == 'transkun':
        #midi_path = transkun_predict(song_id,midi_path) # transkun saves midi_data!
        transkun_predict(audio_path,temp_midi_path) 
    else: 
        model_output, midi_data, note_events = predict(audio_path, model_or_model_path=ICASSP_2022_MODEL_PATH)
        midi_data.write(temp_midi_path)

    # Song metadata analysis
    score = converter.parse(temp_midi_path)
    key_signature_data = score.analyze('key')
    print(f"Tonacja: {key_signature_data.tonic.name} {key_signature_data.mode}")
    key_root = key_signature_data.tonic.name
    key_mode = key_signature_data.mode
    #duration_quarterLen = score.duration.quarterLength  # liczba ćwierćnut
    #duration = score.duration.seconds 
    instrument = get_instrument(score)

    # Rename midi file and save to database 
    filename=safe_filename_version(title,model_name,key_root,key_mode) 
    midi_path = os.path.join(MIDI_FOLDER, f"{filename}.mid")
    song_version_id = add_new_song_version(song_id,model_name,key_root,key_mode,instrument,filename,midi_path)
    os.rename(temp_midi_path, midi_path)


    return jsonify({'title': title, 'song_version_id': song_version_id}), 200




def generate_video(song_version_id):
    song_version = get_song_version(song_version_id)
    midi_path = song_version['midi_path']

    if not os.path.exists(midi_path):
        return jsonify({'error': 'MIDI file not found'}), 404 #TODO convert audio to midi

    video_filename = song_version['filename'] + '.mp4'
    new_video_path = os.path.join(VIDEO_FOLDER, video_filename)
    
    create_video(input_midi=midi_path, video_filename=new_video_path)
    update_song_version(song_version_id, video_path=new_video_path)



@app.route('/api/get-video', methods=['POST'])
def get_video():
    data = request.get_json()
    song_version_id = data.get('song_version_id')
    song_version = get_song_version(song_version_id)

    if not song_version:
        return jsonify({'error': 'Song version not found'}), 404

    video_path = song_version['video_path']
    if not video_path or not os.path.exists(video_path):
        try:
            generate_video(song_version_id)  # teraz to funkcja robi wszystko
        except Exception as e:
            return jsonify({'error': f'Failed to generate video: {str(e)}'}), 500
    
    video_url = f'http://localhost:8000/videos/{song_version_id}'
    return jsonify({'video_url': video_url})


@app.route('/videos/<song_version_id>', methods=['GET'])
def get_video_file(song_version_id):
    song_version = get_song_version(song_version_id)
    if not song_version:
        return jsonify({'error': 'Song version not found'}), 404
    
    video_path = song_version['video_path']
    if not video_path or not os.path.exists(video_path):
        return jsonify({'error': 'Video file not found'}), 404 #TODO
    
    return send_file(video_path)
        



@app.route('/midi/<filename>', methods=['GET'])
def get_midi_file(filename):
    return send_from_directory(MIDI_FOLDER, filename)





if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)