import os

fp = r'src\miniqs\engine\event_bus.py'
with open(fp, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    new_lines.append(line)
    if 'class MarketEvent(BaseModel):' in line:
        new_lines.append('    model_config = {"arbitrary_types_allowed": True}\n')

with open(fp, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
