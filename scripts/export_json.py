import json
import os

CONFIG_DIR = '/etc/wireguard'
OUTPUT_FILE = 'wg_config_export.json'


def export_configs():
    data = {}
    if os.path.isdir(CONFIG_DIR):
        for name in os.listdir(CONFIG_DIR):
            path = os.path.join(CONFIG_DIR, name)
            if os.path.isfile(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data[name] = f.read()
    # additional files in repo root
    for extra in ['cofigs.txt', os.path.join('scripts', 'variables.sh')]:
        if os.path.isfile(extra):
            with open(extra, 'r', encoding='utf-8') as f:
                data[extra] = f.read()
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return OUTPUT_FILE


if __name__ == '__main__':
    print(export_configs())
