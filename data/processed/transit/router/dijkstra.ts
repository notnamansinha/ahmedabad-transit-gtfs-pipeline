/**
 * dijkstra.ts
 * Dijkstra's shortest-path algorithm over the multi-modal transit graph.
 * Returns the lowest-weight path (in seconds) from origin stop to destination stop.
 *
 * This is a standard binary-min-heap Dijkstra implementation.
 * The graph's `weight_secs` field drives all decisions.
 */

import type { GraphEdge, TransitGraph } from "./graph";

export interface DijkstraResult {
  /** Total cost in seconds from origin to destination */
  cost_secs: number;
  /** Ordered sequence of edges traversed (the path) */
  path: GraphEdge[];
  /** Whether a path was found */
  found: boolean;
}

interface QueueItem {
  node_id: string;
  cost: number;
}

/**
 * MinHeap for Dijkstra's priority queue.
 * Keeps the lowest-cost node at the top.
 */
class MinHeap {
  private data: QueueItem[] = [];

  push(item: QueueItem): void {
    this.data.push(item);
    this._bubbleUp(this.data.length - 1);
  }

  pop(): QueueItem | undefined {
    if (this.data.length === 0) return undefined;
    const top = this.data[0];
    const last = this.data.pop()!;
    if (this.data.length > 0) {
      this.data[0] = last;
      this._sinkDown(0);
    }
    return top;
  }

  get size(): number {
    return this.data.length;
  }

  private _bubbleUp(i: number): void {
    while (i > 0) {
      const parent = Math.floor((i - 1) / 2);
      if (this.data[parent].cost <= this.data[i].cost) break;
      [this.data[parent], this.data[i]] = [this.data[i], this.data[parent]];
      i = parent;
    }
  }

  private _sinkDown(i: number): void {
    const n = this.data.length;
    while (true) {
      let smallest = i;
      const l = 2 * i + 1;
      const r = 2 * i + 2;
      if (l < n && this.data[l].cost < this.data[smallest].cost) smallest = l;
      if (r < n && this.data[r].cost < this.data[smallest].cost) smallest = r;
      if (smallest === i) break;
      [this.data[smallest], this.data[i]] = [this.data[i], this.data[smallest]];
      i = smallest;
    }
  }
}

/**
 * Run Dijkstra from `origin_id` to `dest_id` on the given transit graph.
 * Returns the cheapest path (by total seconds) and the edge sequence.
 */
export function dijkstra(
  graph: TransitGraph,
  origin_id: string,
  dest_id: string,
): DijkstraResult {
  const dist = new Map<string, number>();
  const prev = new Map<string, { node: string; edge: GraphEdge }>();
  const heap = new MinHeap();

  dist.set(origin_id, 0);
  heap.push({ node_id: origin_id, cost: 0 });

  while (heap.size > 0) {
    const current = heap.pop()!;
    const { node_id, cost } = current;

    // Early exit if we reached the destination
    if (node_id === dest_id) break;

    // Skip stale entries
    if (cost > (dist.get(node_id) ?? Infinity)) continue;

    const edges = graph.adjacency.get(node_id) ?? [];
    for (const edge of edges) {
      const newCost = cost + edge.weight_secs;
      const oldCost = dist.get(edge.to_id) ?? Infinity;
      if (newCost < oldCost) {
        dist.set(edge.to_id, newCost);
        prev.set(edge.to_id, { node: node_id, edge });
        heap.push({ node_id: edge.to_id, cost: newCost });
      }
    }
  }

  const totalCost = dist.get(dest_id) ?? Infinity;
  if (totalCost === Infinity) {
    return { cost_secs: Infinity, path: [], found: false };
  }

  // Reconstruct path
  const path: GraphEdge[] = [];
  let cursor = dest_id;
  while (prev.has(cursor)) {
    const { edge } = prev.get(cursor)!;
    path.unshift(edge);
    cursor = edge.from_id;
  }

  return { cost_secs: totalCost, path, found: true };
}
