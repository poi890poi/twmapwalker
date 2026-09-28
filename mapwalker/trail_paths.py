"""Keep only consecutive edges accepted by the local dash graph."""
def supported_runs(ordered, graph):
    if not ordered:
        return []
    result = []
    run = [ordered[0]]
    for node in ordered[1:]:
        if node not in graph[run[-1]]:
            result.append(run)
            run = []
        run.append(node)
    result.append(run)
    return result
