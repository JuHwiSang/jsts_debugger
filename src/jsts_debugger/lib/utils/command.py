def is_script_finished_command(command: str) -> bool:
    """
    Check if the given command indicates that the script has finished executing.
    
    Args:
        command (str): The command to check
        
    Returns:
        bool: True if the command indicates script completion, False otherwise
    """
    script_finished_commands = {
        "Inspector.detached",
        "Runtime.executionContextDestroyed"
    }
    return command in script_finished_commands

def is_debugger_paused_command(command: str) -> bool:
    """
    Check if the given command indicates that the debugger has paused.
    """
    return command == "Debugger.paused"

def is_debugger_resumed_command(command: str) -> bool:
    """
    Check if the given command indicates that the debugger has resumed.
    """
    return command == "Debugger.resumed"

def is_command_to_ignore(command: str) -> bool:
    """
    Check if the given command should be ignored.
    """
    return command == "Debugger.scriptParsed"


def is_program_run_command(command: str) -> bool:
    """
    Check if the given command is one that runs/continues program execution.
    
    Args:
        command (str): The command to check
        
    Returns:
        bool: True if the command runs/continues program execution, False otherwise
    """
    run_commands = {
        "Debugger.resume",
        "Debugger.stepInto", 
        "Debugger.stepOut",
        "Debugger.stepOver",
    }
    return command in run_commands

def is_command_may_run(command: str) -> bool:
    """
    Check if the given command may potentially run/continue program execution.
    
    Args:
        command (str): The command to check
        
    Returns:
        bool: True if the command may run program execution, False otherwise
    """
    may_run_commands = {
        "Runtime.runIfWaitingForDebugger",
        "Debugger.setSkipAllPauses",
    }
    return command in may_run_commands
