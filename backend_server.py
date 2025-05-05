from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import numpy as np
from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH
from mido import MidiFile
from synthviz import create_video
import json
import re




app = Flask(__name__)
CORS(app) # Let any domain to access API

UPLOAD_FOLDER = 'uploads'
MIDI_FOLDER = 'midi'
VIDEO_FOLDER = 'videos'
SONGS_JSON = 'songs.json'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MIDI_FOLDER, exist_ok=True)
os.makedirs(VIDEO_FOLDER, exist_ok=True)




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

    file_path = os.path.join(UPLOAD_FOLDER, audio_file.filename)
    audio_file.save(file_path)

    # MIDI filename
    midi_filename = audio_file.filename.rsplit('.', 1)[0] + '.mid'
    midi_path = os.path.join(MIDI_FOLDER, midi_filename)

    # Audio -> Midi conversion using Basic Pitch: 
    model_output, midi_data, note_events = predict(file_path, model_or_model_path=ICASSP_2022_MODEL_PATH)
    midi_data.write(midi_path)

    midi_url = f"http://localhost:8000/midi/{midi_filename}"
    return jsonify({'midi_file': midi_url}), 200

@app.route('/midi/<filename>', methods=['GET'])
def get_midi_file(filename):
    return send_from_directory(MIDI_FOLDER, filename)



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


@app.route('/videos/<filename>', methods=['GET'])
def get_video_file(filename):
    return send_from_directory(VIDEO_FOLDER, filename)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)
