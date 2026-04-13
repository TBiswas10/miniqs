import os
import glob

scripts_dir = r'scripts'
code_to_add = "import sys\nimport os\nsys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))\n"

for fp in glob.glob(os.path.join(scripts_dir, '*.py')):
    with open(fp, 'r') as f:
        content = f.read()
    
    # Remove previous faulty prepend if it exists
    if content.startswith(code_to_add):
        content = content[len(code_to_add):]
        
    lines = content.split('\n')
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('from __future__') or line.startswith('\"\"\"'):
            # simple heuristic: put after docstring or future imports
            insert_idx = i + 1
            if line.startswith('\"\"\"') and content.count('\"\"\"') > 1:
               # basic docstring skip
               insert_idx = i + 2 # not perfect but we inject after 2 for multi
               
    # Let's just do a simpler trick: find the first line that is imports NOT from __future__
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            if not line.startswith('from __future__'):
                insert_idx = i
                break
    
    lines.insert(insert_idx, "import sys\nimport os\nsys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))\n")
    
    with open(fp, 'w') as f:
        f.write('\n'.join(lines))
