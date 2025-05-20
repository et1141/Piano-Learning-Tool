from flask import Flask, request, jsonify, send_from_directory
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

################### vvvvvvvvvv Database functions vvvvvvvvvv ###################
def get_db_connection(): 
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # by móc używać dict-like results
    return conn

def get_song(song_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT audio_path FROM songs where id = ?',(song_id))
    row = cur.fetchone()
    conn.close()
    if row:
        return row
    else:
        return None
    
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

def print_user(user_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        print_user_row(row)
    else:
        print(f"[USER] No user found with ID: {user_id}")

def print_song(song_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT * FROM songs WHERE id = ?', (song_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        print_song_row(row)
    else:
        print(f"[SONG] No song found with ID: {song_id}")

def print_song_version(version_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT * FROM song_versions WHERE id = ?', (version_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        print_song_version_row(row)
    else:
        print(f"[VERSION] No song version found with ID: {version_id}")




def print_user_row(row):
    print(f"[USER] ID: {row['id']}, Username: {row['username']}")

def print_song_row(row):
    print(f"[SONG] ID: {row['id']}, User ID: {row['user_id']}, Title: {row['title']}")
    print(f"       Audio Path: {row['audio_path']}")
    print(f"       Picture Path: {row['picture_path']}")
    print(f"       Original Key: {row['original_key_signature']}")
    print(f"       Uploaded: {row['uploaded_date']}")

def print_song_version_row(row):
    print(f"[VERSION] ID: {row['id']}, Song ID: {row['song_id']}")
    print(f"          Model: {row['model_name']}, Key: {row['key_signature']}")
    print(f"          MIDI: {row['midi_path']}")
    print(f"          PDF: {row['pdf_path']}")
    print(f"          MusicXML: {row['musicxml_path']}")
    print(f"          Video: {row['video_path']}")
    print(f"          Created: {row['created_at']}")

def print_all_tables():
    conn = get_db_connection()
    cur = conn.cursor()

    print("=== USERS ===")
    cur.execute('SELECT * FROM users')
    users = cur.fetchall()
    for user in users:
        print_user_row(user)

    print("\n=== SONGS ===")
    cur.execute('SELECT * FROM songs')
    songs = cur.fetchall()
    for song in songs:
        print_song_row(song)

    print("\n=== SONG_VERSIONS ===")
    cur.execute('SELECT * FROM song_versions')
    versions = cur.fetchall()
    for version in versions:
        print_song_version_row(version)
    conn.close()

################### ^^^^^^^^^^ Database functions ^^^^^^^^^^ ###################



def safe_filename(name):
    name = name.replace(' ', '_')  
    name = re.sub(r'[^a-zA-Z0-9_\-\.]', '', name)  
    return name



def load_song_data():
    if not os.path.exists(SONGS_JSON):
        return {"songs": []}
    with open(SONGS_JSON, 'r') as f:
        return json.load(f)

def save_song_data(data):
    with open(SONGS_JSON, 'w') as f:
        json.dump(data, f, indent=2)


def transkun_predict(song_id,midi_path):
    song = get_song(song_id)

    try:
        subprocess.run(['transkun', song['audio_path']+'.mp3', midi_path], check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Transkun failed: {e}")

    return midi_path

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
    
    title = audio_file.filename #TODO dodaj funkcjonalnosc dawania tytulu - wtedy po prostu przekazuj tytul w request
    audio_path = os.path.join(UPLOAD_FOLDER, safe_filename(title))
    audio_file.save(audio_path)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
                INSERT INTO songs (user_id, title, audio_path)  
                VALUES (?,?,?)
                ''',(1,title,audio_path)) # TODO 1: dodaj picture path, po logowaniu: dynamicznie dodawany user
    song_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'song_id': song_id}), 200 


@app.route('/api/download-upload-audio', methods=['POST'])
def download_audio_yt_dlp():
    data = request.get_json()
    youtube_url = data.get('youtube_url')
    if not youtube_url:
        return jsonify({'error': 'Missing YouTube URL'}), 400

    try:
        # download data (without audio) just to get the title
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl_info:
            info = ydl_info.extract_info(youtube_url, download=False)
        
        video_title = info.get('title', 'unknown_title')
        title = safe_filename(video_title) 
        audio_path = os.path.join(UPLOAD_FOLDER, title) #yt-dlp will fill ext

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

        conn = get_db_connection()
        cur = conn.cursor()


        cur.execute('''INSERT INTO songs (user_id,title,audio_path) VALUES (?, ?, ?)
                    ''',(1,title,audio_path))# TODO 1: dodaj picture path, po logowaniu: dynamicznie dodawany user
        song_id = cur.lastrowid
        conn.commit()
        conn.close()

        return jsonify({'song_id': song_id}), 200

    except Exception as e:
        print("YouTube download error:", e)
        return jsonify({'error': str(e)}), 500
    


@app.route('/api/convert-audio', methods=['POST'])
def convert_audio():
    # MIDI filename
    model_name = request.form.get('model_name', 'transkun') # transkun is the default model
    song_id = request.form.get('song_id')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT title, audio_path FROM songs WHERE id = ?',(song_id))
    row = cur.fetchone()
    conn.close() #it may take a while to convert so i close the connection

    if not row:
        return jsonify({'error: Song not found'})
    
    title = row['title']
    audio_path =  row['audio_path']
    midi_filename = safe_filename(title) + '.mid'
    midi_path = os.path.join(MIDI_FOLDER, midi_filename)

    # Audio -> Midi conversion     
    if model_name == 'transkun':
        #midi_data = transkun_predict(song_id,midi_path) # transkun saves midi_data!
        transkun_predict(song_id,midi_path) 
    else: 
        model_output, midi_data, note_events = predict(audio_path, model_or_model_path=ICASSP_2022_MODEL_PATH)
        midi_data.write(midi_path)
    #midi_url = f"http://localhost:8000/midi/{midi_filename}"

    # Wczytaj plik MIDI
    score = converter.parse(midi_path)

    key_signature_data = score.analyze('key')
    print(f"Tonacja: {key_signature_data.tonic.name} {key_signature_data.mode}")
    key_signature = key_signature_data.tonic.name
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO song_versions (song_id,model_name,key_signature,midi_path) VALUES (?,?,?,?)',(song_id,model_name,key_signature,midi_path))
    #song_version_id = cur.lastrowid # TODO w przypadku gdy user ma wlaczana wersje, ze wyswietla wszystkie piosenki (kazda wersja jako osobny rekord), to to sie moze przydac: 
    conn.commit()
    conn.close()

    return jsonify({'title': title}), 200





@app.route('/api/generate-video', methods=['POST'])
def generate_video():
    data = request.get_json()
    midi_filename = data.get('midi_filename')

    if not midi_filename or not midi_filename.endswith('.mid'):
        return jsonify({'error': 'Invalid MIDI filename'}), 400

    midi_path = os.path.join(MIDI_FOLDER, midi_filename)
    if not os.path.exists(midi_path):
        return jsonify({'error': 'MIDI file not found'}), 404

    video_filename = midi_filename.rsplit('.', 1)[0] + '.mp4'
    video_path = os.path.join(VIDEO_FOLDER, video_filename)

    create_video(
        input_midi=midi_path,
        video_filename=video_path,
    )
    video_url = f'http://localhost:8000/videos/{video_filename}'
    return jsonify({'video_url': video_url})

@app.route('/midi/<filename>', methods=['GET'])
def get_midi_file(filename):
    return send_from_directory(MIDI_FOLDER, filename)


@app.route('/videos/<filename>', methods=['GET'])
def get_video_file(filename):
    return send_from_directory(VIDEO_FOLDER, filename)


if __name__ == '__main__':
    print_all_tables()
    app.run(debug=True, host='0.0.0.0', port=8000)