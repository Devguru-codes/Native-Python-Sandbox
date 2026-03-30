"""A deliberately broken submission that allocates memory until killed."""

chunks = []

while True:
    chunks.append(bytearray(8 * 1024 * 1024))
