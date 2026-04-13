import os
import glob
import re

directories = ['src', 'scripts', 'tests']
old_packages = ['config', 'data', 'engine', 'execution', 'risk', 'runners', 'signals', 'strategies', 'utils']

for root_dir in directories:
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if not filename.endswith('.py'):
                continue
            fp = os.path.join(dirpath, filename)
            with open(fp, 'r', encoding='utf-8') as f:
                content = f.read()

            for pkg in old_packages:
                content = re.sub(rf'^(\s*from\s+){pkg}\b', rf'\1src.miniqs.{pkg}', content, flags=re.MULTILINE)
                content = re.sub(rf'^(\s*import\s+){pkg}\b(.*)$', rf'\1src.miniqs.{pkg} as {pkg}\2', content, flags=re.MULTILINE)
            
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(content)
