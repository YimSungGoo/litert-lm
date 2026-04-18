import datetime
import base64

def get_current_time() -> str:
    """Returns the current date and time."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

system_instruction = "You are a helpful assistant with access to tools."
tools = [get_current_time]
