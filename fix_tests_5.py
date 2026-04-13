import os
import re

directories = ['tests', 'decision_terminal']
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
                # from pkg import -> from src.miniqs.pkg import
                content = re.sub(rf'^(\s*from\s+){pkg}\b', rf'\1src.miniqs.{pkg}', content, flags=re.MULTILINE)
                # import pkg -> import src.miniqs.pkg as pkg
                content = re.sub(rf'^(\s*import\s+){pkg}\b(.*)$', rf'\1src.miniqs.{pkg} as {pkg}\2', content, flags=re.MULTILINE)
                
                # Mock patching inside strings: e.g. patch("runners.paper.xxx") -> patch("src.miniqs.runners.paper.xxx")
                content = re.sub(rf'([\'\"]){pkg}\b', rf'\1src.miniqs.{pkg}', content)
            
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(content)
