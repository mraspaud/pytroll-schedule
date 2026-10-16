#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2014 Martin Raspaud

# Author(s):

#   Martin Raspaud <martin.raspaud@smhi.se>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Graph manipulation."""
import numpy as np


class Graph():
    """A graph class."""

    def __init__(self, n_vertices=None, adj_matrix=None):
        """Set up the graph."""
        if n_vertices is not None:
            self.order = n_vertices
            self.vertices = np.arange(self.order)
            self.adj_matrix = np.zeros((self.order, self.order), bool)
            self.weight_matrix = np.zeros((self.order, self.order), float)
        elif adj_matrix is not None:
            self.order = adj_matrix.shape[0]
            self.vertices = np.arange(self.order)
            self.adj_matrix = adj_matrix
            self.weight_matrix = np.zeros_like(adj_matrix)

    def weight(self, u, v):
        """Weight of the *u*-*v* edge."""
        return self.weight_matrix[u, v]

    def neighbours(self, v):
        """Find neighbours."""
        return self.vertices[self.adj_matrix[v, :] != 0]

    def add_edge(self, v1, v2, weight=1):
        """Add an edge."""
        self.weight_matrix[v1, v2] = weight
        self.weight_matrix[v2, v1] = weight
        self.adj_matrix[v1, v2] = True
        self.adj_matrix[v2, v1] = True

    def add_arc(self, v1, v2, weight=1):
        """Add an arc."""
        self.adj_matrix[v1, v2] = True
        self.weight_matrix[v1, v2] = weight

    def bron_kerbosch(self, r, p, x):
        """Get the maximal cliques."""
        if len(p) == 0 and len(x) == 0:
            yield r
        for v in p:
            for res in self.bron_kerbosch(r | set((v, )),
                                          p & set(self.neighbours(v)),
                                          x & set(self.neighbours(v))):
                yield res
            p = p - set((v, ))
            x = x | set((v, ))

    def dag_longest_path(self, v1, v2=None):
        """Find the longest path between v1 and v2.

        Give the longest path from *v1* to all other vertices or *v2* if
        specified. Assumes the vertices are sorted topologically and that the
        graph is directed and acyclic (DAG).
        """
        self.weight_matrix = -self.weight_matrix
        dist, path = self.dag_shortest_path(v1, v2)
        self.weight_matrix = -self.weight_matrix
        return dist, path

    def dag_shortest_path(self, v1, v2=None):
        """Find the shortest path between v1 and v2.

        Give the shortest path from *v1* to all other vertices or *v2* if
        specified. Assumes the vertices are sorted topologically and that the
        graph is directed and acyclic (DAG). *v1* and *v2* are the indices of
        the vertices in the vertice list.
        """
        # Dijkstra for DAGs.

        dists = [np.inf] * self.order
        paths = [list() for _ in range(self.order)]

        dists[v1] = 0

        for u in self.vertices:
            # could be interrupted when we reach v2 ?
            for v in self.neighbours(u):
                if (dists[v] > dists[u] + self.weight(u, v)):
                    dists[v] = dists[u] + self.weight(u, v)
                    paths[v] = u

        if v2 is None:
            return dists, paths
        else:
            end = v2
            path = [end]
            while end != v1:
                path.append(paths[end])
                end = paths[end]
            return dists[v2], path

    def save(self, filename):
        """Save a file."""
        np.savez_compressed(filename,
                            adj=self.adj_matrix,
                            weights=self.weight_matrix)

    def load(self, filename):
        """Load a file."""
        stuff = np.load(filename)
        self.adj_matrix = stuff["adj"]
        self.weight_matrix = stuff["weights"]
        self.order = self.adj_matrix.shape[0]
        self.vertices = np.arange(self.order)

    def export(self, filename="./sched.gv", labels=None):
        """Export the schedule to gv format for visualization.

        To generate a pdf out of it::

            dot sched.gv -Tpdf -osched.pdf.
        """
        with open(filename, "w") as fd_:
            fd_.write('digraph schedule { \n size="80, 10";\n center="1";\n')
            for v1 in range(1, self.order - 1):
                for v2 in range(1, self.order - 1):
                    if self.adj_matrix[v1, v2]:
                        fd_.write('"' + str(labels[v1 - 1]) + '"' + " -> " +
                                  '"' + str(labels[v2 - 1]) + '"' +
                                  ' [ label = "' + str(self.weight_matrix[v1, v2]) + '" ];\n')

            fd_.write("}\n")
