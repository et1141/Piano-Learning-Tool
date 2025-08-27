# Piano Learning Tool 
 The main functionality of the application is the transcription of arbitrary musical pieces into the MIDI format using artificial intelligence methods (including Transkun and Basic Pitch). A user, having only an audio file or a link to an online recording (e.g., from YouTube), can generate an animation visu- alizing a piano keyboard during playback, change the key, and export the piece in MIDI, MusicXML, or as sheet music in PDF format. The application was developed in a client–server architecture: the backend is implemented in Python with the Flask framework , while the frontend is built with HTML/CSS/JavaScript. The project makes use of several libraries, including synthviz, music21, and partitura.




## Option 1: Run with Docker

### Clone the Repository
```bash
git clone https://github.com/et1141/piano-audio-to-midi
cd piano-audio-to-midi
```

### Build Docker image
```bash
docker build -t piano-learning-app .
```


### Run container
```bash
docker run -d -p 8000:8000 piano-learning-app
```


The server will be available at:  
`http://localhost:8000`

To access the application, open `index.html` in the browser or simply go to:  
`http://localhost:8000`



## Option 2: Manual installation

### Clone the Repository
```bash
git clone https://github.com/et1141/piano-audio-to-midi
cd piano-audio-to-midi
```

### Install required system packages

Make sure you have the following installed **outside of Python**:
- **FFmpeg** — used by Synthviz to generate video:
- **Timidity** — used by Synthviz to synthesize audio from MIDI:
- **LilyPond** - used by music21 to generate pdf music sheet:

  - macOS: `brew install ffmpeg timidity lilypond`
  - Ubuntu: `sudo apt install ffmpeg timidity lilypond`

### Install pyenv (macOS)
```bash
brew install pyenv
```

### Configure pyenv in shell
```bash
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init --path)"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
```

#### Reload terminal
```bash
source ~/.bashrc
```

### Install Python 3.10(basic pitch doesn't work with later versions on Macbook)

```bash
pyenv install 3.10.5
```

### Set local Python version
```bash
pyenv local 3.10.5
```

### Create and Activate Virtual Environment
```bash
python -m venv piano-env
source piano-env/bin/activate
```
Double check if you have python 3.10.5 installed! 
```bash
python --version
```
### Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Run the Backend (Flask)
```bash
python backend_server.py
```
The server will be available at http://localhost:8000.

### Done
To access the application, open `index.html` in the browser or simply go to:  
`http://localhost:8000` address.  





## Share the app via Internet
If you want to expose the app over the Internet, use [ngrok](https://ngrok.com/):
```bash
ngrok http 8000
```

This will generate a public HTTPS link redirecting traffic to your local server.

---