The project involves the practical part of my final bachelor thesis, where I created a tool to help with learning to play the piano. The main objective of the project is to convert an audio file into a MIDI file. The goal is to build and train my own model (possibly inspired by the Transkun model) while also providing the option to use other existing models, like Spotify’s Basic Pitch.

# Piano Learning Tool — Setup Guide


## Clone the Repository
```bash
git clone https://github.com/et1141/piano-audio-to-midi
cd piano-audio-to-midi
```

## Install pyenv (macOS)
```bash
brew install pyenv
```

## Configure pyenv in shell
```bash
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init --path)"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
```

## Reload terminal
```bash
source ~/.bashrc
```

## Install Python 3.10
```bash
pyenv install 3.10.13
```

## Set local Python version
```bash
pyenv local 3.10.13
```

## Create and Activate Virtual Environment
```bash
python -m venv piano-env
source piano-env/bin/activate
```

## Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install "basic-pitch[all]"
```

## Run the Backend (Flask)
```bash
python backend_server.py
```
Backend will be available at `http://localhost:8000`.

## Open the Frontend
Open `index.html` in your browser and upload an audio file. A download link for the converted MIDI file will appear after conversion.

## Done 🎶
Your project is ready! Let me know if you hit any snags. 🚀


## Folder Structure
```
project-root/
├── piano-env/           # Virtual environment (ignored by Git)
├── uploads/            # Uploaded audio files
├── midi/               # Generated MIDI files
├── backend_server.py   # Flask backend
├── index.html          # Frontend
├── requirements.txt    # Python dependencies
└── .gitignore          # Ignored files
```

## Troubleshooting
**Flask not installed:**
```bash
pip install flask
```

**"No file uploaded" error:**
Ensure you're selecting a valid audio file (like `.wav` or `.mp3`).

**Server not responding:**
Make sure Flask server is running and the frontend points to `http://localhost:8000`.

