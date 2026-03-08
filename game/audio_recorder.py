import os
import time
import threading
import queue
import datetime

try:
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
    import whisper
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("WARNING: Audio dependencies missing. Please install sounddevice, soundfile, openai-whisper, numpy")

class AudioRecorder:
    def __init__(self):
        self.session_dir = None
        self.is_recording = False
        self.audio_queue = queue.Queue()
        self.stream = None
        self.model = None
        self.samplerate = 16000
        self.channels = 1
        self.enabled = False
        self.start_time = None
        self.start_datetime = None
        self.turn_markers = [] # list of (datetime_obj, turn_number)
        self.game_timestamp = None

        if AUDIO_AVAILABLE:
            # Load the whisper model asynchronously to avoid blocking
            threading.Thread(target=self._load_model, daemon=True).start()

    def _load_model(self):
        try:
            print("Loading Whisper model (this may take a moment)...")
            # "base" model is a good tradeoff for speed and accuracy
            self.model = whisper.load_model("base")
            print("Whisper model loaded successfully.")
        except Exception as e:
            print(f"Failed to load Whisper model: {e}")

    def init_session(self):
        if not self.enabled:
            return
        self.game_timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        recordings_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "recordings")
        if not os.path.exists(recordings_dir):
            os.makedirs(recordings_dir)
        self.session_dir = os.path.join(recordings_dir, f"{self.game_timestamp}_game")
        os.makedirs(self.session_dir, exist_ok=True)
        self.turn_markers = []
        print(f"Audio session initialized at {self.session_dir}")

    def start_recording(self):
        """Starts a continuous recording for the whole game duration."""
        if not self.enabled or not AUDIO_AVAILABLE or not self.session_dir:
            return
        if self.is_recording:
            return
            
        self.is_recording = True
        self.audio_queue = queue.Queue()
        self.start_time = time.time()
        self.start_datetime = datetime.datetime.now()
        self.turn_markers = []
        
        def audio_callback(indata, frames, time_info, status):
            if status:
                print(status)
            self.audio_queue.put(indata.copy())
            
        try:
            self.stream = sd.InputStream(samplerate=self.samplerate, channels=self.channels, callback=audio_callback)
            self.stream.start()
            print(f"Started continuous audio recording")
        except Exception as e:
            print(f"Failed to start audio recording: {e}")
            self.is_recording = False

    def mark_turn(self, turn_number):
        """Records the elapsed time when a new turn starts."""
        if not self.is_recording or self.start_datetime is None:
            return
        dt_now = datetime.datetime.now()
        self.turn_markers.append((dt_now, turn_number))
        print(f"Audio marked Turn {turn_number} at {dt_now.strftime('%H:%M:%S')}")

    def stop_recording(self):
        """Stops the continuous recording, saves it, and triggers transcription."""
        if not self.is_recording or not self.stream:
            return
            
        self.is_recording = False
        self.stream.stop()
        self.stream.close()
        self.stream = None
        
        # Pull all audio from queue
        audio_data = []
        while not self.audio_queue.empty():
            audio_data.append(self.audio_queue.get())
            
        if not audio_data:
            return
            
        audio_np = np.concatenate(audio_data, axis=0)
        
        if not self.session_dir:
            return
            
        # Save to file
        filename = f"{self.game_timestamp}_full_game.wav"
        filepath = os.path.join(self.session_dir, filename)
        
        try:
            sf.write(filepath, audio_np, self.samplerate)
            print(f"Saved full game audio to {filepath}")
            
            # Trigger transcription with turn markers
            threading.Thread(target=self._transcribe, args=(filepath, self.turn_markers.copy()), daemon=False).start()
        except Exception as e:
            print(f"Failed to save audio file: {e}")

    def _transcribe(self, filepath, markers):
        if not self.model:
            print("Whisper model not loaded yet or failed to load. Skipping transcription.")
            return
            
        try:
            print(f"Transcribing {filepath}...")
            # Use 'fp16=False' to fix common PyTorch warnings/errors on some hardware
            result = self.model.transcribe(filepath, fp16=False)
            text_path = filepath.rsplit('.', 1)[0] + ".txt"
            
            with open(text_path, "w") as f:
                f.write("--- Game Transcription ---\n")
                
                events = []
                # Add turn markers to events
                for dt, turn_num in markers:
                    events.append({
                        "type": "turn",
                        "time": dt,
                        "text": f"\n[Turn {turn_num}]\n"
                    })
                    
                # Add spoken segments to events
                for segment in result.get('segments', []):
                    start = segment['start']
                    end = segment['end']
                    text = segment['text']
                    
                    segment_dt = self.start_datetime + datetime.timedelta(seconds=start)
                    
                    # Store relative start/end seconds instead of full timestamps just for formatting
                    events.append({
                        "type": "speech",
                        "time": segment_dt,
                        "text": f"[{start:.2f}s - {end:.2f}s] {text.strip()}\n"
                    })
                
                # Sort all events chronologically
                events.sort(key=lambda x: x["time"])
                
                # Write them out sequentially
                for event in events:
                    f.write(event["text"])
                    
            print(f"Saved transcription to {text_path}")
        except Exception as e:
            print(f"Transcription failed: {e}")
