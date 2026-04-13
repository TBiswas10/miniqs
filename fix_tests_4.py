import os
import re

directories = ['tests', 'scripts', 'decision_terminal']

replacements = {
    "import event_driven_pipeline": "from scripts import run_event_pipeline as event_driven_pipeline",
    "import backtest": "from scripts import run_backtest as backtest",
    "import stress_testing": "from scripts import run_stress_testing as stress_testing",
    "import execute_validation_pipeline": "from scripts import execute_validation_pipeline",
    "import p0_validation": "from scripts import p0_validation",
    "import quant_control_state": "from src.miniqs.risk import quant_control_state",
    "from p0_validation import": "from tests.p0_validation import",
    "from backtest import": "from scripts.run_backtest import",
    "from event_driven_pipeline import": "from scripts.run_event_pipeline import",
    "from stress_testing import": "from scripts.run_stress_testing import"
}

for root_dir in directories:
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if not filename.endswith('.py'):
                continue
            fp = os.path.join(dirpath, filename)
            with open(fp, 'r', encoding='utf-8') as f:
                content = f.read()
            
            for old, new in replacements.items():
                content = content.replace(old, new)
                
            # Extra catch for 'import quant_control_state as ...'
            content = content.replace("import quant_control_state as", "from src.miniqs.risk import quant_control_state as")
            
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(content)
