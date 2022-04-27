# coding=utf-8
import os
# Enable GPU 0
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import tf_geometric as tfg
import tensorflow as tf
import numpy as np

# ==================================== Graph Data Structure ====================================
# In tf_geometric, the data of a graph can be represented by either a collections of
# tensors (numpy.ndarray or tf.Tensor) or a tfg.Graph object.
# A graph usually consists of x(node features), edge_index and edge_weight(optional)

# Node Features => (num_nodes, num_features)
x = np.random.randn(5, 20).astype(np.float32)  # 5 nodes, 20 features

# Edge Index => (2, num_edges)
# Each column of edge_index (u, v) represents an directed edge from u to v.
# Note that it does not cover the edge from v to u. You should provide (v, u) to cover it.
# This is not convenient for users.
# Thus, we allow users to provide edge_index in undirected form and convert it later.
# That is, we can only provide (u, v) and convert it to (u, v) and (v, u) with `convert_edge_to_directed` method.
edge_index = np.array([
    [0, 0, 1, 3],
    [1, 2, 2, 1]
])

# Edge Weight => (num_edges)
edge_weight = np.array([0.9, 0.8, 0.1, 0.2]).astype(np.float32)


# Usually, we use a graph object to manager these information
# edge_weight is optional, we can set it to None if you don't need it
# Using 'to_directed' to obtain a graph with directed edges such that we can use it as the input of GCN
graph = tfg.Graph(x=x, edge_index=edge_index, edge_weight=edge_weight).to_directed()


# Define a Graph Convolutional Layer (GCN)
gcn_layer = tfg.layers.GCN(4, activation=tf.nn.relu)
# Perform GCN on the graph
h = gcn_layer([graph.x, graph.edge_index, graph.edge_weight])
print("Node Representations (GCN on a Graph): \n", h)

for _ in range(10):
    # Using Graph.cache can avoid recomputation of GCN's normalized adjacency matrix,
    # which can dramatically improve the efficiency of GCN.
    h = gcn_layer([graph.x, graph.edge_index, graph.edge_weight], cache=graph.cache)


# For algorithms that deal with batches of graphs, we can pack a batch of graph into a BatchGraph object
# Batch graph wrap a batch of graphs into a single graph, where each nodes has an unique index and a graph index.
# The node_graph_index is the index of the corresponding graph for each node in the batch.
# The edge_graph_index is the index of the corresponding edge for each node in the batch.
batch_graph = tfg.BatchGraph.from_graphs([graph, graph, graph, graph, graph])

# We can reversely split a BatchGraph object into Graphs objects
graphs = batch_graph.to_graphs()

# Define a Graph Convolutional Layer (GCN)
batch_gcn_layer = tfg.layers.GCN(4, activation=tf.nn.relu)
# Perform GCN on the BatchGraph
batch_h = gcn_layer([batch_graph.x, batch_graph.edge_index, batch_graph.edge_weight])
print("Node Representations (GCN on a BatchGraph): \n", batch_h)

# Graph Pooling algorithms often rely on such batch data structure
# Most of them accept a BatchGraph's data as input and output a feature vector for each graph in the batch
graph_h = tfg.nn.mean_pool(batch_h, batch_graph.node_graph_index, num_graphs=batch_graph.num_graphs)
print("Graph Representations (Mean Pooling on a BatchGraph): \n", batch_h)


# Define a Graph Convolutional Layer (GCN) for scoring each node
gcn_score_layer = tfg.layers.GCN(1)
# We provide some advanced graph pooling operations such as topk_pool
node_score = gcn_score_layer([batch_graph.x, batch_graph.edge_index, batch_graph.edge_weight])
node_score = tf.reshape(node_score, [-1])
print("Score of Each Node: \n", node_score)
topk_node_index = tfg.nn.topk_pool(batch_graph.node_graph_index, node_score, ratio=0.6)
print("Top-k Node Index (Top-k Pooling): \n", topk_node_index)




# ==================================== Built-in Datasets ====================================
# all graph data are in numpy format

# Cora Dataset
graph, (train_index, valid_index, test_index) = tfg.datasets.CoraDataset().load_data()

# PPI Dataset
train_data, valid_data, test_data = tfg.datasets.PPIDataset().load_data()

# TU Datasets
# TU Datasets: https://ls11-www.cs.tu-dortmund.de/staff/morris/graphkerneldatasets
graph_dicts = tfg.datasets.TUDataset("NCI1").load_data()


# ==================================== Basic OOP API ====================================
# OOP Style GCN (Graph Convolutional Network)
gcn_layer = tfg.layers.GCN(units=20, activation=tf.nn.relu)

for graph in test_data:
    # Cache can speed-up GCN by caching the normed edge information
    outputs = gcn_layer([graph.x, graph.edge_index, graph.edge_weight], cache=graph.cache)
    print(outputs)


# OOP Style GAT (Multi-head Graph Attention Network)
gat_layer = tfg.layers.GAT(units=20, activation=tf.nn.relu, num_heads=4)
for graph in test_data:
    outputs = gat_layer([graph.x, graph.edge_index])
    print(outputs)


# OOP Style Multi-layer GCN Model
class GCNModel(tf.keras.Model):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gcn0 = tfg.layers.GCN(16, activation=tf.nn.relu)
        self.gcn1 = tfg.layers.GCN(7)
        self.dropout = tf.keras.layers.Dropout(0.5)

    def call(self, inputs, training=None, mask=None, cache=None):
        x, edge_index, edge_weight = inputs
        h = self.dropout(x, training=training)
        h = self.gcn0([h, edge_index, edge_weight], cache=cache)
        h = self.dropout(h, training=training)
        h = self.gcn1([h, edge_index, edge_weight], cache=cache)
        return h


gcn_model = GCNModel()
for graph in test_data:
    outputs = gcn_model([graph.x, graph.edge_index, graph.edge_weight], cache=graph.cache)
    print(outputs)


# ==================================== Basic Functional API ====================================
# Functional Style GCN
# Functional API is more flexible for advanced algorithms
# You can pass both data and parameters to functional APIs

gcn_w = tf.Variable(tf.random.truncated_normal([test_data[0].num_features, 20]))
for graph in test_data:
    outputs = tfg.nn.gcn(graph.x, edge_index, edge_weight, gcn_w, activation=tf.nn.relu)
    print(outputs)


# ==================================== Advanced Functional API ====================================
# Most APIs are implemented with Map-Reduce Style
# This is a gcn without without weight normalization and transformation
# Just pass the mapper/reducer/updater functions to the Functional API

for graph in test_data:
    outputs = tfg.nn.aggregate_neighbors(
        x=graph.x,
        edge_index=graph.edge_index,
        edge_weight=graph.edge_weight,
        mapper=tfg.nn.identity_mapper,
        reducer=tfg.nn.sum_reducer,
        updater=tfg.nn.sum_updater
    )
    print(outputs)
