from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import numpy as np
from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH
from mido import MidiFile



app = Flask(__name__)
CORS(app) # Let any domain to access API

UPLOAD_FOLDER = 'uploads'
MIDI_FOLDER = 'midi'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MIDI_FOLDER, exist_ok=True)

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)
