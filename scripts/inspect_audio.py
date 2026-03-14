import wave


def inspect_audio(file_path: str) -> None:
    with wave.open(file_path, "rb") as f:
        print(f"File: {file_path}")
        print(f"Sample rate: {f.getframerate()} Hz")
        print(f"Channels: {f.getnchannels()}")
        print(f"Bit depth: {f.getsampwidth() * 8} bits")
        print(f"Duration: {f.getnframes() / f.getframerate()} seconds")
        print(f"Total samples: {f.getnframes()}")
        samples = f.getframerate() / 50
        chunk_bytes = samples * f.getsampwidth() * f.getnchannels()
        print(f"Chunk sizes (20ms frames): {samples} samples / {chunk_bytes} bytes")


if __name__ == "__main__":
    inspect_audio("data/harvard.wav")
