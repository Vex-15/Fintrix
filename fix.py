import sys

path = 'backend/app/utils/synthetic_data.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('"balance": ""', '"balance": None')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed balance")
