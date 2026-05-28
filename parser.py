def normalize_command(command):
    command = command.lower().strip()

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

    # File / folder search
    elif "find" in command and "folder" in command:
        folder_name = (
            command.replace("find", "")
            .replace("folder", "")
            .replace("my", "")
            .strip()
        )
        return "find folder " + folder_name

    elif "find" in command:
        file_name = (
            command.replace("find", "")
            .replace("my", "")
            .strip()
        )
        return "find file " + file_name

    # App controls
    elif command.startswith("launch "):
        target = command.replace("launch ", "").replace("my", "").strip()
        return "open " + target

    elif command.startswith("close "):
        target = command.replace("close ", "").replace("my", "").strip()
        return "close " + target

    elif command.startswith("restart "):
        target = command.replace("restart ", "").replace("my", "").strip()
        return "restart " + target

    # Smart open handling
    elif command.startswith("open "):
        target = command.replace("open ", "").replace("my", "").strip()

        if any(ext in target for ext in file_extensions):
            return "open file " + target

        return "open " + target

    elif command.startswith("my name is "):
        name = command.replace("my name is ", "").strip()
        return "set name " + name
    elif command.startswith("favorite app "):
        return command
    return command