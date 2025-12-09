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

import  simple_term_menu

# create a single select menu, with the default choose on the top
# title: the title of the menu
# lists: the list of items to be selected
# default: the default item(s) to be selected, 
# indent: the number of spaces to indent the menu items
# index: add quick select index to the menu items (only for single select)
def menu_select(title, lists, default=None, indent=3, index=None, multi_select=False):
    menu_entries = []
    preselected_entries = []

    if multi_select:
        for i, item in enumerate(lists):
            # add desired indent to the menu items
            entry = ' ' * indent + item
            menu_entries.append(entry)
            if default is not None and item in default:
                preselected_entries.append(i)

        terminal_menu = simple_term_menu.TerminalMenu(menu_entries, title=title, multi_select=True, preselected_entries=preselected_entries)
        menu_entry_index = terminal_menu.show()
        if menu_entry_index is None:
            return None
        else:
            return [lists[i] for i in menu_entry_index]

    else:
        if default is not None:
            lists.remove(default)
            lists.insert(0, default)

        for item in lists:
            if index is not None:
                #entry = ' '*indent + f"[{index}] " + item 
                entry = f"[{index}] " + item 
                index = index + 1
            else:
                entry = ' '*indent + item
            menu_entries.append(entry)

        terminal_menu = simple_term_menu.TerminalMenu(menu_entries, title=title)
        menu_entry_index = terminal_menu.show()
        if menu_entry_index is None:
            return None
        else:
            return lists[menu_entry_index]