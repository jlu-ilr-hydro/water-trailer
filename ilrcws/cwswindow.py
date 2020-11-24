'''
Created on 11.06.2015

@author: kraft-p
'''

import json
import Tkinter as tk
import ttk
from pprint import pprint as pprint

class CoWSWindow(object):
    def __init__(self,checker):
        # Setup the root UI
        self.root = tk.Tk()
        self.root.title("CoWS-Data")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
def JSONTree(Tree, Parent, Dictionery, TagList=[]):
    for key in Dictionery :
        if isinstance(Dictionery[key], dict):
            Tree.insert(Parent, 'end', key, text=key)
            TagList.append(key)
            JSONTree(Tree, key, Dictionery[key], TagList)
            pprint(TagList)
        elif isinstance(Dictionery[key], list):
            Tree.insert(Parent, 'end', key, text=key) # Still working on this
        else:
            Tree.insert(Parent, 'end', key, text=key, value=Dictionery[key])

if __name__ == "__main__" :
    # Setup Data
    # Setup the Frames
    TreeFrame = ttk.Frame(root, padding="3")
    TreeFrame.grid(row=0, column=0, sticky=tk.NSEW)
    # Setup the Tree
    tree = ttk.Treeview(TreeFrame, columns=('Values'))
    tree.column('Values', width=100, anchor='center')
    tree.heading('Values', text='Values')
    JSONTree(tree, '', Data)
    tree.pack(fill=tk.BOTH, expand=1)
    # Limit windows minimum dimensions
    root.update_idletasks()
    root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())
    root.mainloop()