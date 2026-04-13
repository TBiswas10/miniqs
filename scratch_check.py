import sys
files = [
    r'tests\debug_test.py',
    r'tests\test_decision_terminal_explainability.py',
    r'tests\test_execute_validation_pipeline.py',
    r'tests\test_quant_control_state.py'
]
for f in files:
    print('--- ' + f + ' ---')
    try:
        with open(f, 'r') as file:
            lines = file.readlines()[:15]
            for line in lines:
                if 'import' in line:
                    print(line.strip())
    except Exception as e:
        print(e)
