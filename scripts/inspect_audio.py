import wave


def inspect_audio(file_path: str) -> None:
    with wave.open(file_path, "rb") as f:
        print(f"File: {file_path}")
        print(f"Sample rate: {f.getframerate()} Hz")
        print(f"Channels: {f.getnchannels()}")
        print(f"Bit depth: {f.getsampwidth() * 8} bits")
        print(f"Duration: {f.getnframes() / f.getframerate()} seconds")
        print(f"Total samples: {f.getnframes()}")
        print(
            f"Chunk sizes (20ms frames): {f.getframerate() / 50} samples / {f.getframerate() / 50 * f.getsampwidth() * f.getnchannels()} bytes"
        )


if __name__ == "__main__":
    inspect_audio("data/harvard.wav")
