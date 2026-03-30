"""Demo contestant script that allocates memory until it is terminated."""

payload = []

while True:
    payload.append(bytearray(8 * 1024 * 1024))
