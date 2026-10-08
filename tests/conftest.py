import os

os.environ["LLM_PROVIDER"] = "mock"  # tests never call a real model
