def read_file(file, result):
    with open(file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            result.append(line)
    return result