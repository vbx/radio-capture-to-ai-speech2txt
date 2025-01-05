#!/usr/bin/env python3
import whisper
import warnings
import os
import threading
import socket
import numpy
import mmap
import typer
import struct
import sys

file = None
lock = threading.Lock()

def tcp_receiver(server, port):
    '''
    Read data on socket and write into file
    '''
    print(f'Listening to {server}:{port} ...', flush=True,end='')
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((server, port))
    server_socket.listen(1)
    client_socket, client_address = server_socket.accept()
    print(f"connected with {client_address} !")
    print()
    while True:
        data = client_socket.recv(4096)
        with lock:
            write_header()
            file.write(data)
            file.flush()

def write_header(is_empty=False):
    num_channels = 1
    sample_rate = 16000
    bits_per_sample = 16
    data_size = 0 if is_empty else os.fstat(file.fileno()).st_size - 44
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    wav_header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',                          # ChunkID (4 octets)
        4 + data_size,                    # Taille totale du fichier without RIFF
        b'WAVE',                          # Format (4 octets)
        b'fmt ',                          # Subchunk1ID (4 octets)
        16,                               # Subchunk1Size (4 octets) = 16 pour PCM
        1,                                # AudioFormat (2 octets) = 1 pour PCM
        num_channels,                     # NumChannels (2 octets)
        sample_rate,                      # SampleRate (4 octets)
        byte_rate,                        # ByteRate (4 octets)
        block_align,                      # BlockAlign (2 octets)
        bits_per_sample,                  # BitsPerSample (2 octets)
        b'data',                          # Subchunk2ID (4 octets)
        data_size                         # Subchunk2Size (4 octets)
    )
    if is_empty:
        file.write(wav_header)
        file.flush()
        return

    last_position = file.tell()
    file.seek(0)
    file.write(wav_header)
    file.seek(last_position)
    file.flush()

def audio_transcriber(whisper, model, language, tempo):
    start_position = 44 # without header
    previous_txt_len = 0
    while True:
        threading.Event().wait(tempo)
        with lock:
            # Empty file ?
            if os.fstat(file.fileno()).st_size <= 44:
                continue
            file.seek(start_position)
            data = file.read()

        # buffer size must be a multiple of 2
        if len(data) % 2 != 0:
            data = data[:-1]

        # Load, convert to float32 and normalisation
        audio = numpy.frombuffer(data, dtype=numpy.int16)
        audio = audio.astype(numpy.float32) / 32768.0

        result = whisper.transcribe(model, audio,
            condition_on_previous_text=True,
            word_timestamps=True,
            language=language,
            no_speech_threshold=0.5,
            logprob_threshold=-0.5,
            hallucination_silence_threshold=0.7,
            temperature=0.2
            )

        text = result['segments'][0]['text']
        sys.stdout.write(f"\r>>>>{text}")
        sys.stdout.flush()
        if len(result['segments']) > 1:
            print(flush=True)
            start_position += sec_to_bytes(result['segments'][1]['start'])
            #print("start_position="+str(start_position))
            #print(flush=True)


def bytes_to_sec(len_payload):
    return float(len_payload/16000/2)
def sec_to_bytes(second):
    return int(second*16000*2)

def main(server: str = "0.0.0.0", port: int = 12345,
            model: str = "turbo", language: str = None,
            tempo: float = 0.5):

    print(f"Loading whisper `{model}` model...", end='', flush=True)
    warnings.filterwarnings("ignore", category=FutureWarning)
    model = whisper.load_model(model)
    print(f"Done !")

    global file
    file = open('audio.wav', 'w+b')
    write_header(is_empty=True)

    try:
        thread1 = threading.Thread(target=tcp_receiver, args=(server, port))
        thread2 = threading.Thread(target=audio_transcriber, args=(whisper, model, language, tempo))

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()
    finally:
        file.close()

if __name__ == "__main__":
    """
    CLI program that captures audio data from a TCP socket and transcribes it
    in near real-time using Whisper.

    This program is designed to receive a continuous audio stream through a
    TCP socket and use the Whisper model to transcribe the audio into text
    in near real-time. The transcription happens as the audio data is received,
    allowing for rapid and real-time interaction with the audio input.

    Test example from wav file:
    python transcribe.py --server 127.0.0.1 --port 12345 --language fr
    ffmpeg -re -stream_loop -1 -i input_file.wav -ar 16000 -ac 1 -sample_fmt s16 -f wav tcp://127.0.0.1:12345
    """
    typer.run(main)
