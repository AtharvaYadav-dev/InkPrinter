import math
from shapely.geometry import LineString

def optimize_paths_tsp(paths):
    if not paths:
        return []

    unvisited = list(paths)
    current_pt = (0.0, 0.0)
    optimized = []

    # 1. Greedy NN
    while unvisited:
        best_idx = -1
        best_dist = float('inf')
        best_reverse = False
        
        for i, path in enumerate(unvisited):
            p_start = path.coords[0]
            p_end = path.coords[-1]
            
            d_start = (current_pt[0] - p_start[0])**2 + (current_pt[1] - p_start[1])**2
            d_end = (current_pt[0] - p_end[0])**2 + (current_pt[1] - p_end[1])**2
            
            if d_start < best_dist:
                best_dist = d_start
                best_idx = i
                best_reverse = False
            
            if d_end < best_dist:
                best_dist = d_end
                best_idx = i
                best_reverse = True
                
        chosen_path = unvisited.pop(best_idx)
        if best_reverse:
            chosen_path = LineString(chosen_path.coords[::-1])
            
        optimized.append(chosen_path)
        current_pt = chosen_path.coords[-1]

    # 2. 2-opt
    def dist(p1, p2):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    improved = True
    while improved:
        improved = False
        for i in range(1, len(optimized) - 1):
            for j in range(i + 1, len(optimized)):
                if j == len(optimized):
                    # We can't do j+1 if j is the last element
                    pass
                
                # actually for path TSP 2-opt, if we reverse i to j
                # we need to consider the distance from i-1 to j's new start (which is j's old end)
                # and i's new end (which is i's old start) to j+1's start
                
                p_i_minus_1_end = optimized[i-1].coords[-1]
                p_i_start = optimized[i].coords[0]
                p_j_end = optimized[j].coords[-1]
                
                if j + 1 < len(optimized):
                    p_j_plus_1_start = optimized[j+1].coords[0]
                    d_curr = dist(p_i_minus_1_end, p_i_start) + dist(p_j_end, p_j_plus_1_start)
                    d_new = dist(p_i_minus_1_end, p_j_end) + dist(p_i_start, p_j_plus_1_start)
                else:
                    # if j is the last path, we only care about the connection from i-1
                    d_curr = dist(p_i_minus_1_end, p_i_start)
                    d_new = dist(p_i_minus_1_end, p_j_end)
                
                if d_new < d_curr - 1e-5:
                    # Reverse the subsegment
                    sub_reversed = []
                    for k in range(j, i - 1, -1):
                        sub_reversed.append(LineString(optimized[k].coords[::-1]))
                    optimized[i:j+1] = sub_reversed
                    improved = True
                    break
            if improved:
                break
                
    return optimized

paths = [LineString([(0,0), (10,0)]), LineString([(20,0), (30,0)]), LineString([(10,5), (0,5)])]
opt = optimize_paths_tsp(paths)
for p in opt:
    print(list(p.coords))
