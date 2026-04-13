import os
import re

directories = ['src', 'scripts', 'tests']

for root_dir in directories:
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if not filename.endswith('.py'):
                continue
            fp = os.path.join(dirpath, filename)
            with open(fp, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Massive blunt-force string replacement for the test suite referencing main
            content = content.replace("from main import", "from scripts.run_main import")
            content = content.replace("import main\n", "from scripts import run_main as main\n")
            
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(content)
