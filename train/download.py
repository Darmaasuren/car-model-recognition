from roboflow import Roboflow
rf = Roboflow(api_key="6uzNZk1NMP0p7y5Yc9rl")
project = rf.workspace("training-pfqzf").project("car_model_recognition-amloc")
version = project.version(1)
dataset = version.download("multiclass")
                