import json
import os
import subprocess

CONFIG_DIR = '/etc/wireguard'
INPUT_FILE = 'wg_config_export.json'


def update_endpoint(path, ip):
    lines = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith('Endpoint'):  # update only Endpoint line
                lines.append(f'Endpoint = {ip}:51830\n')
            else:
                lines.append(line)
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)


def import_configs(json_path=INPUT_FILE):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    os.makedirs(CONFIG_DIR, exist_ok=True)
    for name, content in data.items():
        if name == 'cofigs.txt':
            dest = 'cofigs.txt'
        elif name.endswith('variables.sh'):
            dest = os.path.join('scripts', 'variables.sh')
        else:
            dest = os.path.join(CONFIG_DIR, name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'w', encoding='utf-8') as f_out:
            f_out.write(content)

    # determine new public ip
    try:
        ip_address = subprocess.check_output(['curl', '-s', '-4', 'ifconfig.me'], text=True).strip()
    except Exception:
        ip_address = ''

    if ip_address:
        var_path = os.path.join('scripts', 'variables.sh')
        if os.path.isfile(var_path):
            lines = []
            with open(var_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('ip_address_glob='):
                        continue
                    lines.append(line)
            lines.append(f'ip_address_glob={ip_address}\n')
            with open(var_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)

        # update client configs
        for name in data.keys():
            if name.endswith('_cl.conf'):
                update_endpoint(os.path.join(CONFIG_DIR, name), ip_address)
    return True


if __name__ == '__main__':
    import_configs(INPUT_FILE)
