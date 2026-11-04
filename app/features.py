# Columns the model learns from, in this order. Shared by train.py and main.py:
# if the two lists differed (even in order), the model would get wrong inputs without any error.
FEATURES = ["peltier_temp", "ambient_temp", "fan_rpm"]
