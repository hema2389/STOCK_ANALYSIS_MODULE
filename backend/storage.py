import json, os

def save(path, data):
    with open(path, 'w') as f:
    json.dump(data, f)


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)