import re

_POLITE_PREFIX = re.compile(r"^(?:(?:please|can you|could you|would you|hey hina|hina)[ ,]+)+")
_MY = re.compile(r"\bmy\b\s*")
_FIND = re.compile(r"^(?:find|locate)\b")


def _drop_my(text):
    return _MY.sub("", text).strip()


def normalize_command(command):
    command = command.lower().strip()
    command = _POLITE_PREFIX.sub("", command).strip()

    if command.endswith(" mode"):
        mode_name = command[:-len(" mode")].strip()
        if mode_name:
            return "mode " + mode_name

    file_extensions = [
        ".pdf", ".txt", ".py", ".docx", ".doc",
        ".pptx", ".ppt", ".jpg", ".jpeg", ".png",
        ".mp3", ".mp4", ".csv", ".xlsx", ".exe"
    ]

    # Time / system info
    if command in ["time", "tell time"]:
        return "tell time"

    elif command in ["date", "tell date"]:
        return "tell date"

    elif command == "battery":
        return "battery"

    elif command == "disk usage":
        return "disk usage"

    # Calculator
    elif command.startswith("calculate "):
        expr = command.split("calculate ", 1)[1]
        return "calculate " + expr

    # Conversation
    elif command in ["hello", "hi", "hey"]:
        return "hello"

    elif "who are you" in command:
        return "who are you"

    elif "how are you" in command:
        return "how are you"

    elif "thanks" in command or "thank you" in command:
        return "thanks"

    elif "what can you do" in command:
        return "what can you do"

    elif "what do you think" in command:
        return "what do you think"

    elif "i'm tired" in command or "im tired" in command or "i am tired" in command:
        return "im tired"

    elif "tell me something" in command or "say something" in command:
        return "tell me something"

    # File / folder search
    elif _FIND.match(command) and re.search(r"\bfolder\b", command):
        folder_name = _drop_my(re.sub(r"\bfolder\b", "", _FIND.sub("", command, count=1)))
        return "find folder " + folder_name

    elif _FIND.match(command):
        file_name = _drop_my(_FIND.sub("", command, count=1))
        file_name = re.sub(r"^file\s+", "", file_name)
        return "find file " + file_name

    # App controls
    elif command.startswith("launch "):
        target = _drop_my(command[len("launch "):])
        return "open " + target

    elif command.startswith("close "):
        target = _drop_my(command[len("close "):])
        return "close " + target

    elif command.startswith("restart "):
        target = _drop_my(command[len("restart "):])
        return "restart " + target

    # Smart open handling
    elif command.startswith("open "):
        target = _drop_my(command[len("open "):])

        if any(ext in target for ext in file_extensions):
            return "open file " + target

        return "open " + target

    elif command.startswith("my name is "):
        name = command.replace("my name is ", "").strip()
        return "set name " + name
    elif command.startswith("favorite app "):
        return command
    
    # Web search - ChatGPT
    elif "search" in command and "in chatgpt" in command:
        query = (
            command.replace("search", "")
            .replace("in chatgpt", "")
            .replace("about", "")
            .strip()
        )
        return "search chatgpt " + query
    
    elif command.startswith("ask chatgpt about "):
        query = command.replace("ask chatgpt about ", "").strip()
        return "search chatgpt " + query
    
    # Web search - Google
    elif command.startswith("search "):
        query = command.replace("search ", "").strip()
        return "search google " + query
    
    elif command.startswith("google "):
        query = command.replace("google ", "").strip()
        return "search google " + query
    
    return command