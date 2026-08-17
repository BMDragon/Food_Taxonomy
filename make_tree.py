# Created by Brandon Weiss on 8/17/2026

import os

class TreeNode:
    def __init__(self, value, code):
        self.value = value
        self.code = code
        self.children = []

    def add_child(self, child_node):
        self.children.append(child_node)

depths = {"K" : 1,
          "P" : 2,
          "C" : 3,
          "O" : 4,
          "F" : 5,
          "G" : 6,
          "S" : 7
          }
base = 3

def save_tree(node, string, level):
    mdep = level
    if node.code != '':
        mdep = depths[node.code]
    if len(node.children) == 0:
        return string + node.value + ':' + str((mdep - level + 1)*base)
    string = string + '('
    for i in range(len(node.children)):
        string = save_tree(node.children[i], string, mdep + 1)
        string = string + ','
    if string[-1] == ',':
        string = string[:-1]
    string = string + ')' + node.value + ':' + str((mdep - level + 1)*base)
    return string

root = TreeNode("Eukaryota", '')
ranks = {"Eukaryota" : root}

dir = "./taxonomy_files/"
for filename in os.listdir(dir):
    with open(dir+filename, 'r') as file:
        node = root
        dep = 0
        for line in file:
            ln = line.strip().split(';')
            s = ln[0]
            try:
                x = ln[1]
                if len(x) > 0:
                    x = x[-1]
                    depths[x] = max(depths[x], dep)
                    dep = depths[x]
            except:
                x = ''
            if s not in ranks.keys():
                temp = TreeNode(s, x)
                node.add_child(temp)
                ranks[s] = temp
            node = ranks[s]
            dep = dep + 1

with open('./taxon_tree.txt', 'w') as f:
    f.write(save_tree(root, "", 0) + ";")
f.close()