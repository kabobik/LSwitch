import json
import time
import os
import threading
from lswitch.intelligence.user_dictionary import UserDictionary

path = "test_reload_dict.json"
if os.path.exists(path):
    os.remove(path)

# Prepare initial data
with open(path, "w") as f:
    json.dump({"words": {"ru:кот": 5}}, f)
    
f_time = os.path.getmtime(path)
os.utime(path, (f_time - 10, f_time - 10))

# Instantiate
u = UserDictionary(path)
print("Initial weight", u.get_weight("кот", "ru"))

def update_file():
    time.sleep(1)
    # Simulate writing another config manually
    with open(path, "w") as f:
        json.dump({"words": {"ru:кот": 10}}, f)
    print("Test: Wrote updated json")

t = threading.Thread(target=update_file)
t.start()
print("Wait 3 seconds for it to pick up")
for _ in range(6):
    time.sleep(0.5)
    print("Checking weight:", u.get_weight("кот", "ru"))

if os.path.exists(path):
    os.remove(path)
