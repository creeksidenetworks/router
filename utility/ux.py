# Edgerouter/VyOS management scripts
# Copyright (c) 2024 Jackson Tong, Creekside Networks LLC.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""
UX Helper Functions for Terminal Output
Provides consistent styling for terminal output following the rocky-setup.sh style guide.
"""

import os
import sys

#===============================================================================
# Terminal Colors
#===============================================================================

class Colors:
    """ANSI color codes for terminal output"""
    RED     = '\033[31m'
    GREEN   = '\033[32m'
    YELLOW  = '\033[33m'
    BLUE    = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN    = '\033[36m'
    WHITE   = '\033[37m'
    BOLD    = '\033[1m'
    DIM     = '\033[2m'
    RESET   = '\033[0m'

# Check if terminal supports colors
def supports_color():
    """Check if the terminal supports color output"""
    if not hasattr(sys.stdout, 'isatty'):
        return False
    if not sys.stdout.isatty():
        return False
    if os.environ.get('TERM') == 'dumb':
        return False
    return True

# Disable colors if not supported
if not supports_color():
    for attr in dir(Colors):
        if not attr.startswith('_'):
            setattr(Colors, attr, '')

#===============================================================================
# Output Helper Functions
#===============================================================================

def print_header(title, width=60):
    """Print a section header with box border
    
    Args:
        title: The title to display in the header
        width: The width of the header box (default 60)
    """
    padding = (width - len(title) - 2) // 2
    print("")
    print(f"{Colors.CYAN}{'═' * width}{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.RESET}{' ' * padding}{Colors.BOLD}{title}{Colors.RESET}{' ' * (width - padding - len(title) - 2)}{Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}{'═' * width}{Colors.RESET}")

def print_step(step_num, title):
    """Print a step header
    
    Args:
        step_num: The step number (string or int), use empty string to omit
        title: The step title
    """
    print("")
    if step_num:
        print(f"{Colors.YELLOW}{step_num}{Colors.RESET} {Colors.BOLD}{title}{Colors.RESET}")
    else:
        print(f"{Colors.BOLD}{title}{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}")

def print_subtitle(title):
    """Print a subtitle for a section
    
    Args:
        title: The subtitle text to display
    """
    print("")
    print(f"  {Colors.CYAN}▸{Colors.RESET} {Colors.BOLD}{title}{Colors.RESET}")

def print_ok(message):
    """Print a success message with green checkmark
    
    Args:
        message: The success message to display
    """
    print(f"  {Colors.GREEN}✓{Colors.RESET} {message}")

def print_warn(message):
    """Print a warning message with yellow warning symbol
    
    Args:
        message: The warning message to display
    """
    print(f"  {Colors.YELLOW}⚠{Colors.RESET} {message}")

def print_error(message):
    """Print an error message with red X
    
    Args:
        message: The error message to display
    """
    print(f"  {Colors.RED}✗{Colors.RESET} {message}")

def print_info(message):
    """Print an info message with blue info symbol
    
    Args:
        message: The info message to display
    """
    print(f"  {Colors.BLUE}ℹ{Colors.RESET} {message}")

def print_dim(message):
    """Print a dimmed message
    
    Args:
        message: The message to display in dim text
    """
    print(f"{Colors.DIM}{message}{Colors.RESET}")

def print_summary(title, items):
    """Print a summary box with items
    
    Args:
        title: The title of the summary box
        items: List of items to display in the box
    """
    print("")
    print(f"{Colors.CYAN}┌─ {title} {'─' * (58 - len(title))}{Colors.RESET}")
    for item in items:
        print(f"{Colors.CYAN}│{Colors.RESET}  {item}")
    print(f"{Colors.CYAN}└{'─' * 60}{Colors.RESET}")

def print_changes(title, changes_dict):
    """Print a formatted list of configuration changes
    
    Args:
        title: The title for the changes section
        changes_dict: Dictionary of changes with stages and descriptions
    """
    print("")
    print(f"{Colors.CYAN}┌─ {title} {'─' * (58 - len(title))}{Colors.RESET}")
    print(f"{Colors.CYAN}│{Colors.RESET}")
    for stage in sorted(changes_dict.keys()):
        for key in changes_dict[stage]:
            desc = changes_dict[stage][key]['description']
            print(f"{Colors.CYAN}│{Colors.RESET}    {Colors.GREEN}▸{Colors.RESET} {desc}")
    print(f"{Colors.CYAN}└{'─' * 60}{Colors.RESET}")

def print_menu_title(title):
    """Print a menu title
    
    Args:
        title: The menu title to display
    """
    print("")
    print(f"{Colors.GREEN}{Colors.BOLD}{title}{Colors.RESET}")

def print_field(number, label, value, extra=None):
    """Print a configuration field with number, label, and value
    
    Args:
        number: The field number
        label: The field label
        value: The current value (displayed in green)
        extra: Optional extra info to display after value
    """
    extra_str = f" ({extra})" if extra else ""
    print(f"  {Colors.CYAN}{number}.{Colors.RESET} {label}: {Colors.GREEN}{value}{Colors.RESET}{extra_str}")

def print_action(message):
    """Print an action message (what the script is doing)
    
    Args:
        message: The action message
    """
    print(f"  {Colors.BLUE}▶{Colors.RESET} {message}")

def print_result(success, message):
    """Print a result message (success or failure)
    
    Args:
        success: Boolean indicating success or failure
        message: The result message
    """
    if success:
        print_ok(message)
    else:
        print_error(message)

def format_value(value, default="(not set)"):
    """Format a value for display, showing default if None/empty
    
    Args:
        value: The value to format
        default: The default string to show if value is None/empty
    
    Returns:
        Formatted string with color
    """
    if value is None or value == "":
        return f"{Colors.DIM}{default}{Colors.RESET}"
    return f"{Colors.GREEN}{value}{Colors.RESET}"

def clear_line():
    """Clear the current line in terminal"""
    print('\r' + ' ' * 80 + '\r', end='')

def graceful_exit(message="Operation cancelled by user."):
    """Print a graceful exit message and exit
    
    Args:
        message: The message to display before exiting
    """
    print(f"\n\n  {Colors.YELLOW}⚠{Colors.RESET} {message}")
    print(f"  {Colors.DIM}Exiting...{Colors.RESET}\n")
