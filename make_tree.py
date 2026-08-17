# Created by Brandon Weiss on 8/17/2026

import os

class TreeNode:
    def __init__(self, value):
        self.value = value
        self.children = []  # List to hold references to child nodes

    def add_child(self, child_node):
        self.children.append(child_node)

def save_tree(node, string):
    if len(node.children) == 0:
        return string + node.value
    string = string + '('
    for i in range(len(node.children)):
        string = save_tree(node.children[i], string)
        string = string + ','
    if string[-1] == ',':
        string = string[:-1]
    string = string + ')' + node.value
    return string

root = TreeNode("Eukaryota")
ranks = {"Eukaryota" : root}

dir = "./taxonomy_files/"
for filename in os.listdir(dir):
    with open(dir+filename, 'r') as file:
        node = root
        for line in file:
            s = line.split(';')[0]
            if s not in ranks.keys():
                temp = TreeNode(s)
                node.add_child(temp)
                ranks[s] = temp
            node = ranks[s]

with open('./taxon_tree.txt', 'w') as f:
    f.write(save_tree(root, "") + ";")
f.close()